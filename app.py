from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

st.set_page_config(page_title="FNO Intelligence Terminal", layout="wide")

try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_AVAILABLE = True
except ImportError:
    AUTOREFRESH_AVAILABLE = False

st.markdown("""
<style>
div[data-baseweb="popover"] { background: #000000 !important; }
div[data-baseweb="popover"] * { background-color: #000000 !important; color: #ffffff !important; -webkit-text-fill-color: #ffffff !important; }
div[data-baseweb="menu"] { background: #000000 !important; }
div[data-baseweb="menu"] * { background-color: #000000 !important; color: #ffffff !important; -webkit-text-fill-color: #ffffff !important; }
ul[role="listbox"] { background: #000000 !important; }
ul[role="listbox"] * { background-color: #000000 !important; color: #ffffff !important; -webkit-text-fill-color: #ffffff !important; }
li[role="option"] { background: #000000 !important; color: #ffffff !important; }
li[role="option"]:hover { background: #1a1a2e !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div style="
    background: linear-gradient(90deg, #0d1117, #0f1a2e, #0d1117);
    border-bottom: 1px solid rgba(57,164,255,0.25);
    padding: 10px 20px;
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 12px;
">
    <span style="font-size:22px;">📊</span>
    <span style="
        font-size: 22px;
        font-weight: 900;
        letter-spacing: 0.06em;
        background: linear-gradient(90deg, #39a4ff, #b46cff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    ">FnO Intelligence Terminal</span>
    <span style="
        margin-left: auto;
        font-size: 11px;
        color: #99a1ab;
        font-weight: 600;
        letter-spacing: 0.05em;
    ">LIVE · NSE/BSE · INDIA VIX</span>
</div>
""", unsafe_allow_html=True)

INDIA_VIX_QUOTE_KEY = "NSE_INDEX|India VIX"
INDIA_VIX_DATA_KEY = "NSE_INDEX:India VIX"

INSTRUMENTS = {
    "NIFTY": {
        "display_name": "NIFTY",
        "quote_key": "NSE_INDEX|Nifty 50",
        "quote_data_key": "NSE_INDEX:Nifty 50",
        "option_key": "NSE_INDEX|Nifty 50",
        "history_key": "NSE_INDEX|Nifty 50",
    },
    "SENSEX": {
        "display_name": "SENSEX",
        "quote_key": "BSE_INDEX|SENSEX",
        "quote_data_key": "BSE_INDEX:SENSEX",
        "option_key": "BSE_INDEX|SENSEX",
        "history_key": "BSE_INDEX|SENSEX",
    },
    "BANKNIFTY": {
        "display_name": "BANKNIFTY",
        "quote_key": "NSE_INDEX|Nifty Bank",
        "quote_data_key": "NSE_INDEX:Nifty Bank",
        "option_key": "NSE_INDEX|Nifty Bank",
        "history_key": "NSE_INDEX|Nifty Bank",
    },
    "FINNIFTY": {
        "display_name": "FINNIFTY",
        "quote_key": "NSE_INDEX|Nifty Fin Service",
        "quote_data_key": "NSE_INDEX:Nifty Fin Service",
        "option_key": "NSE_INDEX|Nifty Fin Service",
        "history_key": "NSE_INDEX|Nifty Fin Service",
    },
    "MIDCPNIFTY": {
        "display_name": "MIDCPNIFTY",
        "quote_key": "NSE_INDEX|NIFTY MID SELECT",
        "quote_data_key": "NSE_INDEX:NIFTY MID SELECT",
        "option_key": "NSE_INDEX|NIFTY MID SELECT",
        "history_key": "NSE_INDEX|NIFTY MID SELECT",
    },
}

RED = "#ff4d4f"
GREEN = "#20e27a"
PURPLE = "#b46cff"
YELLOW = "#f4c542"
BLUE = "#39a4ff"
ORANGE = "#ff9f43"
BG = "#0c0d0f"
GRID = "rgba(255,255,255,0.08)"
BORDER = "rgba(255,255,255,0.09)"
TEXT = "#f5f7fa"
MUTED = "#99a1ab"
SELECT_BORDER = "#2a74b8"
IST = ZoneInfo("Asia/Kolkata")


def get_secret(name, default=None):
    return st.secrets[name] if name in st.secrets else default


ACCESS_TOKEN = get_secret("ACCESS_TOKEN", "")
TG_BOT_TOKEN = get_secret("TG_BOT_TOKEN", "")
TG_CHAT_ID = get_secret("TG_CHAT_ID", "")
REFRESH_RATE = int(get_secret("REFRESH_RATE", 10))


def get_default_expiry():
    today = datetime.now(IST).date()
    days_ahead = (3 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    candidate = today + timedelta(days=days_ahead)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return str(candidate)


DEFAULT_EXPIRY_DATE = get_secret("DEFAULT_EXPIRY_DATE") or get_default_expiry()

for key, default in {
    "pcr_history": [],
    "vix_history": [],
    "buildup_history": [],
    "last_reported_minute": None,
    "prev_vix": None,
    "prev_spot": None,
    "last_signal": "AI SCANNING...",
    "last_reason": "Waiting for data...",
    "last_status": ("SYSTEM READY - SELECT SYMBOL AND EXPIRY", "info"),
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

st.markdown(
    f"""
    <style>
    .stApp {{background:{BG}; color:{TEXT};}}
    .block-container {{padding-top:0.65rem; padding-bottom:0.5rem; max-width:100%;}}
    h1, h2, h3, h4, h5, h6, p, div, span, label {{color:{TEXT};}}
    [data-testid="stHeader"] {{background:transparent;}}
    [data-testid="stToolbar"] {{right:0.8rem;}}

    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {{
        display: flex !important;
        align-items: stretch !important;
    }}
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] > div {{
        width: 100% !important;
        display: flex !important;
        align-items: center !important;
    }}
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] [data-testid="stSelectbox"] {{
        width: 100% !important;
    }}
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] [data-baseweb="select"] {{
        width: 100% !important;
    }}
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] div[data-baseweb="select"] > div {{
        min-height: 62px !important;
        height: 62px !important;
    }}

    .top-shell {{
        background: linear-gradient(90deg,#1a1c20,#1d1e21);
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 10px 14px;
        height: 62px;
        min-height: 62px;
        display: flex;
        align-items: center;
        width: 100%;
        box-sizing: border-box;
        margin-bottom: 0px;
    }}

    div[data-baseweb="select"] > div {{
        background-color: #000000 !important;
        background: #000000 !important;
        border: 1px solid {SELECT_BORDER} !important;
        box-shadow: none !important;
        min-height: 62px !important;
        height: 62px !important;
        border-radius: 8px !important;
        display: flex !important;
        align-items: center !important;
    }}

    div[data-baseweb="select"] > div > div {{
        display: flex !important;
        align-items: center !important;
        height: 100% !important;
    }}

    div[data-baseweb="select"] *,
    div[data-baseweb="select"] > div,
    div[data-baseweb="select"] > div > div,
    div[data-baseweb="select"] > div > div > div {{
        background-color: #000000 !important;
        background: #000000 !important;
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
    }}

    div[data-baseweb="select"] svg {{
        fill: #ffffff !important;
    }}

    div[data-baseweb="select"] input {{
        background-color: #000000 !important;
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
        caret-color: #ffffff !important;
    }}

    div[data-baseweb="popover"],
    div[data-baseweb="menu"],
    ul[role="listbox"] {{
        background-color: #000000 !important;
        background: #000000 !important;
        border: 1px solid {SELECT_BORDER} !important;
        color: #ffffff !important;
    }}

    div[data-baseweb="popover"] *,
    div[data-baseweb="menu"] *,
    ul[role="listbox"] * {{
        background-color: #000000 !important;
        background: #000000 !important;
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
    }}

    div[data-baseweb="menu"] [role="option"]:hover,
    ul[role="listbox"] > li:hover {{
        background-color: #1a1a2e !important;
        background: #1a1a2e !important;
    }}

    div[data-baseweb="menu"] [role="option"][aria-selected="true"],
    ul[role="listbox"] > li[aria-selected="true"] {{
        background-color: #1d5f99 !important;
        background: #1d5f99 !important;
    }}

    .metric-inline {{font-size:13px; font-weight:800; white-space:nowrap;}}
    .metric-blue {{color:{BLUE};}}
    .metric-purple {{color:{PURPLE};}}
    .metric-yellow {{color:{YELLOW};}}
    .market-closed-banner {{background:#1a1a2e; border:1px solid #2a74b8; color:{BLUE}; padding:12px 18px; border-radius:8px; font-size:16px; font-weight:800; text-align:center; margin-bottom:12px;}}
    .status-banner {{background:#c93c2a; color:white; padding:12px 18px; border-radius:8px; font-size:18px; font-weight:900; text-align:center; margin-bottom:12px; letter-spacing:0.02em;}}
    .panel {{background:#0f1012; border:1px solid {BORDER}; border-radius:8px; padding:8px;}}
    .mini-card {{background:#141518; border:1px solid {BORDER}; border-radius:8px; padding:16px 12px; text-align:center; margin-bottom:14px; min-height:84px; display:flex; flex-direction:column; justify-content:center;}}
    .mini-title {{font-size:11px; font-weight:800; margin-bottom:8px;}}
    .mini-red {{color:#f25d52;}}
    .mini-green {{color:#28dd7d;}}
    .mini-orange {{color:#e89d45;}}
    .mini-value {{font-size:22px; font-weight:900; color:white;}}
    .prob-shell {{background:#111214; border-radius:8px; padding:14px 18px; margin-top:10px; margin-bottom:10px; border:1px solid {BORDER};}}
    .prob-row {{display:flex; align-items:center; gap:20px;}}
    .prob-text {{font-size:18px; font-weight:900; min-width:120px;}}
    .prob-bar {{flex:1; height:12px; background:#4b4f56; border-radius:999px; overflow:hidden;}}
    .prob-fill {{height:100%; background:#2d82c7; border-radius:999px;}}
    .trade-box {{background:#050607; border:1px solid #2166ff; border-radius:10px; padding:16px 20px; margin-top:12px;}}
    .trade-title {{font-size:24px; font-weight:900; color:{BLUE};}}
    .trade-note {{font-size:13px; color:#b8bec7; margin-top:6px;}}
    .small-caption {{font-size:12px; color:{MUTED}; text-align:right; margin-top:6px;}}
    .stDataFrame {{border:1px solid {BORDER}; border-radius:8px; overflow:hidden;}}
    </style>
    """,
    unsafe_allow_html=True,
)


def is_market_open():
    now_ist = datetime.now(IST)
    market_open = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now_ist <= market_close


def api_headers():
    if not ACCESS_TOKEN:
        raise RuntimeError("Missing ACCESS_TOKEN in Streamlit secrets")
    return {"Authorization": f"Bearer {ACCESS_TOKEN}", "Accept": "application/json"}


@st.cache_data(ttl=60, show_spinner=False)
def load_expiry_choices(option_key):
    url = "https://api.upstox.com/v2/option/contract"
    r = requests.get(url, params={"instrument_key": option_key}, headers=api_headers(), timeout=10)
    r.raise_for_status()
    payload = r.json()
    contracts = payload.get("data", []) if isinstance(payload, dict) else []
    expiries = sorted({item.get("expiry") for item in contracts if item.get("expiry")})
    return expiries or [DEFAULT_EXPIRY_DATE]


def get_market_data(config):
    url = "https://api.upstox.com/v2/market-quote/quotes"
    r = requests.get(
        url,
        params={"instrument_key": f"{config['quote_key']},{INDIA_VIX_QUOTE_KEY}"},
        headers=api_headers(),
        timeout=10,
    )
    if r.status_code == 401:
        raise RuntimeError("Invalid ACCESS_TOKEN")
    r.raise_for_status()
    data = r.json().get("data", {})
    quote_key = config["quote_data_key"]
    if quote_key not in data:
        raise RuntimeError(f"Quote not found for {config['display_name']}")
    spot = float(data[quote_key]["last_price"])
    vix = float(data[INDIA_VIX_DATA_KEY]["last_price"]) if INDIA_VIX_DATA_KEY in data else None
    return spot, vix


def get_option_chain(config, expiry):
    url = "https://api.upstox.com/v2/option/chain"
    r = requests.get(
        url,
        params={"instrument_key": config["option_key"], "expiry_date": expiry},
        headers=api_headers(),
        timeout=15,
    )
    if r.status_code == 401:
        raise RuntimeError("Invalid ACCESS_TOKEN")
    r.raise_for_status()
    payload = r.json()
    data = payload.get("data", []) if isinstance(payload, dict) else []
    if not data:
        raise RuntimeError(f"Option chain not found for {config['display_name']} @ {expiry}")
    return data


@st.cache_data(ttl=20, show_spinner=False)
def get_intraday_candles(history_key, interval="3minute"):
    url = f"https://api.upstox.com/v2/historical-candle/intraday/{history_key}/{interval}"
    r = requests.get(url, headers=api_headers(), timeout=15)
    if r.status_code == 401:
        raise RuntimeError("Invalid ACCESS_TOKEN")
    r.raise_for_status()
    payload = r.json()
    candles = payload.get("data", {}).get("candles", []) if isinstance(payload, dict) else []
    if not candles:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume", "oi"])

    df = pd.DataFrame(candles, columns=["time", "open", "high", "low", "close", "volume", "oi"])
    df["time"] = pd.to_datetime(df["time"], utc=True).dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    df = df.sort_values("time").reset_index(drop=True)
    return df


def send_telegram(msg):
    if not TG_BOT_TOKEN or not TG_CHAT_ID or not msg.strip():
        return False
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.get(
            url,
            params={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=8,
        )
        return resp.ok
    except Exception:
        return False


def base_layout(title, height=330):
    return dict(
        template="plotly_dark",
        title=dict(text=title, x=0.5, xanchor="center", font=dict(size=18, color="#f0f0f0")),
        paper_bgcolor="#0f1012",
        plot_bgcolor="#0f1012",
        height=height,
        margin=dict(l=8, r=8, t=42, b=8),
        legend=dict(orientation="h", y=1.02, x=1, xanchor="right", font=dict(color="#ffffff")),
        xaxis=dict(showgrid=True, gridcolor=GRID, zeroline=False, tickfont=dict(color="#d3d7dd")),
        yaxis=dict(showgrid=True, gridcolor=GRID, zeroline=False, tickfont=dict(color="#d3d7dd")),
    )


def build_bar_chart(subset, left_col, right_col, title):
    fig = go.Figure()
    x = subset["strike_price"].astype(str)
    fig.add_bar(x=x, y=subset[left_col], name="CALL", marker_color=RED)
    fig.add_bar(x=x, y=subset[right_col], name="PUT", marker_color=GREEN)
    fig.update_layout(**base_layout(title, 330), barmode="group")
    return fig


def build_line_chart(history, title, color):
    fig = go.Figure()
    if history:
        x = [item[0] for item in history]
        y = [item[1] for item in history]
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="lines+markers",
                line=dict(color=color, width=2),
                marker=dict(size=5)
            )
        )
    fig.update_layout(**base_layout(title, 300), showlegend=False)
    return fig


def append_buildup_bucket(timestamp_dt, buildup_value):
    bucket = pd.Timestamp(timestamp_dt).floor("3min").to_pydatetime()
    history = st.session_state.get("buildup_history", [])

    if history and history[-1][0] == bucket:
        prev_bucket, prev_val = history[-1]
        history[-1] = (prev_bucket, prev_val + buildup_value)
    else:
        history.append((bucket, buildup_value))

    st.session_state.buildup_history = history[-100:]


def build_candle_buildup_chart(candle_df, buildup_history, symbol):
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.72, 0.28],
        subplot_titles=(f"{symbol} · 3-MIN CANDLESTICK", "NET POSITION BUILDUP")
    )

    if not candle_df.empty:
        fig.add_trace(
            go.Candlestick(
                x=candle_df["time"],
                open=candle_df["open"],
                high=candle_df["high"],
                low=candle_df["low"],
                close=candle_df["close"],
                name="Price",
                increasing_line_color=GREEN,
                decreasing_line_color=RED,
                increasing_fillcolor=GREEN,
                decreasing_fillcolor=RED,
            ),
            row=1,
            col=1
        )

    if buildup_history:
        bdf = pd.DataFrame(buildup_history, columns=["time", "buildup"]).dropna().copy()
        if not bdf.empty:
            bdf["time"] = pd.to_datetime(bdf["time"])
            bdf = bdf.groupby("time", as_index=False)["buildup"].sum()
            bdf = bdf.sort_values("time")

            if not candle_df.empty:
                valid_times = set(candle_df["time"])
                bdf = bdf[bdf["time"].isin(valid_times)]

            colors = [GREEN if v >= 0 else RED for v in bdf["buildup"]]

            fig.add_trace(
                go.Bar(
                    x=bdf["time"],
                    y=bdf["buildup"],
                    name="Buildup",
                    marker_color=colors,
                    xperiod=180000,
                    xperiodalignment="start",
                ),
                row=2,
                col=1
            )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0f1012",
        plot_bgcolor="#0f1012",
        height=560,
        margin=dict(l=8, r=8, t=48, b=8),
        legend=dict(orientation="h", y=1.02, x=1, xanchor="right", font=dict(color="#ffffff")),
        xaxis=dict(showgrid=True, gridcolor=GRID, zeroline=False, rangeslider=dict(visible=False)),
        yaxis=dict(showgrid=True, gridcolor=GRID, zeroline=False),
        xaxis2=dict(showgrid=True, gridcolor=GRID, zeroline=False),
        yaxis2=dict(showgrid=True, gridcolor=GRID, zeroline=True, zerolinecolor="rgba(255,255,255,0.18)"),
        bargap=0.15,
    )
    fig.update_annotations(font=dict(size=14, color="#f0f0f0"))
    return fig


def analyze(data, spot, vix, symbol, expiry):
    df = pd.json_normalize(data).sort_values("strike_price")
    if df.empty:
        raise RuntimeError("Empty option chain")

    df["call_chg_oi"] = df["call_options.market_data.oi"] - df["call_options.market_data.prev_oi"]
    df["put_chg_oi"] = df["put_options.market_data.oi"] - df["put_options.market_data.prev_oi"]

    call_sum = df["call_options.market_data.oi"].sum()
    put_sum = df["put_options.market_data.oi"].sum()
    total_pcr = round(put_sum / call_sum, 2) if call_sum else 0.0

    df["dist"] = (df["strike_price"] - spot).abs()
    nearest_idx = df["dist"].idxmin()
    center_pos = df.index.get_loc(nearest_idx)

    subset = df.iloc[max(0, center_pos - 2): min(len(df), center_pos + 3)].copy()
    if subset.empty:
        subset = df.head(5).copy()

    curr_dt = datetime.now(IST).replace(tzinfo=None)

    st.session_state.pcr_history.append((curr_dt, total_pcr))
    st.session_state.pcr_history = st.session_state.pcr_history[-100:]

    vix_chg = 0.0
    if vix is not None:
        st.session_state.vix_history.append((curr_dt, vix))
        st.session_state.vix_history = st.session_state.vix_history[-100:]
        prev_vix = st.session_state.prev_vix
        vix_chg = ((vix - prev_vix) / prev_vix * 100) if prev_vix else 0.0

    net_buildup = float(subset["put_chg_oi"].sum() - subset["call_chg_oi"].sum())
    append_buildup_bucket(curr_dt, net_buildup)

    df_reset = df.reset_index(drop=True)
    atm_strike = df.loc[nearest_idx, "strike_price"]
    atm_pos_list = df_reset.index[df_reset["strike_price"] == atm_strike].tolist()
    atm_pos_idx = atm_pos_list[0] if atm_pos_list else center_pos
    wide = df_reset.iloc[max(0, atm_pos_idx - 5): min(len(df_reset), atm_pos_idx + 6)].copy()

    above_atm = wide[wide["strike_price"] > spot]
    below_atm = wide[wide["strike_price"] <= spot]

    if not above_atm.empty:
        active_res = int(above_atm.loc[above_atm["call_chg_oi"].idxmax(), "strike_price"])
    else:
        active_res = int(wide.loc[wide["call_chg_oi"].idxmax(), "strike_price"])

    if not below_atm.empty:
        active_sup = int(below_atm.loc[below_atm["put_chg_oi"].idxmax(), "strike_price"])
    else:
        active_sup = int(wide.loc[wide["put_chg_oi"].idxmax(), "strike_price"])

    wide["total_abs_chg_oi"] = wide["call_chg_oi"].abs() + wide["put_chg_oi"].abs()
    battleground = int(wide.loc[wide["total_abs_chg_oi"].idxmax(), "strike_price"])

    bull_score = max(5, min(95, 50 + (total_pcr - 1.0) * 40 + (vix_chg * -2)))

    prev_spot = st.session_state.prev_spot
    sr_range = max(active_res - active_sup, 1)
    buffer = sr_range * 0.03

    bounced_from_res = prev_spot is not None and prev_spot >= (active_res - buffer) and spot < prev_spot
    bounced_from_sup = prev_spot is not None and prev_spot <= (active_sup + buffer) and spot > prev_spot
    broke_above_res = spot > active_res
    broke_below_sup = spot < active_sup

    if broke_above_res:
        alert_msg = "BREAKOUT — BUY CE 🚀"
        trade_note = f"Spot {spot:,.0f} broke above Res {active_res} → Buy ATM/OTM Call | SL below {active_res} | PCR {total_pcr:.2f}"
        alert_emoji = "🚀"
        status_type = "success"
    elif broke_below_sup:
        alert_msg = "BREAKDOWN — BUY PE ⚠️"
        trade_note = f"Spot {spot:,.0f} broke below Sup {active_sup} → Buy ATM/OTM Put | SL above {active_sup} | PCR {total_pcr:.2f}"
        alert_emoji = "⚠️"
        status_type = "error"
    elif bounced_from_res:
        alert_msg = "REJECTION AT RES — BUY PE 🔻"
        trade_note = f"Spot reversed from Res {active_res} ({prev_spot:,.0f} → {spot:,.0f}) → Buy Put | SL above {active_res} | PCR {total_pcr:.2f}"
        alert_emoji = "🔻"
        status_type = "error"
    elif bounced_from_sup:
        alert_msg = "BOUNCE FROM SUP — BUY CE 🔼"
        trade_note = f"Spot bounced from Sup {active_sup} ({prev_spot:,.0f} → {spot:,.0f}) → Buy Call | SL below {active_sup} | PCR {total_pcr:.2f}"
        alert_emoji = "🔼"
        status_type = "success"
    else:
        alert_msg = "SIDEWAYS ⚖️"
        trade_note = f"Spot {spot:,.0f} ranging between Sup {active_sup} & Res {active_res} | Wait for breakout or reversal signal | PCR {total_pcr:.2f}"
        alert_emoji = "⚖️"
        status_type = "info"

    st.session_state.last_signal = f"{symbol} — {alert_msg}"
    st.session_state.last_reason = trade_note
    st.session_state.last_status = (f"{symbol} [{expiry}] {alert_emoji} {alert_msg}", status_type)

    now = datetime.now(IST)
    if now.minute != st.session_state.last_reported_minute:
        vix_line = f"\n📊 <b>India VIX:</b> {vix:.2f}" if vix is not None else ""
        msg = (
            f"<b>{'─' * 28}</b>\n"
            f"🧠 <b>{symbol} — {alert_msg}</b>\n"
            f"<b>{'─' * 28}</b>\n"
            f"\n"
            f"📅 <b>Expiry:</b> {expiry}\n"
            f"💰 <b>Spot:</b> {spot:,.1f}\n"
            f"📈 <b>PCR:</b> {total_pcr:.2f}"
            f"{vix_line}\n"
            f"\n"
            f"🔴 <b>Active Res:</b> {active_res}\n"
            f"🟢 <b>Active Sup:</b> {active_sup}\n"
            f"⚔️  <b>Battleground:</b> {battleground}\n"
            f"\n"
            f"🎯 <b>Trade Signal:</b>\n"
            f"<code>{trade_note}</code>\n"
            f"\n"
            f"🕐 {now.strftime('%H:%M IST')} | {expiry}"
        )
        send_telegram(msg)
        st.session_state.last_reported_minute = now.minute

    st.session_state.prev_vix = vix
    st.session_state.prev_spot = spot

    return {
        "subset": subset,
        "spot": spot,
        "vix": vix,
        "vix_chg": vix_chg,
        "pcr": total_pcr,
        "active_res": active_res,
        "active_sup": active_sup,
        "battleground": battleground,
        "bull_prob": bull_score,
        "alert_msg": alert_msg,
        "trade_note": trade_note,
        "time": curr_dt.strftime("%H:%M:%S"),
        "net_buildup": net_buildup,
    }


if not ACCESS_TOKEN:
    st.error("Missing ACCESS_TOKEN in secrets.toml")
    st.stop()

control_cols = st.columns([1.6, 1.6, 2.4, 1.6, 2.4])

with control_cols[0]:
    symbol = st.selectbox(
        "Symbol",
        list(INSTRUMENTS.keys()),
        key="symbol_select",
        label_visibility="collapsed",
    )

config = INSTRUMENTS[symbol]

try:
    expiries = load_expiry_choices(config["option_key"])
except Exception:
    expiries = [DEFAULT_EXPIRY_DATE]

with control_cols[1]:
    default_index = expiries.index(DEFAULT_EXPIRY_DATE) if DEFAULT_EXPIRY_DATE in expiries else 0
    expiry = st.selectbox(
        "Expiry",
        expiries,
        index=default_index,
        key="expiry_select",
        label_visibility="collapsed",
    )

result = None
error_message = None
market_open = is_market_open()
candle_df = pd.DataFrame()

if market_open:
    try:
        spot, vix = get_market_data(config)
        chain = get_option_chain(config, expiry)
        result = analyze(chain, spot, vix, config["display_name"], expiry)
        candle_df = get_intraday_candles(config["history_key"], interval="3minute")
    except Exception as e:
        error_message = str(e)
        st.session_state.last_status = (f"❌ {error_message}", "error")

spot_text = f"{result['spot']:,.2f}" if result else "--"
pcr_text = f"{result['pcr']:.2f}" if result else "--"
vix_text = f"{result['vix']:.2f} ({result['vix_chg']:+.2f}%)" if result and result['vix'] is not None else "--"
now_ist = datetime.now(IST)

with control_cols[2]:
    st.markdown(f'<div class="top-shell"><div class="metric-inline metric-blue">{config["display_name"]} SPOT: {spot_text}</div></div>', unsafe_allow_html=True)
with control_cols[3]:
    st.markdown(f'<div class="top-shell"><div class="metric-inline metric-purple">PCR: {pcr_text}</div></div>', unsafe_allow_html=True)
with control_cols[4]:
    st.markdown(f'<div class="top-shell"><div class="metric-inline metric-yellow">INDIA VIX: {vix_text}</div></div>', unsafe_allow_html=True)

if not market_open:
    now_str = now_ist.strftime("%I:%M %p")
    st.markdown(f'<div class="market-closed-banner">🕐 MARKET CLOSED — Current IST: {now_str} | Trading hours: 9:15 AM – 3:30 PM</div>', unsafe_allow_html=True)
else:
    status_text, status_type = st.session_state.last_status
    status_color_map = {"info": "#2b4f77", "success": "#17743b", "error": "#c93c2a"}
    st.markdown(f'<div class="status-banner" style="background:{status_color_map.get(status_type, "#c93c2a")}">{status_text}</div>', unsafe_allow_html=True)

row1_left, row1_mid, row1_right = st.columns([4.2, 4.2, 1.35])

with row1_left:
    if result is not None:
        st.plotly_chart(build_bar_chart(result["subset"], "call_options.market_data.oi", "put_options.market_data.oi", "OI BUILDUP"), use_container_width=True)
    else:
        st.info(error_message or ("Market is closed" if not market_open else "No data"))

with row1_mid:
    if result is not None:
        st.plotly_chart(build_bar_chart(result["subset"], "call_chg_oi", "put_chg_oi", "CHANGE IN OI"), use_container_width=True)
    else:
        st.info(error_message or ("Market is closed" if not market_open else "No data"))

with row1_right:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown(f'<div class="mini-card"><div class="mini-title mini-red">ACTIVE RES (CHG)</div><div class="mini-value">{result["active_res"] if result else "--"}</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="mini-card"><div class="mini-title mini-green">ACTIVE SUP (CHG)</div><div class="mini-value">{result["active_sup"] if result else "--"}</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="mini-card"><div class="mini-title mini-orange">BATTLEGROUND</div><div class="mini-value">{result["battleground"] if result else "--"}</div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

bear_label = f"{int(result['bull_prob'])}% BULL" if result and result['bull_prob'] >= 50 else f"{int(result['bull_prob'])}% BEAR" if result else "--"
prob_fill = int(result['bull_prob']) if result else 50
st.markdown(
    f'<div class="prob-shell"><div class="prob-row"><div class="prob-text">{bear_label}</div><div class="prob-bar"><div class="prob-fill" style="width:{prob_fill}%"></div></div></div></div>',
    unsafe_allow_html=True
)

if market_open and (not candle_df.empty or st.session_state.buildup_history):
    st.plotly_chart(
        build_candle_buildup_chart(
            candle_df,
            st.session_state.buildup_history,
            config["display_name"]
        ),
        use_container_width=True
    )
else:
    st.info(error_message or ("Market is closed" if not market_open else "No chart data"))

row2_left, row2_right = st.columns(2)
with row2_left:
    st.plotly_chart(build_line_chart(st.session_state.pcr_history, "PCR TREND", PURPLE), use_container_width=True)
with row2_right:
    st.plotly_chart(build_line_chart(st.session_state.vix_history, "INDIA VIX TREND", GREEN), use_container_width=True)

signal_color_map = {"success": "#17743b", "error": "#c93c2a", "info": "#2b4f77"}
_, sig_type = st.session_state.last_status
sig_border = signal_color_map.get(sig_type, "#2166ff")

st.markdown(
    f'''<div class="trade-box" style="border-color:{sig_border};">
        <div class="trade-title" style="color:{sig_border};">{st.session_state.last_signal}</div>
        <div class="trade-note">{st.session_state.last_reason}</div>
    </div>''',
    unsafe_allow_html=True,
)

if result is not None:
    st.markdown(f'<div class="small-caption">Updated at {result["time"]}</div>', unsafe_allow_html=True)
    table_df = result["subset"][[
        "strike_price",
        "call_options.market_data.oi",
        "put_options.market_data.oi",
        "call_chg_oi",
        "put_chg_oi",
    ]].rename(columns={
        "strike_price": "Strike",
        "call_options.market_data.oi": "Call OI",
        "put_options.market_data.oi": "Put OI",
        "call_chg_oi": "Call Chg OI",
        "put_chg_oi": "Put Chg OI",
    })
    with st.expander("Show data table"):
        st.dataframe(table_df, use_container_width=True, hide_index=True)

if AUTOREFRESH_AVAILABLE:
    refresh_interval_ms = REFRESH_RATE * 1000 if market_open else 60_000
    st_autorefresh(interval=refresh_interval_ms, key="fno_autorefresh")
else:
    st.caption("streamlit-autorefresh not installed; the app will refresh only on manual rerun.")
