import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

st.set_page_config(page_title="FNO Intelligence Terminal", layout="wide")

# ── Autorefresh (non-blocking, replaces time.sleep + st.rerun) ─────────────────
try:
    from streamlit_autorefresh import st_autorefresh
    _AUTOREFRESH_AVAILABLE = True
except ImportError:
    _AUTOREFRESH_AVAILABLE = False

# Early injection to catch portal-rendered dropdown popup
st.markdown("""
<style>
div[data-baseweb="popover"] { background: #000000 !important; }
div[data-baseweb="popover"] * { background-color: #000000 !important; color: #ffffff !important; -webkit-text-fill-color: #ffffff !important; }
div[data-baseweb="menu"] { background: #000000 !important; }
div[data-baseweb="menu"] * { background-color: #000000 !important; color: #ffffff !important; }
ul[role="listbox"] { background: #000000 !important; }
ul[role="listbox"] * { background-color: #000000 !important; color: #ffffff !important; }
li[role="option"] { background: #000000 !important; color: #ffffff !important; }
li[role="option"]:hover { background: #1a1a2e !important; }
</style>
""", unsafe_allow_html=True)

# Title bar
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
    "NIFTY": {"display_name": "NIFTY", "quote_key": "NSE_INDEX|Nifty 50", "quote_data_key": "NSE_INDEX:Nifty 50", "option_key": "NSE_INDEX|Nifty 50"},
    "SENSEX": {"display_name": "SENSEX", "quote_key": "BSE_INDEX|SENSEX", "quote_data_key": "BSE_INDEX:SENSEX", "option_key": "BSE_INDEX|SENSEX"},
    "BANKNIFTY": {"display_name": "BANKNIFTY", "quote_key": "NSE_INDEX|Nifty Bank", "quote_data_key": "NSE_INDEX:Nifty Bank", "option_key": "NSE_INDEX|Nifty Bank"},
    "FINNIFTY": {"display_name": "FINNIFTY", "quote_key": "NSE_INDEX|Nifty Fin Service", "quote_data_key": "NSE_INDEX:Nifty Fin Service", "option_key": "NSE_INDEX|Nifty Fin Service"},
    "MIDCPNIFTY": {"display_name": "MIDCPNIFTY", "quote_key": "NSE_INDEX|NIFTY MID SELECT", "quote_data_key": "NSE_INDEX:NIFTY MID SELECT", "option_key": "NSE_INDEX|NIFTY MID SELECT"},
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


# ── FIX #5: Auto-compute next weekday Thursday as fallback expiry ──────────────
def get_default_expiry():
    today = datetime.now(IST).date()
    days_ahead = (3 - today.weekday()) % 7   # 3 = Thursday
    if days_ahead == 0:
        days_ahead = 7
    candidate = today + timedelta(days=days_ahead)
    # Skip if it falls on weekend (shouldn't since Thursday, but safety check)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return str(candidate)

DEFAULT_EXPIRY_DATE = get_secret("DEFAULT_EXPIRY_DATE") or get_default_expiry()


for key, default in {
    "pcr_history": [],
    "vix_history": [],
    "last_reported_minute": None,
    "prev_vix": None,
    "prev_spot": None,
    "last_signal": "AI SCANNING...",
    "last_reason": "Waiting for data...",
    "last_status": ("SYSTEM READY - SELECT SYMBOL AND EXPIRY", "info"),
    "countdown": REFRESH_RATE,
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

    /* ===== UNIFORM TOP ROW HEIGHT ===== */
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
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] [data-testid="stSelectbox"] > div,
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

    /* ===== SELECTBOX CONTROL (CLOSED STATE) ===== */
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

    /* ===== DROPDOWN POPUP (OPEN STATE) ===== */
    div[data-baseweb="popover"],
    div[data-baseweb="popover"] > div,
    div[data-baseweb="popover"] > div > div,
    div[data-baseweb="menu"],
    div[data-baseweb="menu"] > div,
    ul[role="listbox"],
    ul[role="listbox"] > li {{
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

    /* ===== REST OF APP STYLES ===== */
    .metric-inline {{font-size:13px; font-weight:800; white-space:nowrap;}}
    .metric-blue {{color:{BLUE};}}
    .metric-purple {{color:{PURPLE};}}
    .metric-yellow {{color:{YELLOW};}}
    .sync-wrap {{display:flex; flex-direction:column; align-items:center; justify-content:center; width:100%; height:62px;}}
    .sync-label {{font-size:11px; color:{MUTED}; font-weight:700; letter-spacing:0.05em; margin-bottom:2px;}}
    .sync-countdown {{font-size:26px; font-weight:900; color:{BLUE}; line-height:1;}}
    .sync-unit {{font-size:11px; color:{MUTED}; margin-top:1px;}}
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

    /* ===== BLAST ZONE ===== */
    .blast-header {{
        font-size: 15px;
        font-weight: 900;
        color: {ORANGE};
        letter-spacing: 0.06em;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        gap: 8px;
    }}
    .blast-shell {{
        background: #0f1012;
        border: 1px solid rgba(255,159,67,0.25);
        border-radius: 10px;
        padding: 14px 16px;
        margin-top: 14px;
        margin-bottom: 10px;
    }}
    .blast-table {{width:100%; border-collapse:collapse; font-size:13px;}}
    .blast-table th {{
        color:{MUTED};
        font-size:11px;
        font-weight:800;
        letter-spacing:0.05em;
        padding:6px 10px;
        border-bottom:1px solid rgba(255,255,255,0.07);
        text-align:center;
    }}
    .blast-table td {{
        padding: 7px 10px;
        text-align: center;
        border-bottom: 1px solid rgba(255,255,255,0.04);
        font-weight: 700;
        color: #ffffff;
    }}
    .blast-table tr:last-child td {{ border-bottom: none; }}
    .blast-table tr:hover td {{ background: rgba(255,255,255,0.03); }}
    .score-fire {{ color: {ORANGE}; font-size: 14px; letter-spacing: 2px; }}
    .atm-row td {{ background: rgba(57,164,255,0.07) !important; }}
    </style>
    """,
    unsafe_allow_html=True,
)


def is_market_open():
    now_ist = datetime.now(IST)
    market_open = now_ist.replace(hour=9, minute=0, second=0, microsecond=0)
    market_close = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now_ist <= market_close


def api_headers():
    if not ACCESS_TOKEN:
        raise RuntimeError("Missing ACCESS_TOKEN in Streamlit secrets")
    return {"Authorization": f"Bearer {ACCESS_TOKEN}", "Accept": "application/json"}


@st.cache_data(ttl=60, show_spinner=False)
def load_expiry_choices(option_key):
    url = f"https://api.upstox.com/v2/option/contract?instrument_key={option_key}"
    r = requests.get(url, headers=api_headers(), timeout=10)
    r.raise_for_status()
    payload = r.json()
    contracts = payload.get("data", []) if isinstance(payload, dict) else []
    expiries = sorted({item.get("expiry") for item in contracts if item.get("expiry")})
    return expiries or [DEFAULT_EXPIRY_DATE]


def get_market_data(config):
    quote_keys = [config["quote_key"], INDIA_VIX_QUOTE_KEY]
    url = f"https://api.upstox.com/v2/market-quote/quotes?instrument_key={','.join(quote_keys)}"
    r = requests.get(url, headers=api_headers(), timeout=10)
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
    url = f"https://api.upstox.com/v2/option/chain?instrument_key={config['option_key']}&expiry_date={expiry}"
    r = requests.get(url, headers=api_headers(), timeout=15)
    if r.status_code == 401:
        raise RuntimeError("Invalid ACCESS_TOKEN")
    r.raise_for_status()
    payload = r.json()
    data = payload.get("data", []) if isinstance(payload, dict) else []
    if not data:
        raise RuntimeError(f"Option chain not found for {config['display_name']} @ {expiry}")
    return data


def send_telegram(msg):
    if not TG_BOT_TOKEN or not TG_CHAT_ID or not msg.strip():
        return False
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    try:
        requests.get(url, params={
            "chat_id": TG_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML",
        }, timeout=8)
        return True
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
        fig.add_trace(go.Scatter(x=x, y=y, mode="lines+markers", line=dict(color=color, width=2), marker=dict(size=5)))
    fig.update_layout(**base_layout(title, 300), showlegend=False)
    return fig


def build_gamma_chart(blast_df):
    fig = go.Figure()
    strikes = blast_df["Strike"].astype(str)
    colors = [ORANGE if g == blast_df["Call Γ"].max() else BLUE for g in blast_df["Call Γ"]]
    fig.add_bar(x=strikes, y=blast_df["Call Γ"], name="Call Gamma", marker_color=colors)
    fig.add_bar(x=strikes, y=blast_df["Put Γ"], name="Put Gamma", marker_color=GREEN)
    layout = base_layout("⚡ GAMMA SPIKE — BLAST ZONE", 260)
    layout["legend"] = dict(orientation="h", y=1.05, x=1, xanchor="right", font=dict(color="#ffffff"))
    fig.update_layout(**layout, barmode="group")
    fig.add_annotation(
        text="Higher Gamma = Explosive Move Potential",
        xref="paper", yref="paper", x=0.01, y=0.97,
        showarrow=False, font=dict(size=10, color=MUTED), align="left"
    )
    return fig


# ── FIX #6: Corrected gamma scaling for realistic index option values ──────────
def blast_score(gamma, delta, chg_oi, max_chg_oi):
    g_score = min(gamma * 5000, 5)                          # was * 10; index gamma ~0.001
    d_score = max(0, (0.1 - abs(abs(delta) - 0.5)) * 50)
    o_score = (chg_oi / max_chg_oi * 5) if max_chg_oi > 0 else 0
    total = g_score + d_score + o_score
    if total >= 7:
        return "🔥🔥🔥", total
    elif total >= 4:
        return "🔥🔥", total
    else:
        return "🔥", total


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

    # ── Blast Zone data ────────────────────────────────────────────────────────
    blast_rows = []
    max_chg = max(subset["call_chg_oi"].abs().max(), subset["put_chg_oi"].abs().max(), 1)
    atm_strike = int(df.loc[nearest_idx, "strike_price"])

    for _, row in subset.iterrows():
        c_delta = row.get("call_options.option_greeks.delta", 0) or 0
        c_gamma = row.get("call_options.option_greeks.gamma", 0) or 0
        p_delta = row.get("put_options.option_greeks.delta", 0) or 0
        p_gamma = row.get("put_options.option_greeks.gamma", 0) or 0
        chg = abs(row["call_chg_oi"]) + abs(row["put_chg_oi"])
        avg_gamma = (c_gamma + p_gamma) / 2
        avg_delta = (abs(c_delta) + abs(p_delta)) / 2
        emoji, score = blast_score(avg_gamma, avg_delta, chg, max_chg)
        blast_rows.append({
            "Strike": int(row["strike_price"]),
            "ATM": int(row["strike_price"]) == atm_strike,
            "Call Δ": round(c_delta, 3),
            "Call Γ": round(c_gamma, 4),
            "Put Δ": round(p_delta, 3),
            "Put Γ": round(p_gamma, 4),
            "Score": score,
            "Blast": emoji,
        })

    blast_df = pd.DataFrame(blast_rows)

    curr_time = datetime.now(IST).strftime("%H:%M:%S")
    st.session_state.pcr_history.append((curr_time, total_pcr))
    st.session_state.pcr_history = st.session_state.pcr_history[-100:]

    vix_chg = 0.0
    if vix is not None:
        st.session_state.vix_history.append((curr_time, vix))
        st.session_state.vix_history = st.session_state.vix_history[-100:]
        prev_vix = st.session_state.prev_vix
        vix_chg = ((vix - prev_vix) / prev_vix * 100) if prev_vix else 0.0

    # ── ATM ± 5 strikes window for Res/Sup calculation ───────────────────────
    df_reset = df.reset_index(drop=True)
    atm_pos_list = df_reset.index[df_reset["strike_price"] == df.loc[nearest_idx, "strike_price"]].tolist()
    atm_pos_idx = atm_pos_list[0] if atm_pos_list else center_pos
    wide = df_reset.iloc[max(0, atm_pos_idx - 5): min(len(df_reset), atm_pos_idx + 6)].copy()

    # Resistance = closest strike ABOVE spot with highest call chg OI
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

    battleground = int(wide.loc[wide["call_chg_oi"].abs().idxmax(), "strike_price"])
    bull_prob = max(5, min(95, 50 + (total_pcr - 1.0) * 40 + (vix_chg * -2)))

    # ── Reversal Detection (compares current spot vs prev_spot) ──────────────
    prev_spot = st.session_state.prev_spot
    sr_range = max(active_res - active_sup, 1)
    buffer = sr_range * 0.03   # 3% of S/R range as reversal buffer

    bounced_from_res = (
        prev_spot is not None and
        prev_spot >= (active_res - buffer) and
        spot < prev_spot
    )
    bounced_from_sup = (
        prev_spot is not None and
        prev_spot <= (active_sup + buffer) and
        spot > prev_spot
    )
    broke_above_res = spot > active_res
    broke_below_sup = spot < active_sup

    # ── Signal + Trade Suggestion Logic ──────────────────────────────────────
    if broke_above_res:
        alert_msg   = "BREAKOUT — BUY CE 🚀"
        trade_note  = (f"Spot {spot:,.0f} broke above Res {active_res} → "
                       f"Buy ATM/OTM Call | SL below {active_res} | PCR {total_pcr:.2f}")
        alert_emoji = "🚀"
        status_type = "success"
    elif broke_below_sup:
        alert_msg   = "BREAKDOWN — BUY PE ⚠️"
        trade_note  = (f"Spot {spot:,.0f} broke below Sup {active_sup} → "
                       f"Buy ATM/OTM Put | SL above {active_sup} | PCR {total_pcr:.2f}")
        alert_emoji = "⚠️"
        status_type = "error"
    elif bounced_from_res:
        alert_msg   = "REJECTION AT RES — BUY PE 🔻"
        trade_note  = (f"Spot reversed from Res {active_res} "
                       f"({prev_spot:,.0f} → {spot:,.0f}) → "
                       f"Buy Put | SL above {active_res} | PCR {total_pcr:.2f}")
        alert_emoji = "🔻"
        status_type = "error"
    elif bounced_from_sup:
        alert_msg   = "BOUNCE FROM SUP — BUY CE 🔼"
        trade_note  = (f"Spot bounced from Sup {active_sup} "
                       f"({prev_spot:,.0f} → {spot:,.0f}) → "
                       f"Buy Call | SL below {active_sup} | PCR {total_pcr:.2f}")
        alert_emoji = "🔼"
        status_type = "success"
    else:
        alert_msg   = "SIDEWAYS ⚖️"
        trade_note  = (f"Spot {spot:,.0f} ranging between Sup {active_sup} & Res {active_res} | "
                       f"Wait for breakout or reversal signal | PCR {total_pcr:.2f}")
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
        "blast_df": blast_df,
        "spot": spot,
        "vix": vix,
        "vix_chg": vix_chg,
        "pcr": total_pcr,
        "active_res": active_res,
        "active_sup": active_sup,
        "battleground": battleground,
        "bull_prob": bull_prob,
        "alert_msg": alert_msg,
        "trade_note": trade_note,
        "time": curr_time,
    }


if not ACCESS_TOKEN:
    st.error("Missing ACCESS_TOKEN in secrets.toml")
    st.stop()

control_cols = st.columns([1.6, 1.6, 2.2, 1.5, 2.2, 1.4])
with control_cols[0]:
    symbol = st.selectbox("Symbol", list(INSTRUMENTS.keys()), label_visibility="collapsed")

config = INSTRUMENTS[symbol]

try:
    expiries = load_expiry_choices(config["option_key"])
except Exception:
    expiries = [DEFAULT_EXPIRY_DATE]

with control_cols[1]:
    default_index = expiries.index(DEFAULT_EXPIRY_DATE) if DEFAULT_EXPIRY_DATE in expiries else 0
    expiry = st.selectbox("Expiry", expiries, index=default_index, label_visibility="collapsed")

result = None
error_message = None
market_open = is_market_open()

if market_open:
    try:
        spot, vix = get_market_data(config)
        chain = get_option_chain(config, expiry)
        result = analyze(chain, spot, vix, config["display_name"], expiry)
    except Exception as e:
        error_message = str(e)
        st.session_state.last_status = (f"❌ {error_message}", "error")

spot_text = f"{result['spot']:,.2f}" if result else "--"
pcr_text = f"{result['pcr']:.2f}" if result else "--"
vix_text = f"{result['vix']:.2f} ({result['vix_chg']:+.2f}%)" if result and result['vix'] is not None else "--"

now_ist = datetime.now(IST)

if market_open:
    seconds_left = REFRESH_RATE - (now_ist.second % REFRESH_RATE)
    # ── FIX #7: JS live countdown ticker (ticks every second client-side) ──────
    countdown_html = f"""
    <div class="top-shell">
      <div class="sync-wrap">
        <div class="sync-label">NEXT REFRESH</div>
        <div class="sync-countdown" id="fno-cd">{seconds_left}</div>
        <div class="sync-unit">seconds</div>
      </div>
    </div>
    <script>
      (function() {{
        let t = {seconds_left};
        function tick() {{
          const el = window.parent.document.getElementById('fno-cd');
          if (!el) return;
          el.textContent = t;
          if (t > 0) {{ t--; setTimeout(tick, 1000); }}
        }}
        tick();
      }})();
    </script>"""
else:
    # ── FIX #8: Weekend-aware next market open calculation ────────────────────
    def next_market_open(now):
        candidate = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if now >= candidate:
            candidate += timedelta(days=1)
        while candidate.weekday() >= 5:   # 5=Sat, 6=Sun
            candidate += timedelta(days=1)
        return candidate

    next_open = next_market_open(now_ist)
    diff = next_open - now_ist
    hrs, rem = divmod(int(diff.total_seconds()), 3600)
    mins = rem // 60
    countdown_html = f"""
    <div class="top-shell">
      <div class="sync-wrap">
        <div class="sync-label">MARKET OPENS IN</div>
        <div class="sync-countdown">{hrs:02d}:{mins:02d}</div>
        <div class="sync-unit">HH:MM</div>
      </div>
    </div>"""

with control_cols[2]:
    st.markdown(f'<div class="top-shell"><div class="metric-inline metric-blue">{config["display_name"]} SPOT: {spot_text}</div></div>', unsafe_allow_html=True)
with control_cols[3]:
    st.markdown(f'<div class="top-shell"><div class="metric-inline metric-purple">PCR: {pcr_text}</div></div>', unsafe_allow_html=True)
with control_cols[4]:
    st.markdown(f'<div class="top-shell"><div class="metric-inline metric-yellow">INDIA VIX: {vix_text}</div></div>', unsafe_allow_html=True)
with control_cols[5]:
    st.markdown(countdown_html, unsafe_allow_html=True)

if not market_open:
    now_str = now_ist.strftime("%I:%M %p")
    st.markdown(f'<div class="market-closed-banner">🕐 MARKET CLOSED — Current IST: {now_str} | Trading hours: 9:00 AM – 3:30 PM</div>', unsafe_allow_html=True)
else:
    status_text, status_type = st.session_state.last_status
    status_color_map = {"info": "#2b4f77", "success": "#17743b", "error": "#c93c2a"}
    st.markdown(f'<div class="status-banner" style="background:{status_color_map.get(status_type, "#c93c2a")}">{status_text}</div>', unsafe_allow_html=True)

# ── ROW 1: OI Buildup + Change in OI + Mini Cards ────────────────────────────
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
st.markdown(f'<div class="prob-shell"><div class="prob-row"><div class="prob-text">{bear_label}</div><div class="prob-bar"><div class="prob-fill" style="width:{prob_fill}%"></div></div></div></div>', unsafe_allow_html=True)

# ── ROW 2: PCR Trend + India VIX Trend ───────────────────────────────────────
row2_left, row2_right = st.columns(2)
with row2_left:
    st.plotly_chart(build_line_chart(st.session_state.pcr_history, "PCR TREND", PURPLE), use_container_width=True)
with row2_right:
    st.plotly_chart(build_line_chart(st.session_state.vix_history, "INDIA VIX TREND", GREEN), use_container_width=True)

# ── ROW 3: Gamma Blast Zone ───────────────────────────────────────────────────
if result is not None:
    blast_df = result["blast_df"]
    blast_left, blast_right = st.columns([1.2, 1])
    with blast_left:
        st.plotly_chart(build_gamma_chart(blast_df), use_container_width=True)
    with blast_right:
        st.markdown('<div class="blast-shell">', unsafe_allow_html=True)
        st.markdown('<div class="blast-header">🔥 BLAST ZONE — DELTA & GAMMA SCANNER</div>', unsafe_allow_html=True)
        rows_html = ""
        for _, row in blast_df.iterrows():
            atm_class = "atm-row" if row["ATM"] else ""
            atm_tag = " ◀ ATM" if row["ATM"] else ""
            rows_html += f"""
            <tr class="{atm_class}">
                <td style="color:{'#39a4ff' if row['ATM'] else '#ffffff'}; font-weight:900;">{row['Strike']}{atm_tag}</td>
                <td style="color:#20e27a;">{row['Call Δ']}</td>
                <td style="color:#ff9f43;">{row['Call Γ']}</td>
                <td style="color:#ff4d4f;">{row['Put Δ']}</td>
                <td style="color:#ff9f43;">{row['Put Γ']}</td>
                <td class="score-fire">{row['Blast']}</td>
            </tr>"""
        st.markdown(f"""
        <table class="blast-table">
            <thead>
                <tr>
                    <th>STRIKE</th>
                    <th>CALL Δ</th>
                    <th>CALL Γ</th>
                    <th>PUT Δ</th>
                    <th>PUT Γ</th>
                    <th>BLAST</th>
                </tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>
        <div style="font-size:11px; color:{MUTED}; margin-top:10px;">
            🔥🔥🔥 High explosive &nbsp;|&nbsp; 🔥🔥 Moderate &nbsp;|&nbsp; 🔥 Low &nbsp;|&nbsp; ◀ ATM = At-the-money
        </div>
        """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

# ── Trade Signal Box ─────────────────────────────────────────────────────────
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
    table_df = result["subset"][["strike_price", "call_options.market_data.oi", "put_options.market_data.oi", "call_chg_oi", "put_chg_oi"]].rename(columns={
        "strike_price": "Strike",
        "call_options.market_data.oi": "Call OI",
        "put_options.market_data.oi": "Put OI",
        "call_chg_oi": "Call Chg OI",
        "put_chg_oi": "Put Chg OI",
    })
    with st.expander("Show data table"):
        st.dataframe(table_df, use_container_width=True, hide_index=True)

# ── FIX #2: Non-blocking autorefresh via streamlit-autorefresh ────────────────
# Install: pip install streamlit-autorefresh
# Replaces the old time.sleep(REFRESH_RATE) + st.rerun() block entirely.
# The browser handles the timer client-side — no thread blocking.
if _AUTOREFRESH_AVAILABLE:
    refresh_interval_ms = REFRESH_RATE * 1000 if market_open else 60_000
    st_autorefresh(interval=refresh_interval_ms, key="fno_autorefresh")
else:
    # Graceful fallback if package not installed (blocking, same as before)
    sleep_secs = REFRESH_RATE if market_open else 60
    time.sleep(sleep_secs)
    st.rerun()
