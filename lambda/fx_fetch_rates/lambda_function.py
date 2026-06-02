import json
import boto3
import urllib.request
import os
from datetime import datetime, timedelta

def lambda_handler(event, context):
    
    # Read from environment variables instead of hardcoding
    bucket_name = os.environ.get('BUCKET_NAME', 'fx-rates-yourname')
    region = os.environ.get('AWS_REGION_NAME', 'us-east-2')
    
    target_date = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
    url = f"https://api.frankfurter.app/{target_date}?from=USD&to=INR,EUR,GBP"
    
    print(f"Fetching rates for {target_date}")
    
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'Mozilla/5.0 (compatible; fx-rates-bot/1.0)'}
    )
    
    with urllib.request.urlopen(req, timeout=10) as response:
        data = json.loads(response.read())
    
    print(f"Rates fetched: {data['rates']}")
    
    record = {
        "date": data["date"],
        "base": data["base"],
        "rates": data["rates"],
        "fetched_at": datetime.now().isoformat()
    }
    
    s3 = boto3.client('s3', region_name=region)
    key = f"raw/usd/{data['date']}.json"
    
    s3.put_object(
        Bucket=bucket_name,
        Key=key,
        Body=json.dumps(record),
        ContentType='application/json'
    )
    
    print(f"Saved to s3://{bucket_name}/{key}")
    
    return {
        "statusCode": 200,
        "date": data["date"],
        "rates": data["rates"]
    }