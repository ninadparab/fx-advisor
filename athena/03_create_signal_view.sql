-- This view is stored in the Glue Data Catalog as a definition only.

CREATE OR REPLACE VIEW fx_rates_db.usd_inr_signals AS

WITH base AS (
    SELECT
        date,
        rates.inr AS rate
    FROM "fx_rates_db"."usd"
),

stats AS (
    SELECT
        date,
        rate,

        AVG(rate) OVER (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS ma_7,
        STDDEV(rate) OVER (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS sd_7,
        COUNT(*) OVER (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS cnt_7,

        AVG(rate) OVER (ORDER BY date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS ma_30,
        STDDEV(rate) OVER (ORDER BY date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS sd_30,
        COUNT(*) OVER (ORDER BY date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS cnt_30,

        AVG(rate) OVER (ORDER BY date ROWS BETWEEN 89 PRECEDING AND CURRENT ROW) AS ma_90,
        STDDEV(rate) OVER (ORDER BY date ROWS BETWEEN 89 PRECEDING AND CURRENT ROW) AS sd_90,
        COUNT(*) OVER (ORDER BY date ROWS BETWEEN 89 PRECEDING AND CURRENT ROW) AS cnt_90,

        AVG(rate) OVER (ORDER BY date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) AS ma_252,
        STDDEV(rate) OVER (ORDER BY date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) AS sd_252,
        COUNT(*) OVER (ORDER BY date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) AS cnt_252

    FROM base
),

bollinger AS (
    SELECT
        date,
        rate,

        (rate - (ma_7 - 2 * sd_7)) / NULLIF(4 * sd_7, 0) AS pct_b_7,
        (rate - (ma_30 - 2 * sd_30)) / NULLIF(4 * sd_30, 0) AS pct_b_30,
        (rate - (ma_90 - 2 * sd_90)) / NULLIF(4 * sd_90, 0) AS pct_b_90,
        (rate - (ma_252 - 2 * sd_252)) / NULLIF(4 * sd_252, 0) AS pct_b_252,

        cnt_7, cnt_30, cnt_90, cnt_252

    FROM stats
)

SELECT
    date,
    ROUND(rate, 4) AS usd_inr,

    ROUND(pct_b_7, 2) AS pb_7d,
    ROUND(pct_b_30, 2) AS pb_30d,
    ROUND(pct_b_90, 2) AS pb_90d,
    ROUND(pct_b_252, 2) AS pb_1y,

    CASE
        WHEN cnt_7 < 7 THEN 'INSUFFICIENT_DATA'
        WHEN pct_b_7 > 0.8 THEN 'HIGH'
        WHEN pct_b_7 < 0.2 THEN 'LOW'
        ELSE 'TYPICAL'
    END AS signal_7d,

    CASE
        WHEN cnt_30 < 30 THEN 'INSUFFICIENT_DATA'
        WHEN pct_b_30 > 0.8 THEN 'HIGH'
        WHEN pct_b_30 < 0.2 THEN 'LOW'
        ELSE 'TYPICAL'
    END AS signal_30d,

    CASE
        WHEN cnt_90 < 90 THEN 'INSUFFICIENT_DATA'
        WHEN pct_b_90 > 0.8 THEN 'HIGH'
        WHEN pct_b_90 < 0.2 THEN 'LOW'
        ELSE 'TYPICAL'
    END AS signal_90d,

    CASE
        WHEN cnt_252 < 252 THEN 'INSUFFICIENT_DATA'
        WHEN pct_b_252 > 0.8 THEN 'HIGH'
        WHEN pct_b_252 < 0.2 THEN 'LOW'
        ELSE 'TYPICAL'
    END AS signal_1y

FROM bollinger