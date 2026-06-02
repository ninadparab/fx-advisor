-- Sanity check: verify data completeness and basic stats

SELECT 
    COUNT(*) AS total_trading_days,
    MIN(date) AS earliest_date,
    MAX(date) AS latest_date,
    ROUND(MIN(rates.inr), 4) AS min_inr,
    ROUND(MAX(rates.inr), 4) AS max_inr,
    ROUND(AVG(rates.inr), 4) AS avg_inr,
    ROUND(MIN(rates.eur), 4) AS min_eur,
    ROUND(MAX(rates.eur), 4) AS max_eur,
    ROUND(MIN(rates.gbp), 4) AS min_gbp,
    ROUND(MAX(rates.gbp), 4) AS max_gbp
FROM "fx_rates_db"."usd";


