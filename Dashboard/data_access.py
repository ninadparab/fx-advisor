"""Data access layer — fetches FX rates and signals from AWS."""
import boto3
import pandas as pd
import io
import time
from decimal import Decimal
import streamlit as st

REGION = 'us-east-2'
ATHENA_OUTPUT = 's3://fx-rates-ninpar/athena-results/'
DYNAMODB_TABLE = 'fx-signals'

# Pick up credentials from Streamlit secrets if running on cloud
try:
    aws_creds = st.secrets["aws"]
    boto3.setup_default_session(
        aws_access_key_id=aws_creds["access_key_id"],
        aws_secret_access_key=aws_creds["secret_access_key"],
        region_name=aws_creds["region"]
    )
except (FileNotFoundError, KeyError):
    # Local development — uses AWS CLI credentials
    pass


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
        raise Exception(f"Athena query failed: {reason}")
    
    result_location = status['QueryExecution']['ResultConfiguration']['OutputLocation']
    bucket = result_location.split('/')[2]
    key = '/'.join(result_location.split('/')[3:])
    obj = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_csv(io.BytesIO(obj['Body'].read()))


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
    """Load latest precomputed Bollinger signals from DynamoDB.
    
    DynamoDB stores pairs as USD_INR (uppercase); dashboard uses usd_inr (lowercase).
    Returns dict mapping lowercase pair name to signal record.
    Returns empty dict if table unavailable — dashboard falls back to live computation."""
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
                ScanIndexForward=False,  # most recent first
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
    import os
    
    # Try multiple paths — works both locally and on Streamlit Cloud
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
    
    # Fall back to empty if file not found — dashboard handles this gracefully
    return pd.DataFrame(columns=['date', 'central_bank'])