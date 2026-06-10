"""Signal generation — Bollinger Bands, GARCH volatility, direction signals.

Honest design principles:
- Bollinger: multi-window context, all pairs
- GARCH: volatility tier, all pairs (strongest signal in the project)
- Direction: ONLY USD/INR and USD/PHP (only pairs with validated edge)
"""
import numpy as np
import pandas as pd
from arch import arch_model
import streamlit as st

# Direction prediction only for pairs where analysis found statistical edge
DIRECTION_PAIRS = ['usd_inr', 'usd_php']

# Map each pair to relevant central banks for event awareness
EVENT_BANK_MAP = {
    'usd_inr': ['FOMC', 'RBI'],
    'usd_eur': ['FOMC', 'ECB'],
    'usd_gbp': ['FOMC', 'BOE'],
    'usd_mxn': ['FOMC', 'Banxico'],
    'usd_php': ['FOMC', 'BSP'],
}


# ============ BOLLINGER BANDS ============

def compute_bollinger_signal(rate_series, window=30, n_std=2):
    """EWMA Bollinger Bands for a single window.
    
    Returns dict with position info, raw values, and full band series for plotting.
    Falls back when Lambda hasn't computed the pair's signals yet.
    """
    ewma_mean = rate_series.ewm(span=window).mean()
    ewma_std = rate_series.ewm(span=window).std()
    upper = ewma_mean + n_std * ewma_std
    lower = ewma_mean - n_std * ewma_std
    
    pct_b = (rate_series - lower) / (upper - lower)
    current_pct_b = pct_b.iloc[-1]
    
    if current_pct_b > 0.8:
        position = "HIGH"
        description = "Near the top of the recent range"
    elif current_pct_b < 0.2:
        position = "LOW"
        description = "Near the bottom of the recent range"
    else:
        position = "TYPICAL"
        description = "Within typical recent range"
    
    return {
        'position': position,
        'description': description,
        'pct_b': float(current_pct_b),
        'current': float(rate_series.iloc[-1]),
        'upper_band': float(upper.iloc[-1]),
        'lower_band': float(lower.iloc[-1]),
        'mid_band': float(ewma_mean.iloc[-1]),
        'upper_series': upper,
        'lower_series': lower,
        'mid_series': ewma_mean,
        'window': window
    }


def get_bollinger_from_signal(signal_dict, pair):
    """Extract multi-window Bollinger info from DynamoDB-stored signal.
    
    Uses precomputed Lambda output — covers 7d/30d/90d/1y windows.
    Returns None if signal isn't available for this pair.
    """
    if not signal_dict:
        return None
    
    return {
        'windows': {
            '7d':  {'signal': signal_dict.get('signal_7d'),  'pct_b': signal_dict.get('pb_7d')},
            '30d': {'signal': signal_dict.get('signal_30d'), 'pct_b': signal_dict.get('pb_30d')},
            '90d': {'signal': signal_dict.get('signal_90d'), 'pct_b': signal_dict.get('pb_90d')},
            '1y':  {'signal': signal_dict.get('signal_1y'),  'pct_b': signal_dict.get('pb_1y')},
        },
        'current': signal_dict.get(pair),  # stored under pair name in lowercase
        'date': signal_dict.get('date'),
        'updated_at': signal_dict.get('updated_at')
    }


# ============ GARCH VOLATILITY ============

@st.cache_data(ttl=3600)
def compute_garch_signal(rate_series_values, dates):
    """GARCH(1,1) Student-t volatility forecast.
    
    Takes values + dates separately so Streamlit can cache the result.
    Returns volatility tier, next-day forecast, and 5-day average.
    """
    series = pd.Series(rate_series_values, index=pd.to_datetime(dates))
    returns = series.pct_change().dropna() * 100  # percent
    
    try:
        model = arch_model(returns, vol='GARCH', p=1, q=1, dist='t')
        fit = model.fit(disp='off', show_warning=False)
        
        # Next-day forecast
        forecast_1d = fit.forecast(horizon=1, reindex=False)
        next_vol = float(np.sqrt(forecast_1d.variance.values[-1, 0]))
        
        # 5-day average forecast
        forecast_5d = fit.forecast(horizon=5, reindex=False)
        avg_5d_vol = float(np.sqrt(forecast_5d.variance.values[-1, :].mean()))
        
        # Compare to historical
        historical_vol = float(returns.std())
        ratio = next_vol / historical_vol
        
        # Tier categorization (added ELEVATED tier per analysis findings)
        if ratio > 1.5:
            tier = "HIGH"
            advice = "Markets are turbulent. Consider locking in your rate now if you need to transfer."
            color = "#D32F2F"  # red
        elif ratio > 1.2:
            tier = "ELEVATED"
            advice = "Volatility is rising. If timing matters, lean toward acting sooner."
            color = "#F57C00"  # orange
        elif ratio < 0.7:
            tier = "CALM"
            advice = "Markets are calm. You have flexibility to wait if you choose."
            color = "#388E3C"  # green
        else:
            tier = "NORMAL"
            advice = "Volatility is in a normal range. No strong timing pressure either way."
            color = "#1976D2"  # blue
        
        return {
            'tier': tier,
            'advice': advice,
            'color': color,
            'next_vol': next_vol,
            'historical_vol': historical_vol,
            'ratio': ratio,
            'avg_5d_vol': avg_5d_vol,
            'success': True
        }
    except Exception as e:
        return {
            'tier': 'UNKNOWN',
            'advice': 'Could not compute volatility forecast for this period.',
            'color': '#9E9E9E',
            'next_vol': None,
            'historical_vol': None,
            'ratio': None,
            'avg_5d_vol': None,
            'success': False,
            'error': str(e)
        }


# ============ DIRECTION (selective by pair) ============

def can_show_direction(pair):
    """Returns True only for pairs where analysis found a validated direction edge."""
    return pair in DIRECTION_PAIRS


def direction_caveat(pair):
    """Honest explanation of why direction is/isn't shown for this pair."""
    if pair in DIRECTION_PAIRS:
        return (
            f"Direction prediction available for {pair.upper()}. "
            "Backed by Chronos-Bolt foundation model achieving 63% direction accuracy "
            "on USD/INR (statistically significant vs random, p=0.026) and 55% on USD/PHP, "
            "with well-calibrated probability intervals (77-87% coverage)."
        )
    else:
        return (
            f"Direction prediction is **not** shown for {pair.upper()}. "
            "Our analysis tested 7+ forecasting approaches (Chronos, Prophet, GARCH, XGBoost, "
            "AutoARIMA, AutoETS, AutoGluon ensembles) and found no statistically validated "
            "directional edge for this pair. Showing a direction signal here would be dishonest."
        )


# ============ EVENT AWARENESS ============

def days_to_next_event(pair, events_df, today=None):
    """Days until the next central bank meeting relevant to this pair.
    
    Returns (days, bank_name) tuple, or (None, None) if no upcoming events found.
    """
    if events_df.empty:
        return None, None
    
    if today is None:
        today = pd.Timestamp.today().normalize()
    
    relevant_banks = EVENT_BANK_MAP.get(pair, [])
    relevant_events = events_df[events_df['central_bank'].isin(relevant_banks)]
    future_events = relevant_events[relevant_events['date'] >= today].sort_values('date')
    
    if future_events.empty:
        return None, None
    
    next_event = future_events.iloc[0]
    days = (next_event['date'] - today).days
    return days, next_event['central_bank']


def get_visible_events(pair, events_df, start_date, end_date):
    """All relevant central bank events within a given date range (for chart overlays)."""
    if events_df.empty:
        return pd.DataFrame()
    
    relevant_banks = EVENT_BANK_MAP.get(pair, [])
    in_range = events_df[
        (events_df['date'] >= start_date) &
        (events_df['date'] <= end_date) &
        (events_df['central_bank'].isin(relevant_banks))
    ]
    return in_range


# ============ SYNTHESIZED RECOMMENDATION ============

def synthesize_recommendation(boll_position, vol_tier, days_to_event, has_direction):
    """Build a single plain-language recommendation from all three layers.
    
    This is the headline a non-expert user reads.
    """
    parts = []
    
    # Volatility drives urgency framing
    if vol_tier == "HIGH":
        urgency = "Markets are turbulent right now."
    elif vol_tier == "ELEVATED":
        urgency = "Volatility is rising."
    elif vol_tier == "CALM":
        urgency = "Markets are calm."
    else:
        urgency = ""
    
    # Position adds context
    if boll_position == "HIGH":
        context = "The rate is near the top of its recent range"
    elif boll_position == "LOW":
        context = "The rate is near the bottom of its recent range"
    else:
        context = "The rate is in a typical recent range"
    
    # Event proximity adds caveat
    event_note = ""
    if days_to_event is not None and days_to_event <= 2:
        event_note = " A central bank meeting is imminent — expect potential volatility."
    elif days_to_event is not None and days_to_event <= 5:
        event_note = " A central bank meeting is approaching."
    
    # Combine
    sentence = f"{context}. {urgency}{event_note}"
    
    # Add timing advice based on volatility
    if vol_tier == "HIGH":
        advice = "If you need to transfer soon, consider locking in your rate now or splitting the transfer."
    elif vol_tier == "ELEVATED":
        advice = "Consider acting sooner rather than later if timing flexibility is limited."
    elif vol_tier == "CALM" and boll_position == "LOW":
        advice = "Conditions are favorable for transferring now."
    elif vol_tier == "CALM":
        advice = "You have flexibility to wait for a better rate if you choose."
    else:
        advice = "No strong timing pressure either way."
    
    return f"{sentence} {advice}"