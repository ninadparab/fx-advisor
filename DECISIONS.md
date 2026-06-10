# Project Decisions & Findings Log

A running record of the key technical and analytical decisions made building the FX Transfer Advisor, with the evidence behind each. This is the "why" behind the code.

---

## Infrastructure

### Why AWS serverless (Lambda + Athena) over a provisioned server
The workload is tiny and bursty — fetch rates once a day, compute signals once a day. A serverless design costs essentially nothing at this scale (within free tier) and requires no server maintenance. Athena's pay-per-query model fits perfectly: a few cents per month for the volume involved.

### Why S3 + Glue + Athena instead of a database
The raw data is a daily JSON file — a natural fit for a data lake. S3 stores the files, Glue catalogs the schema, Athena queries them with SQL. This separates storage (cheap, durable) from compute (serverless, on-demand). DynamoDB is layered on top only as a fast serving layer for the computed signals.

### Single-line JSON requirement
Athena's JSON SerDe requires one JSON object per line. The fetch Lambda was changed from pretty-printed to single-line output after Athena failed to parse multi-line records.

### Explicit region in boto3 clients
Lambda functions must specify `region_name` explicitly (e.g., `boto3.client('s3', region_name='us-east-2')`) to avoid timeouts from region resolution.

### Cost lesson: SageMaker notebook instances
Left an `ml.t3.medium` notebook instance running for ~80 hours, costing ~$4. SageMaker notebook instances bill per hour while running regardless of use, unlike Lambda. Added auto-stop lifecycle configuration and tighter budget alarms. In production, idle-resource cost (Redshift, RDS, EMR) is one of the biggest cloud bill surprises.

---

## Signal Design

### EWMA over SMA for Bollinger Bands
For trending pairs, SMA-based Bollinger Bands get "stuck" — USD/INR showed HIGH signals on 71% of days with SMA (useless) vs 39% with EWMA (meaningful variation). EWMA adapts faster to regime changes and starts producing signals immediately rather than after a 90-day warmup. Signal agreement between methods is 68-86%, with disagreements concentrated during trend transitions where EWMA is more accurate.

Decision: use EWMA in production. The marginal added complexity is justified by signal quality.

---

## Forecasting Models

### Chronos-Bolt: the best honest predictor
- Direction accuracy 63.3% on USD/INR (p=0.026 vs random, 95% CI 51.7-75.0%)
- Does NOT beat the majority-class baseline (56.4%) at p<0.05 — honest caveat
- Well-calibrated: 80% prediction intervals contain the actual value 77-87% of the time
- Calibration is consistent across regimes (event/non-event, high/low vol)

Decision: deploy selectively for direction on USD/INR and USD/PHP only. Surface probability bands rather than binary calls.

### Prophet: documented failure
Theil U 2.1-3.7 across all pairs — 2-4x WORSE than the naive baseline. Root causes:
1. FX lacks the strong seasonality Prophet is designed for
2. Piecewise-linear trend overfits and over-extrapolates
3. Additive holiday model is too simplistic for FX events (the *surprise* matters, not the event)
4. Default `n_changepoints=25` uniformly spaced is wrong for FX, where shifts cluster around events
5. 13 months is insufficient data for Prophet's component estimation

Adding real central-bank event dates produced no statistically significant improvement. Prophet's 80% intervals contain truth only 38-52% of the time — overconfident AND wrong.

Decision: rejected. Documented as a portfolio finding on model-data fit.

### XGBoost: documented failure
No improvement over the majority-class baseline on any pair. On USD/INR, achieved 51.7% vs 61.7% from a trivial "always-up" predictor — a 10pp degradation. Diagnostics:
- Feature importance correctly identified Bollinger %B, rate differentials, momentum (theory matched)
- But correct features can't overcome a near-random problem with 165 training rows
- Class-weight balancing pushed the model away from the natural class distribution
- Cross-pair contamination (india_policy_rate as top feature for USD/EUR) indicated spurious fitting

Decision: rejected. Lesson: identifying the right features doesn't help when the prediction problem is fundamentally near-random at this data size.

### AutoARIMA / AutoETS: trivial trend-following
Initial results looked competitive (ARIMA 61.7% on INR, p=0.046 vs random). But prediction-distribution analysis revealed the truth: ARIMA predicted UP 98% of the time on USD/INR, 0% on USD/EUR — constant outputs, not predictions. The "accuracy" was just the proportion of UP days. None beat the majority baseline.

Decision: rejected as standalone models. The majority-baseline test correctly flagged the illusion.

### AutoGluon: AutoML validation
Tested 8+ architectures (TFT, Chronos2, ETS, Theta, LightGBM, ensembles). On multi-step (30-day) forecasting, all achieved Theil U 1.3-4.1 — worse than naive. Models systematically predicted mean-reversion while rates kept trending. TFT topped the single-step leaderboard but that reflected the trivial "tomorrow ≈ today" task, not real forecasting.

Decision: rejected. Confirms no AutoML architecture beats the hand-built stack. A meaningful negative result — the FX problem is fundamentally constrained, not waiting for the right model.

### GARCH: the standout finding
GARCH(1,1) with Student-t errors:
- 23-32% RMSE reduction vs naive across all pairs (Theil U 0.68-0.77)
- 56-82% reduction in high-volatility regimes (USD/GBP Theil U 0.18)
- Ties the harder historical-average baseline overall, but adapts to recent conditions
- USD/MXN exception: no high-vol improvement (likely Banxico intervention dampening volatility)

Decision: deploy for all pairs. This is the engine of the product's urgency signal.

---

## Methodology Corrections

### Proper Theil's U2
Early notebooks computed error ratios using MAE (rate prediction) and MSE (volatility). Theil's U2 is formally RMSE(model)/RMSE(naive). Corrected throughout:
- Rate prediction: small change (MAE and RMSE behave similarly for symmetric errors)
- Volatility (GARCH): MSE ratio of 0.48 became RMSE ratio of 0.70 — still a substantial ~30% improvement, but more honest than the "50% reduction" the MSE framing implied

### Majority-class baseline awareness
Direction accuracy must beat the majority class, not just 50%. USD/INR has 56.4% UP days, so a trivial always-up predictor scores 56.4%. This reframing revealed that no model significantly beats trivial trend-following — the honest, correct conclusion.

### Prediction distribution analysis
Checking *what* each model predicts (not just accuracy) exposed ARIMA's constant-output behavior. A model predicting UP 98% of the time isn't forecasting; it's following the trend.

---

## Macro Data

### Rate differentials: theoretically important, empirically slow
Daily-return correlations with rate differentials were near zero (|corr| < 0.04). But forward-return analysis showed the signal emerges at longer horizons:
- USD/GBP vs UK differential: +0.51 at 60-day forward returns
- USD/INR vs India differential: -0.39 at 60-day forward returns (forward premium puzzle)

The differential changes only at policy meetings (~8/year) and is otherwise static, so it can't explain daily moves. The carry trade operates over weeks/months, not days.

### Sign differences reveal market structure
USD/GBP, USD/MXN, USD/PHP follow textbook uncovered interest parity (positive correlation). USD/INR and USD/EUR show the "forward premium puzzle" (negative correlation) — high-yield currencies appreciating rather than depreciating. This aligns with INR being a managed currency (RBI intervention).

### Data sources
- US macro: FRED (comprehensive, free, daily)
- Foreign policy rates: BIS Policy Rates Dataset (FRED's foreign coverage was incomplete — UK/India/Mexico returned 0 observations)

---

## Conditional Findings

### Direction prediction improves around central bank events
- USD/INR: 63% all days -> 69% in event windows (+6pp)
- USD/PHP: 55% all days -> 69% in event windows (+14pp)
- Suggestive but not significant (n=13 per pair, p=0.13)
- EUR/GBP/MXN show decreased accuracy in event windows (consistent with them being managed/mean-reverting)

### GARCH excels exactly when needed
High-vol regime Theil U: 0.18 (GBP) to 0.72 (MXN). The model is most accurate precisely when volatility information is most actionable for the user's transfer-timing decision.

### Calibration is regime-invariant
Chronos 80% intervals achieve 73-89% coverage across all conditions — trustworthy regardless of market state.