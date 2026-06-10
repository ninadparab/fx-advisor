"""FX Transfer Advisor — Streamlit Dashboard.

Honest, statistically-validated signals for people transferring money internationally.
Backed by 11 notebooks of rigorous analysis. See github.com/ninadparab/fx-advisor.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from data_access import (
    load_fx_history,
    load_latest_signals,
    load_central_bank_events,
    credentials_configured
)
from signals import (
    compute_bollinger_signal,
    compute_garch_signal,
    get_bollinger_from_signal,
    can_show_direction,
    direction_caveat,
    days_to_next_event,
    get_visible_events,
    synthesize_recommendation,
    EVENT_BANK_MAP
)


# ============ PAGE CONFIG ============

st.set_page_config(
    page_title="FX Advisor",
    page_icon="💱",
    layout="wide",
    initial_sidebar_state="expanded"
)

PAIRS = {
    'usd_inr': 'USD → INR  (India)',
    'usd_eur': 'USD → EUR  (Eurozone)',
    'usd_gbp': 'USD → GBP  (UK)',
    'usd_mxn': 'USD → MXN  (Mexico)',
    'usd_php': 'USD → PHP  (Philippines)'
}


# ============ SIDEBAR ============

st.sidebar.title("💱 FX Advisor")
st.sidebar.markdown("---")

selected_pair = st.sidebar.selectbox(
    "Currency pair",
    options=list(PAIRS.keys()),
    format_func=lambda x: PAIRS[x],
    index=0
)

history_days = st.sidebar.slider("Chart history (days)", 30, 180, 90)

st.sidebar.markdown("---")
st.sidebar.caption(
    "**About this dashboard**\n\n"
    "Three honest signals for transfer timing:\n"
    "- **Context** — where the rate sits vs recent range\n"
    "- **Volatility** — how turbulent the market is\n"
    "- **Direction** — calibrated probability (only where statistically validated)\n\n"
    "Built on rigorous testing of 7+ forecasting models. "
    "[Repo](https://github.com/ninadparab/fx-advisor)"
)


# ============ CREDENTIAL CHECK ============

if not credentials_configured():
    st.error(
        "**AWS credentials not configured.** "
        "This dashboard reads live data from AWS Athena and DynamoDB and requires credentials to work."
    )
    st.markdown(
        """
        **For Streamlit Cloud deployment:**
        1. Click the three-dot menu in the upper right of your app
        2. Select **Settings → Secrets**
        3. Paste the following (replacing with your IAM user's credentials):
        
        ```toml
        [aws]
        access_key_id = "AKIA..."
        secret_access_key = "your_secret_here"
        region = "us-east-2"
        ```
        
        4. Click **Save**. The app will restart automatically.
        
        **IAM permissions needed:** AmazonAthenaFullAccess, AmazonS3ReadOnlyAccess, AmazonDynamoDBReadOnlyAccess
        
        **For local development:** Run `aws configure` in your terminal.
        """
    )
    st.stop()


# ============ LOAD DATA ============

try:
    with st.spinner("Loading FX data..."):
        df = load_fx_history(days=max(history_days + 60, 250))
        signals = load_latest_signals()
        events = load_central_bank_events()
except Exception as e:
    st.error(f"**Data loading failed.**\n\n```\n{str(e)}\n```")
    st.markdown(
        "Common causes:\n"
        "- IAM user missing `s3:PutObject` on `s3://fx-rates-ninpar/athena-results/`\n"
        "- IAM user missing Glue Data Catalog permissions (`AWSGlueConsoleFullAccess`)\n"
        "- The `fx_rates_db.usd` table doesn't exist in the configured region\n"
        "- Athena workgroup permissions"
    )
    st.stop()

rate_series = df[selected_pair].dropna()


# ============ COMPUTE SIGNALS ============

# Bollinger: use Lambda's multi-window precomputed signals where available
lambda_signal = signals.get(selected_pair)
boll_multi = get_bollinger_from_signal(lambda_signal, selected_pair) if lambda_signal else None
boll_live = compute_bollinger_signal(rate_series, window=30)

# GARCH: always live (Lambda doesn't compute volatility yet)
garch = compute_garch_signal(rate_series.values, rate_series.index)

# Event awareness
days_event, event_bank = days_to_next_event(selected_pair, events)


# ============ HEADER ============

st.title(PAIRS[selected_pair])

# Top metrics row
col1, col2, col3, col4 = st.columns(4)

current_rate = float(rate_series.iloc[-1])
yesterday_rate = float(rate_series.iloc[-2])
daily_change = current_rate - yesterday_rate
daily_change_pct = (daily_change / yesterday_rate) * 100

with col1:
    st.metric(
        label="Current rate",
        value=f"{current_rate:.4f}",
        delta=f"{daily_change:+.4f} ({daily_change_pct:+.2f}%)"
    )

with col2:
    st.metric("Position in range", boll_live['position'])

with col3:
    st.metric("Volatility", garch['tier'])

with col4:
    if days_event is not None:
        st.metric("Next event", f"{event_bank} in {days_event}d")
    else:
        st.metric("Next event", "None scheduled")


# ============ HEADLINE RECOMMENDATION ============

st.markdown("---")
recommendation = synthesize_recommendation(
    boll_live['position'],
    garch['tier'],
    days_event,
    can_show_direction(selected_pair)
)

# Style by volatility tier
if garch['tier'] == "HIGH":
    st.error(f"**Recommendation:** {recommendation}")
elif garch['tier'] == "ELEVATED":
    st.warning(f"**Recommendation:** {recommendation}")
elif garch['tier'] == "CALM":
    st.success(f"**Recommendation:** {recommendation}")
else:
    st.info(f"**Recommendation:** {recommendation}")


# ============ MAIN CHART: Rate + Bollinger Bands + Events ============

st.markdown("---")
st.subheader("Rate history")

plot_series = rate_series.iloc[-history_days:]

# Build the chart
fig = go.Figure()

# Bollinger upper band (transparent line)
fig.add_trace(go.Scatter(
    x=boll_live['upper_series'].iloc[-history_days:].index,
    y=boll_live['upper_series'].iloc[-history_days:].values,
    line=dict(color='rgba(33,150,243,0.0)', width=0),
    showlegend=False,
    hoverinfo='skip'
))

# Bollinger lower band (fills up to upper)
fig.add_trace(go.Scatter(
    x=boll_live['lower_series'].iloc[-history_days:].index,
    y=boll_live['lower_series'].iloc[-history_days:].values,
    line=dict(color='rgba(33,150,243,0.0)', width=0),
    fill='tonexty',
    fillcolor='rgba(33,150,243,0.12)',
    name='Bollinger Band (±2σ)',
    hoverinfo='skip'
))

# EWMA mean (dashed)
fig.add_trace(go.Scatter(
    x=boll_live['mid_series'].iloc[-history_days:].index,
    y=boll_live['mid_series'].iloc[-history_days:].values,
    line=dict(color='rgba(33,150,243,0.6)', width=1, dash='dash'),
    name='30-day average'
))

# Actual rate
fig.add_trace(go.Scatter(
    x=plot_series.index,
    y=plot_series.values,
    line=dict(color='#212121', width=2.5),
    name='Rate',
    hovertemplate='%{x|%Y-%m-%d}<br>Rate: %{y:.4f}<extra></extra>'
))

# Mark relevant central bank events
visible_events = get_visible_events(
    selected_pair,
    events,
    plot_series.index[0],
    plot_series.index[-1]
)

for _, row in visible_events.iterrows():
    fig.add_vline(
        x=row['date'],
        line=dict(color='#D32F2F', width=1, dash='dot'),
        opacity=0.4
    )

# Highlight today
fig.add_vline(
    x=plot_series.index[-1],
    line=dict(color='#2E7D32', width=1),
    opacity=0.5
)

fig.update_layout(
    height=420,
    margin=dict(l=20, r=20, t=20, b=20),
    hovermode='x unified',
    yaxis_title='Rate',
    xaxis_title=None,
    legend=dict(orientation='h', y=-0.12, x=0)
)

st.plotly_chart(fig, use_container_width=True)

cap = "Blue shaded area: 2σ Bollinger Band (EWMA, 30-day)."
if not visible_events.empty:
    cap += " Red dotted lines mark central bank meetings relevant to this pair."
cap += " Green line marks today."
st.caption(cap)


# ============ MULTI-WINDOW CONTEXT ============

st.markdown("---")
st.subheader("Where does today's rate sit?")

if boll_multi:
    # Use Lambda's precomputed multi-window signals (richer)
    st.caption(
        f"From the production pipeline — daily computation completed "
        f"{boll_multi['updated_at'][:10] if boll_multi.get('updated_at') else 'recently'}"
    )
    
    win_cols = st.columns(4)
    for i, (window_name, win_data) in enumerate(boll_multi['windows'].items()):
        signal = win_data.get('signal')
        pct_b = win_data.get('pct_b')
        
        if signal and pct_b is not None:
            window_labels = {'7d': '7 days', '30d': '30 days', '90d': '90 days', '1y': '1 year'}
            with win_cols[i]:
                st.metric(
                    label=f"vs {window_labels[window_name]}",
                    value=signal,
                    delta=f"%B = {pct_b:.2f}",
                    delta_color="off"
                )
    
    st.caption(
        "Multiple time horizons give richer context. A rate can be LOW vs last week but "
        "HIGH vs the past year — both true, both relevant for transfer decisions."
    )
else:
    # Fall back to live single-window
    st.info(
        f"Lambda hasn't precomputed signals for {selected_pair.upper()} yet — "
        f"showing live 30-day Bollinger computation."
    )
    
    g_col1, g_col2, g_col3 = st.columns(3)
    g_col1.metric("Lower band", f"{boll_live['lower_band']:.4f}")
    g_col2.metric("Current", f"{boll_live['current']:.4f}")
    g_col3.metric("Upper band", f"{boll_live['upper_band']:.4f}")

# Position gauge
gauge_value = (boll_multi['windows']['30d']['pct_b'] * 100) if boll_multi else (boll_live['pct_b'] * 100)

fig_gauge = go.Figure(go.Indicator(
    mode="gauge+number",
    value=gauge_value,
    domain={'x': [0, 1], 'y': [0, 1]},
    title={'text': "Position in 30-day range (%)", 'font': {'size': 14}},
    gauge={
        'axis': {'range': [0, 100], 'ticksuffix': '%', 'tickfont': {'size': 11}},
        'bar': {'color': "#1A237E", 'thickness': 0.25},
        'steps': [
            {'range': [0, 20], 'color': "#A5D6A7"},      # LOW (green)
            {'range': [20, 80], 'color': "#FFF59D"},     # TYPICAL (yellow)
            {'range': [80, 100], 'color': "#EF9A9A"}     # HIGH (red)
        ],
        'threshold': {
            'line': {'color': "black", 'width': 3},
            'thickness': 0.7,
            'value': gauge_value
        }
    },
    number={'font': {'size': 28}}
))
fig_gauge.update_layout(height=250, margin=dict(l=20, r=20, t=40, b=20))
st.plotly_chart(fig_gauge, use_container_width=True)


# ============ VOLATILITY DETAIL ============

st.markdown("---")
st.subheader("Volatility forecast")

st.markdown(
    f"<div style='padding: 12px; border-left: 4px solid {garch['color']}; "
    f"background-color: rgba(0,0,0,0.02); border-radius: 4px;'>"
    f"<strong>{garch['tier']}</strong>: {garch['advice']}"
    f"</div>",
    unsafe_allow_html=True
)

st.write("")  # spacer

v_col1, v_col2, v_col3 = st.columns(3)

if garch['success']:
    v_col1.metric("Next-day forecast", f"{garch['next_vol']:.3f}%")
    v_col2.metric("5-day average", f"{garch['avg_5d_vol']:.3f}%")
    v_col3.metric("vs historical avg", f"{garch['ratio']:.2f}x",
                  delta=f"{(garch['ratio']-1)*100:+.0f}%",
                  delta_color="off")

    st.caption(
        "GARCH(1,1) with Student-t errors. This is the project's strongest finding: "
        "23-32% lower forecast error than the naive baseline overall, and 56-82% lower "
        "in high-volatility regimes — most reliable exactly when it matters most."
    )
else:
    st.warning("Could not compute volatility — insufficient data window for this pair.")


# ============ DIRECTION SIGNAL (selective) ============

st.markdown("---")
st.subheader("Direction signal")

if can_show_direction(selected_pair):
    confidence = "ELEVATED" if (days_event is not None and days_event <= 2) else "NORMAL"
    
    if confidence == "ELEVATED":
        st.success(
            f"✅ Direction prediction available. "
            f"Confidence: **{confidence}** (central bank meeting in {days_event} days — "
            f"analysis found accuracy improves 6-14 percentage points in event windows)"
        )
    else:
        st.success(
            f"✅ Direction prediction available. Confidence: **{confidence}**"
        )
    
    st.caption(direction_caveat(selected_pair))
    
    st.info(
        "**Implementation note**: Live Chronos-Bolt direction probabilities would be "
        "displayed here in production. The model is loaded by the daily `fx-compute-signal` "
        "Lambda; surfacing live predictions in the dashboard requires either the Lambda "
        "to also write directional signals to DynamoDB, or for the dashboard to run "
        "Chronos inference on-demand (adds ~5s per page load)."
    )
    
    # Placeholder for the actual Chronos signal
    st.markdown(
        "**Format**: probability bands rather than binary calls. "
        "Example: *\"~65% chance USD/INR rises over the next few days. Likely range: 95.1 - 95.8.\"*"
    )
else:
    st.warning(
        f"⚠️ Direction prediction is **not** available for {PAIRS[selected_pair]}."
    )
    st.caption(direction_caveat(selected_pair))


# ============ FOOTER ============

st.markdown("---")
st.caption(
    "Built with Streamlit and AWS (Lambda + S3 + Athena + DynamoDB + EventBridge + SES). "
    "Analysis backed by 11 notebooks of rigorous testing including proper Theil's U2, "
    "statistical significance vs majority-class baselines, prediction distribution analysis, "
    "and calibration analysis across market regimes. "
    "[GitHub](https://github.com/ninadparab/fx-advisor) · "
    "[Dashboard design rationale](https://github.com/ninadparab/fx-advisor/blob/main/DASHBOARD.md)"
)