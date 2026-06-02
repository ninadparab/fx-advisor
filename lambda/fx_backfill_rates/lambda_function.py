import json
import boto3
import urllib.request
import os
from datetime import datetime, timedelta
import time

def lambda_handler(event, context):
    
    bucket_name = os.environ.get('BUCKET_NAME', 'fx-rates-yourname')
    region = os.environ.get('AWS_REGION_NAME', 'us-east-2')
    
    s3 = boto3.client('s3', region_name=region)
    
    # Backfill last 400 days
    saved = []
    skipped = []
    
    for days_ago in range(1, 400):
        target_date = (datetime.now() - timedelta(days=days_ago)).strftime('%Y-%m-%d')
        url = f"https://api.frankfurter.app/{target_date}?from=USD&to=INR,EUR,GBP"
        
        try:
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'Mozilla/5.0 (compatible; fx-rates-bot/1.0)'}
            )
            
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read())
            
            record = {
                "date": data["date"],
                "base": data["base"],
                "rates": data["rates"],
                "fetched_at": datetime.now().isoformat()
            }
            
            key = f"raw/usd/{data['date']}.json"
            
            s3.put_object(
                Bucket=bucket_name,
                Key=key,
                Body=json.dumps(record),
                ContentType='application/json'
            )
            
            saved.append(data['date'])
            print(f"Saved {data['date']}: INR={data['rates'].get('INR')}")
            
            # Small delay to avoid hammering the API
            time.sleep(0.3)
            
        except Exception as e:
            print(f"Skipped {target_date}: {e}")
            skipped.append(target_date)
            continue
    
    return {
        "statusCode": 200,
        "saved": len(saved),
        "skipped": len(skipped),
        "date_range": f"{saved[-1]} to {saved[0]}" if saved else "none"
    }
