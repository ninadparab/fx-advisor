# Dashboard Design

This project began with a product question: **what should we show someone who is about to transfer money?** This document translates the modeling analysis into concrete dashboard elements, and — just as importantly — records what we deliberately chose *not* to show, because the analysis didn't support it.

The honest framing throughout: we cannot reliably predict tomorrow's exact rate (no model beats the random walk — Meese-Rogoff). What we *can* do is tell the user where the rate sits in its recent range, how turbulent the market is right now, and — for two specific pairs — a calibrated probability of direction. The product's value is synthesis and timing, not crystal-ball prediction.

---

## The Three-Layer Logic

Every recommendation is built from three layers, each backed by a model that earned its place in testing:

| Layer | Question it answers | Model | Works for |
|---|---|---|---|
| Context | "Is this a good rate vs recently?" | Bollinger Bands (EWMA) | All pairs |
| Volatility | "Should I act now or can I wait?" | GARCH(1,1) | All pairs |
| Direction | "Which way is it likely to move?" | Chronos-Bolt | USD/INR, USD/PHP only |

The layers degrade gracefully: every pair gets context and volatility; only the two pairs with a validated directional edge get a direction signal.

---

## What the Dashboard Should Include

### 1. The headline recommendation (synthesized)

A single, plain-language call derived from the three layers. Examples:

- *"Rates are calm and near a 30-day low for USD/INR. A reasonable time to transfer — little urgency either way."*
- *"USD/MXN volatility is elevated. If you need to transfer soon, consider locking in now rather than waiting."*
- *"USD/INR is near the top of its recent range and an RBI meeting is in 2 days. Conditions are unusually uncertain — splitting your transfer may reduce timing risk."*

This is the one thing a non-expert user reads. Everything below supports it.

### 2. Historical rate chart with Bollinger Bands (all pairs)

The core visual. Shows:
- The rate line over the last 60-90 days
- EWMA Bollinger Bands (upper/lower) shaded
- A marker for "today" and where it sits in the band

This directly answers "is this a good rate?" without any prediction. It's descriptive, robust, and always honest. **Bollinger %B** (0 = bottom of range, 1 = top) can be shown as a simple gauge: LOW / TYPICAL / HIGH.

### 3. Volatility gauge (all pairs) — the urgency driver

The strongest finding in the project. Show current GARCH-forecast volatility vs its recent historical level, as a simple tier:

- **CALM** — flexible, safe to wait
- **NORMAL** — no strong timing pressure
- **ELEVATED** — consider acting sooner
- **HIGH** — lock in now if you need to transfer

This is backed by GARCH reducing volatility-forecast error 56-82% in exactly these high-volatility regimes — it's most reliable when it matters most. Add an "ELEVATED" tier (current vol > 1.2x historical) so meaningful build-ups surface before they hit the strict HIGH threshold.

### 4. Direction probability (USD/INR and USD/PHP only)

For the two pairs with a validated edge, show a **calibrated probability band**, never a binary call:

> *"~65% chance USD/INR rises over the next few days. Likely range: 95.1 - 95.8."*

Two design rules from the analysis:
- **Show the probability and the range, not a yes/no.** Chronos's intervals are well-calibrated (77-87% coverage), so the range is trustworthy; the point direction is not certain.
- **Elevate confidence around central bank meetings.** Direction accuracy on these pairs rises 6-14pp in the ±2-day window around FOMC/RBI/BSP meetings. Surface this as "confidence: elevated" during those windows.

For USD/EUR, USD/GBP, USD/MXN: **suppress the direction signal entirely.** No validated edge, and EUR calibration was poor. Showing it would be dishonest.

### 5. Central bank meeting countdown (all pairs)

A small "next relevant meeting: RBI in 2 days" indicator. It affects how much weight to put on direction and warns the user that volatility may spike. Pulls from the verified meeting calendar.

### 6. Dollar-cost-averaging suggestion (conditional)

When volatility is ELEVATED or HIGH and the user has flexibility, suggest splitting the transfer into 2-3 tranches over a week. This is the honest hedge when we can't predict direction: spreading the transfer reduces timing risk without pretending to know the future.

---

## What We Deliberately Left Out

Documenting the *absence* of features is as important as the features themselves — it's what keeps the product honest.

| Not included | Why |
|---|---|
| "Predicted rate tomorrow: X" | No model beats the naive random walk on rate level (Theil U ~1.0). A point prediction would imply false precision. |
| Direction calls for EUR/GBP/MXN | No statistically validated edge; EUR calibration was poor. |
| Binary "BUY NOW / WAIT" direction signal | Even where direction works, it's probabilistic. Binary calls overpromise. |
| Long-horizon (30-day) rate forecasts | Multi-step forecasting was Theil U 1.3-4.1 — far worse than naive. |
| "AI-powered prediction" marketing language | The honest product is about context, volatility, and timing — not prediction. |
| Confidence scores from XGBoost/Prophet | Both failed testing; their probabilities were miscalibrated. |

---

## Example Dashboard Layout (USD/INR)

```
+--------------------------------------------------------------+
|  USD -> INR                                    95.24 today    |
|                                                              |
|  "Near the top of the 30-day range, and an RBI meeting is    |
|   in 2 days. Conditions are uncertain — consider splitting   |
|   your transfer."                                            |
+--------------------------------------------------------------+
|  [ 90-day rate chart with EWMA Bollinger Bands ]             |
|  Position in range:  [====LOW====TYPICAL====[X]HIGH ]        |
+--------------------------------------------------------------+
|  Volatility:  ELEVATED    (1.26x recent average)            |
|  Direction:   ~58% chance up  |  range 94.9 - 95.7           |
|               confidence: ELEVATED (RBI meeting in 2 days)   |
|  Next event:  RBI, in 2 days                                 |
+--------------------------------------------------------------+
|  Suggested: split transfer into 2-3 parts this week          |
+--------------------------------------------------------------+
```

For USD/EUR the same layout appears **without** the Direction line — only context, volatility, and the meeting countdown.

---

## Why This Is the Right Product

The competitive insight: existing FX tools either show raw rates (no guidance) or make confident predictions they can't back up. This dashboard occupies the honest middle — it gives genuinely useful, statistically validated signals (where the rate sits, how volatile the market is, and a calibrated direction probability for two pairs) while refusing to fake the predictions that don't survive testing.

The volatility-driven urgency signal in particular is something most consumer FX tools don't provide, and it's backed by the project's most robust finding. "Knowing how much the rate will move" turns out to be more reliably useful than "knowing which way" — and it's exactly the information a person deciding *when* to transfer actually needs.