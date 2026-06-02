# FX Transfer Advisor

An AWS-native data pipeline that ingests daily FX rates,
computes multi-window Bollinger Band signals, and delivers
a daily email digest indicating whether current rates are
favorable for transferring money.

## Architecture

EventBridge (6:00 AM UTC, Mon-Fri)
    → Lambda: fx-fetch-rates
    → S3: raw/usd/{date}.json

EventBridge (6:30 AM UTC, Mon-Fri)
    → Lambda: fx-compute-signal
    → Athena: multi-window Bollinger query
    → DynamoDB: fx-signals table
    → SES: daily email digest

## AWS Services Used

S3, Lambda, EventBridge Scheduler, Glue (Crawler + Data Catalog),
Athena, DynamoDB, SES, IAM, CloudWatch

## Signal Logic

Uses Bollinger Bands (%B indicator) across four time windows
(7-day, 30-day, 90-day, 1-year) to classify the current FX rate
as HIGH, TYPICAL, or LOW relative to recent behavior.

Raw percentiles fail for currency pairs like USD/INR that have
a structural depreciation trend. Bollinger Bands solve this by
computing deviation from a rolling mean, making the signal
stationary and meaningful regardless of long-term drift.
