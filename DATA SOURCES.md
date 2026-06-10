# Data Sources

All data used in this project, with provenance and access methods. Reproducibility and traceable sourcing are treated as first-class requirements.

---

## FX Rates (target variable)

**Source:** Frankfurter API — https://www.frankfurter.app/
**What:** Daily USD exchange rates vs INR, EUR, GBP, MXN, PHP
**Underlying data:** European Central Bank (ECB) reference rates
**Cost:** Free, no authentication
**Frequency:** Daily (business days only — no weekend/holiday data)
**Access:** Direct HTTP GET via Lambda (`fx-fetch-rates`), with a User-Agent header (the API blocks default urllib)
**History:** ~400 days backfilled via a separate `fx-backfill-rates` Lambda

Note: ECB reference rates are published once per business day (~16:00 CET). They are reference rates, not tradeable rates, so they differ slightly from live market quotes but are consistent and free.

---

## US Macro Indicators

**Source:** FRED (Federal Reserve Economic Data) — https://fred.stlouisfed.org/
**Access:** `fredapi` Python package, free API key (instant registration)
**Frequency:** Mostly daily; CPI is monthly

| FRED Series ID | Variable | Frequency |
|---|---|---|
| DFF | Federal Funds Rate | Daily |
| DGS2 | US 2-Year Treasury Yield | Daily (business) |
| DGS10 | US 10-Year Treasury Yield | Daily (business) |
| VIXCLS | VIX Volatility Index | Daily (business) |
| DTWEXBGS | Trade-Weighted USD Index (Broad) | Daily (business) |
| CPIAUCSL | US CPI (all items) | Monthly |
| T10Y2Y | 10Y-2Y Treasury Spread | Daily (business) |

Note: US CPI was dropped from the feature set for daily modeling — at monthly frequency it had ~98% NaN when aligned to daily data, providing no usable signal.

---

## Foreign Central Bank Policy Rates

**Source:** BIS Policy Rates Dataset — https://data.bis.org/topics/CBPOL
**Access:** BIS Stats API (CSV format), free, no authentication
**Frequency:** Monthly (rates change only at policy meetings)

| Country | BIS Code | API Endpoint |
|---|---|---|
| India | IN | `WS_CBPOL/1.0/M.IN?format=csv` |
| Mexico | MX | `WS_CBPOL/1.0/M.MX?format=csv` |
| Philippines | PH | `WS_CBPOL/1.0/M.PH?format=csv` |
| UK | GB | `WS_CBPOL/1.0/M.GB?format=csv` |
| Eurozone | XM | `WS_CBPOL/1.0/M.XM?format=csv` |

**Why BIS instead of FRED:** FRED's coverage of foreign policy rates is incomplete or discontinued — UK, India, and Mexico all returned 0 observations. The BIS Policy Rates Dataset is the authoritative international source, covering 38 central banks and updated within 24 hours of each decision.

Forward-filled to business days, since policy rates persist between meetings. India data was backfilled at the start (BIS publishes with a slight lag).

---

## Central Bank Meeting Dates

Compiled from official sources for event-window analysis. Stored in `infrastructure/central_bank_meetings.csv`.

| Central Bank | Source |
|---|---|
| FOMC (US) | federalreserve.gov/monetarypolicy/fomccalendars.htm |
| RBI (India) | rbi.org.in (FY26 schedule; Aug 2025 meeting rescheduled to Aug 6) |
| Bank of England | bankofengland.co.uk/monetary-policy/upcoming-mpc-dates |
| ECB (Eurozone) | ecb.europa.eu/press/calendars/mgcgc/html |
| Banxico (Mexico) | banxico.org.mx (partial; key dates user-verified) |
| BSP (Philippines) | bsp.gov.ph (partial; key dates user-verified) |

FOMC, RBI, BoE, and ECB dates are fully verified from official calendars. Banxico and BSP dates are partially verified — specific dates confirmed from official announcements, others flagged in the CSV source column for future verification.

---

## Data NOT Used (and why)

| Considered | Why excluded |
|---|---|
| Retail remittance flows | <1-2% of currency-specific daily FX volume; too small to move daily rates (tested and rejected hypothesis) |
| Survey-based economist consensus | Behind paywalls (Bloomberg, Reuters); market-implied data (yields) is a free real-time proxy |
| Foreign 2-year yields | Not freely available for emerging markets; would be the ideal forward-looking rate-expectation feature |
| Intraday/tick data | Out of scope; product operates on daily signals |

---

## Reproducibility Notes

- FX rates flow through the live AWS pipeline; notebooks read via Athena
- Macro features are regenerated in `06_macro_data_collection.ipynb` and cached to `macro_features.csv` and S3 (`s3://fx-rates-ninpar/macro/features.csv`)
- All API access is free-tier; a FRED API key is the only credential required for full reproduction