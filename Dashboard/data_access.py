"""Data access layer — fetches FX rates and signals from AWS."""
import os
import boto3
import pandas as pd
import io
import time
from decimal import Decimal
import streamlit as st

REGION = 'us-east-2'
ATHENA_OUTPUT = 's3://fx-rates-ninpar/athena-results/'
DYNAMODB_TABLE = 'fx-signals'


def _configure_aws_credentials():
    """Set up AWS credentials.
    
    Priority:
    1. Streamlit Cloud secrets (st.secrets["aws"])
    2. Local AWS CLI credentials (~/.aws/credentials)
    3. Environment variables
    
    Returns True if credentials are configured, False otherwise.
    """
    # Try Streamlit secrets first
    try:
        if "aws" in st.secrets:
            aws_creds = st.secrets["aws"]
            os.environ["AWS_ACCESS_KEY_ID"] = aws_creds["access_key_id"]
            os.environ["AWS_SECRET_ACCESS_KEY"] = aws_creds["secret_access_key"]
            os.environ["AWS_DEFAULT_REGION"] = aws_creds.get("region", REGION)
            return True
    except (FileNotFoundError, KeyError, AttributeError):
        pass
    
    # Fall back to local credentials — boto3 finds them automatically
    # via ~/.aws/credentials or environment variables
    try:
        session = boto3.Session()
        creds = session.get_credentials()
        if creds is None:
            return False
        return True
    except Exception:
        return False


# Configure credentials at module load time
_CREDS_CONFIGURED = _configure_aws_credentials()


def _decimal_to_float(obj):
    """Recursively convert DynamoDB Decimal to float for JSON/display."""
    if isinstance(obj, list):
        return [_decimal_to_float(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _decimal_to_float(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        return float(obj)
    return obj


def _query_athena(query, database='fx_rates_db'):
    """Run an Athena query and return a DataFrame."""
    if not _CREDS_CONFIGURED:
        raise Exception(
            "AWS credentials not configured. "
            "On Streamlit Cloud: add AWS credentials in app Settings -> Secrets. "
            "Locally: run `aws configure` or set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY."
        )
    
    athena = boto3.client('athena', region_name=REGION)
    s3 = boto3.client('s3', region_name=REGION)
    
    response = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={'Database': database},
        ResultConfiguration={'OutputLocation': ATHENA_OUTPUT}
    )
    query_id = response['QueryExecutionId']
    
    while True:
        status = athena.get_query_execution(QueryExecutionId=query_id)
        state = status['QueryExecution']['Status']['State']
        if state in ['SUCCEEDED', 'FAILED', 'CANCELLED']:
            break
        time.sleep(1)
    
    if state != 'SUCCEEDED':
        reason = status['QueryExecution']['Status'].get('StateChangeReason', 'unknown')
        athena_error = status['QueryExecution']['Status'].get('AthenaError', {})
        error_msg = athena_error.get('ErrorMessage', '')
        full_msg = f"Athena query failed (state={state}): {reason}"
        if error_msg:
            full_msg += f"\nAthena error: {error_msg}"
        full_msg += f"\nQuery: {query[:200]}..."
        raise Exception(full_msg)
    
    result_location = status['QueryExecution']['ResultConfiguration']['OutputLocation']
    bucket = result_location.split('/')[2]
    key = '/'.join(result_location.split('/')[3:])
    obj = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_csv(io.BytesIO(obj['Body'].read()))


def credentials_configured():
    """Public check — used by app.py to show a helpful error if AWS isn't set up."""
    return _CREDS_CONFIGURED


@st.cache_data(ttl=3600)
def load_fx_history(days=120):
    """Load the most recent N days of FX rates for all pairs."""
    df = _query_athena(f"""
        SELECT date, 
               rates.inr AS usd_inr, 
               rates.eur AS usd_eur,
               rates.gbp AS usd_gbp, 
               rates.mxn AS usd_mxn, 
               rates.php AS usd_php
        FROM fx_rates_db.usd
        ORDER BY date DESC
        LIMIT {days}
    """)
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date').sort_index()
    return df


@st.cache_data(ttl=3600)
def load_latest_signals():
    """Load latest precomputed Bollinger signals from DynamoDB."""
    if not _CREDS_CONFIGURED:
        return {}
    
    try:
        dynamodb = boto3.resource('dynamodb', region_name=REGION)
        table = dynamodb.Table(DYNAMODB_TABLE)
        
        pair_map = {
            'usd_inr': 'USD_INR',
            'usd_eur': 'USD_EUR',
            'usd_gbp': 'USD_GBP',
            'usd_mxn': 'USD_MXN',
            'usd_php': 'USD_PHP'
        }
        
        signals = {}
        for lower_pair, upper_pair in pair_map.items():
            response = table.query(
                KeyConditionExpression='currency_pair = :p',
                ExpressionAttributeValues={':p': upper_pair},
                ScanIndexForward=False,
                Limit=1
            )
            if response['Items']:
                signals[lower_pair] = _decimal_to_float(response['Items'][0])
        
        return signals
    except Exception as e:
        print(f"DynamoDB load failed: {e}")
        return {}


def load_central_bank_events():
    """Load the central bank meeting schedule."""
    candidate_paths = [
        '../infrastructure/central_bank_meetings.csv',
        'infrastructure/central_bank_meetings.csv',
        './infrastructure/central_bank_meetings.csv'
    ]
    
    for path in candidate_paths:
        if os.path.exists(path):
            df = pd.read_csv(path)
            df['date'] = pd.to_datetime(df['date'])
            return df
    
    return pd.DataFrame(columns=['date', 'central_bank'])