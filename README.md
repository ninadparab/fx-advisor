# FX Transfer Advisor

An end-to-end FX transfer advisory system built on AWS. It tracks five USD currency pairs daily, generates probabilistic forecasts and volatility signals, and produces actionable "transfer now vs. wait" guidance for people sending money across borders.

**Currency pairs:** USD/INR, USD/EUR, USD/GBP, USD/MXN, USD/PHP
**Live pipeline:** Automated daily on AWS (Lambda + S3 + Glue + Athena + DynamoDB + SES)
**Repo:** github.com/ninadparab/fx-advisor

---

## What This Project Does

Most FX tools tell you what the rate *is*. This one helps you decide what to *do* — transfer now, wait, or split the transfer over time — by combining three honest signals:

1. **Context** — where today's rate sits relative to its recent range (Bollinger Bands)
2. **Direction** — calibrated probability of the rate rising or falling (Chronos-Bolt, selective)
3. **Volatility** — how turbulent the market is right now (GARCH), which drives urgency

The guiding principle throughout was intellectual honesty: rather than overpromising "AI predicts FX," the system surfaces only the signals that survive rigorous statistical testing, and clearly separates what works from what doesn't.

---

## Architecture

```
EventBridge (6:00 AM UTC, Mon-Fri)
    -> Lambda: fx-fetch-rates -> S3: fx-rates-ninpar/raw/usd/{date}.json
EventBridge (6:30 AM UTC, Mon-Fri)
    -> Lambda: fx-compute-signal
       -> Athena (multi-window Bollinger query on Glue catalog)
       -> DynamoDB: fx-signals (partition: currency_pair, sort: date)
       -> SES email digest
```

**Data layer:** S3 (raw JSON) + Glue Catalog (schema) + Athena (serverless SQL)
**Serving layer:** DynamoDB (fast key-value reads)
**Compute:** Lambda (serverless, pay-per-invocation)
**Orchestration:** EventBridge (cron schedules)
**Notification:** SES (daily email digest)

---

## Key Findings

### 1. Daily FX direction is near-random (Meese-Rogoff confirmed)
No model significantly beats the majority-class baseline on any pair. This is the expected result from decades of FX research and is honestly reported rather than hidden.

### 2. Foundation models give the best *honest* predictions
Chronos-Bolt achieves 63% direction accuracy on USD/INR (statistically significant vs random, p=0.026) with well-calibrated probability intervals (77-87% coverage at the 80% target). It does not beat the majority baseline, but its probabilistic outputs are trustworthy.

### 3. GARCH volatility prediction is the standout result
GARCH(1,1) with Student-t errors reduces RMSE by 23-32% vs the naive baseline across all pairs, and by 56-82% in high-volatility regimes. This is the most robust, reproducible win and powers the product's urgency signal.

### 4. Multi-step forecasting is dramatically harder than single-step
AutoGluon's best models achieve Theil U 1.3-4.1 on 30-day forecasts vs ~1.0 on 1-day forecasts. The product focuses on near-term signals accordingly.

### 5. Event-window direction shows a promising (unconfirmed) pattern
Chronos direction accuracy on trending pairs (INR, PHP) rises 6-14 percentage points in the 2-day window around central bank meetings. Suggestive but not statistically significant at the current sample size (n=13 per pair).

---

## Production Model Stack

| Component | Status | Use Case | Evidence |
|---|---|---|---|
| Bollinger Bands (EWMA) | Deployed | Context, all pairs | EWMA beats SMA for trending pairs |
| Chronos-Bolt | Deployed (selective) | Direction: USD/INR, USD/PHP | 63% on INR (p=0.026), calibrated intervals |
| GARCH(1,1) Student-t | Deployed | Volatility, all pairs | Theil U 0.68-0.77, 0.18-0.44 in high-vol |

### Rejected (with documented evidence)

| Component | Reason |
|---|---|
| Prophet | Theil U 2.1-3.7, catastrophically worse than naive |
| XGBoost | No improvement over majority-class baseline |
| AutoARIMA / AutoETS | Predictions degenerate to trivial trend-following |
| AutoGluon ensembles | Multi-step Theil U 1.3-4.1 |

---

## Notebooks

| # | Notebook | Purpose |
|---|---|---|
| 01 | `eda_fx_rates` | Exploratory analysis, Sharpe/autocorrelation, naive baseline |
| 02 | `sma_vs_ewma_bollinger` | Bollinger Band method comparison (SMA vs EWMA) |
| 03 | `chronos_forecast` | Foundation model forecasting + calibration |
| 04 | `prophet_forecast` | Classical decomposition (documented failure) |
| 05 | `garch_volatility` | Volatility forecasting (standout finding) |
| 06 | `macro_data_collection` | FRED + BIS macro feature engineering |
| 07 | `xgboost_direction` | Tabular ML direction classification (documented failure) |
| 08 | `ets_arima_baselines` | Classical statistical baselines |
| 09 | `autogluon_comparison` | AutoML across all architectures |
| 10 | `conditional_evaluation` | Performance by regime (events, volatility) |
| 11 | `final_comparison` | Consolidated comparison and decision matrix |

---

## Methodology

- **Theil's U2** (RMSE ratio vs naive), applied consistently across all models
- **Walk-forward evaluation** (60-day rolling test) for valid out-of-sample comparison
- **Statistical significance testing** against both random (50%) and majority-class baselines
- **Prediction distribution analysis** to detect trivial trend-following
- **Calibration analysis** for probabilistic forecasts (interval coverage)
- **Conditional evaluation** by market regime

---

## Tech Stack

**Infrastructure:** AWS Lambda, S3, Glue, Athena, DynamoDB, EventBridge, SES
**Modeling:** Python 3.11, Chronos-Bolt, arch (GARCH), Prophet, XGBoost, AutoGluon-TimeSeries, StatsForecast
**Data:** Frankfurter API (ECB reference rates), FRED (US macro), BIS (foreign policy rates)
**Analysis:** pandas, numpy, matplotlib, scikit-learn, scipy

---

## Reproducing Locally

```bash
git clone https://github.com/ninadparab/fx-advisor.git
cd fx-advisor
py -3.11 -m venv .venv
.\.venv\Scripts\Activate     # Windows PowerShell
pip install -r requirements.txt
python -m ipykernel install --user --name=fx-advisor
```

Notebooks read from the deployed AWS pipeline via Athena. To run without AWS access, the EDA notebooks can be pointed at the raw data exports in `data/`.
