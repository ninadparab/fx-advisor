import json
import boto3
import os
import time
from datetime import datetime
from decimal import Decimal

def lambda_handler(event, context):
    
    athena = boto3.client('athena', region_name='us-east-2')
    dynamodb = boto3.resource('dynamodb', region_name='us-east-2')
    ses = boto3.client('ses', region_name='us-east-2')
    
    output_location = os.environ['ATHENA_OUTPUT_LOCATION']
    database = os.environ['ATHENA_DATABASE']
    table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])
    email_from = os.environ['EMAIL_FROM']
    email_to = os.environ['EMAIL_TO']
    
    # Step 1: Query Athena for the latest signal
    query = """
        SELECT *
        FROM fx_rates_db.usd_inr_signals
        ORDER BY date DESC
        LIMIT 1
    """
    
    response = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={'Database': database},
        ResultConfiguration={'OutputLocation': output_location}
    )
    query_id = response['QueryExecutionId']
    print(f"Athena query started: {query_id}")
    
    # Step 2: Wait for query to finish
    while True:
        status = athena.get_query_execution(QueryExecutionId=query_id)
        state = status['QueryExecution']['Status']['State']
        if state in ['SUCCEEDED', 'FAILED', 'CANCELLED']:
            break
        time.sleep(1)
    
    if state != 'SUCCEEDED':
        reason = status['QueryExecution']['Status'].get('StateChangeReason', 'unknown')
        raise Exception(f"Athena query failed: {reason}")
    
    # Step 3: Fetch results
    results = athena.get_query_results(QueryExecutionId=query_id)
    rows = results['ResultSet']['Rows']
    
    if len(rows) < 2:
        raise Exception("No data returned from Athena view")
    
    # Row 0 is headers, row 1 is data
    headers = [col['VarCharValue'] for col in rows[0]['Data']]
    values = [col.get('VarCharValue', '') for col in rows[1]['Data']]
    record = dict(zip(headers, values))
    
    print(f"Latest signal: {record}")
    
    # Step 4: Write to DynamoDB
    table.put_item(Item={
        'currency_pair': 'USD_INR',
        'date': record['date'],
        'usd_inr': Decimal(record['usd_inr']),
        'pb_7d': Decimal(record['pb_7d']) if record.get('pb_7d') else None,
        'pb_30d': Decimal(record['pb_30d']) if record.get('pb_30d') else None,
        'pb_90d': Decimal(record['pb_90d']) if record.get('pb_90d') else None,
        'pb_1y': Decimal(record['pb_1y']) if record.get('pb_1y') else None,
        'signal_7d': record.get('signal_7d', 'UNKNOWN'),
        'signal_30d': record.get('signal_30d', 'UNKNOWN'),
        'signal_90d': record.get('signal_90d', 'UNKNOWN'),
        'signal_1y': record.get('signal_1y', 'UNKNOWN'),
        'updated_at': datetime.now().isoformat()
    })
    print("Saved signal to DynamoDB")
    
    # Step 5: Format and send email
    email_body = format_email(record)
    
    ses.send_email(
        Source=email_from,
        Destination={'ToAddresses': [email_to]},
        Message={
            'Subject': {'Data': f"FX Signal {record['date']}: USD/INR = {record['usd_inr']}"},
            'Body': {'Text': {'Data': email_body}}
        }
    )
    print(f"Email sent to {email_to}")
    
    return {
        'statusCode': 200,
        'signal': record
    }


def format_email(record):
    """Format the signal record into a readable email body."""
    
    return f"""
FX Transfer Signal — {record['date']}

USD/INR rate: {record['usd_inr']}

Signal across windows:
  Last 7 days:    {record.get('signal_7d', 'N/A')}   (%B = {record.get('pb_7d', 'N/A')})
  Last 30 days:   {record.get('signal_30d', 'N/A')}   (%B = {record.get('pb_30d', 'N/A')})
  Last 90 days:   {record.get('signal_90d', 'N/A')}   (%B = {record.get('pb_90d', 'N/A')})
  Last 1 year:    {record.get('signal_1y', 'N/A')}   (%B = {record.get('pb_1y', 'N/A')})

Interpretation:
- HIGH: today's rate is in the upper end of the window — favorable to send USD
- TYPICAL: no strong signal either way
- LOW: today's rate is in the lower end — consider waiting if you can

Note: %B ranges from 0 (lower band) to 1 (upper band).
This is an experimental tool. Not financial advice.
"""