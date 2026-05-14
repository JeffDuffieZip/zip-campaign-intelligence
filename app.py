"""
Zip Campaign Intelligence Agent — Executive Demo UI
Run: streamlit run app.py
"""

import base64
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

import markdown as md_lib
import streamlit as st
from dotenv import load_dotenv

from agent import stream_response

load_dotenv()

ASSETS = Path(__file__).parent / "assets"


def render_md(text: str) -> str:
    """Convert markdown to HTML with extensions for tables, fenced code, line-breaks."""
    if not text:
        return ""
    return md_lib.markdown(
        text,
        extensions=["tables", "fenced_code", "nl2br", "sane_lists"],
        output_format="html5",
    )


def load_asset_b64(filename: str) -> str:
    """Read an asset file and return base64 — for embedding in HTML."""
    path = ASSETS / filename
    return base64.b64encode(path.read_bytes()).decode("ascii") if path.exists() else ""


def load_asset_text(filename: str) -> str:
    """Read a text asset (SVG, etc.) and return raw contents."""
    path = ASSETS / filename
    return path.read_text() if path.exists() else ""


# ── Official Zip Co brand assets (pulled directly from zip.co) ──────────────
ZIP_WORDMARK_SVG = load_asset_text("zip_wordmark.svg")
ZIP_SQUARE_LOGO_B64 = load_asset_b64("zip_logo.png")

# ── Page config ───────────────────────────────────────────────────────────────

_favicon_path = ASSETS / "zip_logo.png"
st.set_page_config(
    page_title="Zip · Campaign Intelligence",
    page_icon=str(_favicon_path) if _favicon_path.exists() else "⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Brand CSS ─────────────────────────────────────────────────────────────────

st.markdown("""
<style>
  /* ── Zip Co brand palette (extracted from Zip Co Growth Analytics PDF) ───────
     #1A0725  ink purple    — primary text
     #411260  brand purple  — headings / accents
     #6442BD  vivid purple  — brand accent / CTAs
     #786D79  warm gray     — secondary text
     #8B858E  cool gray     — muted text
     #EBEBE9  paper cream   — page background
     #FFFFFF  white         — card background
     #1B7E4F  signal green  — positive / significant
     #B43A3A  signal red    — negative
  ─────────────────────────────────────────────────────────────────────────── */
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

  /* Page background — Zip cream paper */
  .stApp { background: #EBEBE9 !important; }
  .main .block-container { background: transparent !important; }

  /* Header */
  .zip-header {
    background: #FFFFFF;
    border: 1px solid #E1E0DF;
    padding: 20px 28px; border-radius: 14px; margin-bottom: 22px;
    display: flex; align-items: center; justify-content: space-between;
    box-shadow: 0 1px 2px rgba(26,7,37,0.04);
  }
  .zip-logo-wrap { display:flex; align-items:center; gap:16px; }
  .zip-wordmark {
    display:flex; align-items:center; height:32px;
  }
  .zip-wordmark svg {
    height:32px; width:auto; display:block;
  }
  .zip-pipe {
    width:1px; height:30px; background:#E1E0DF;
  }
  /* Legacy fallback for any remaining placeholder marks */
  .zip-mark {
    width:38px; height:38px; border-radius:10px;
    background: #1A0725;
    display:flex; align-items:center; justify-content:center;
    font-weight:800; color:#FFFFFF; font-size:1.05rem; letter-spacing:-1px;
  }
  .zip-logo { font-size: 1.35rem; font-weight: 700; color: #1A0725; letter-spacing: -0.5px; line-height:1.1; }
  .zip-logo .dot { color: #6442BD; }
  .zip-subtitle { color: #786D79; font-size: 0.78rem; margin-top:2px; letter-spacing:0.2px; }
  .zip-eyebrow {
    display:inline-block; color:#6442BD; font-size:0.65rem;
    font-weight:700; letter-spacing:1.4px; text-transform:uppercase; margin-bottom:3px;
  }
  .zip-badge {
    background: rgba(100,66,189,0.08); border: 1px solid rgba(100,66,189,0.25);
    color: #6442BD; padding: 5px 12px; border-radius: 20px;
    font-size: 0.7rem; font-weight: 700; letter-spacing:1px; text-transform:uppercase;
  }

  /* Chat messages */
  .msg-user {
    background: #6442BD; color: #FFFFFF; padding: 12px 16px;
    border-radius: 14px 14px 4px 14px; margin: 8px 0 8px 60px;
    font-size: 0.9rem; line-height: 1.5;
    box-shadow: 0 1px 2px rgba(26,7,37,0.08);
  }
  .msg-agent {
    background: #FFFFFF; border: 1px solid #E1E0DF; color: #1A0725;
    padding: 14px 18px; border-radius: 14px 14px 14px 4px;
    margin: 8px 60px 8px 0; font-size: 0.88rem; line-height: 1.6;
    box-shadow: 0 1px 2px rgba(26,7,37,0.04);
  }
  .msg-agent p { margin: 0 0 10px 0; }
  .msg-agent ul, .msg-agent ol { margin: 4px 0 12px 18px; padding: 0; }
  .msg-agent li { margin: 4px 0; }
  .msg-agent strong { color: #411260; font-weight: 700; }
  .msg-agent h1, .msg-agent h2, .msg-agent h3, .msg-agent h4 {
    color: #1A0725; margin: 14px 0 6px 0; font-weight: 800;
    letter-spacing: -0.3px;
  }
  .msg-agent h1 { font-size: 1.05rem; }
  .msg-agent h2 { font-size: 0.98rem; }
  .msg-agent h3, .msg-agent h4 { font-size: 0.92rem; color:#411260; }
  .msg-agent hr {
    border: none; border-top: 1px solid #E1E0DF;
    margin: 12px 0 !important;
  }
  .msg-agent table {
    width: 100%; border-collapse: collapse; margin: 8px 0 12px 0;
    font-size: 0.82rem;
  }
  .msg-agent th {
    background: #F5F4F2; color: #411260; font-weight: 700;
    text-align: left; padding: 8px 10px; border-bottom: 1px solid #E1E0DF;
    font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.6px;
  }
  .msg-agent td {
    padding: 8px 10px; border-bottom: 1px solid #F0EFED;
    color: #1A0725;
  }
  .msg-agent tr:last-child td { border-bottom: none; }
  .msg-agent code {
    background: #F5F4F2; color: #6442BD; padding: 1px 6px;
    border-radius: 4px; font-size: 0.85em; font-family: 'SF Mono', Menlo, monospace;
  }
  .msg-agent blockquote {
    border-left: 3px solid #6442BD; padding: 4px 12px;
    margin: 8px 0; color: #786D79; background: #FAF9F8;
    border-radius: 0 6px 6px 0;
  }
  /* Inline KPI tile pattern used in narrative responses */
  .kpi-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 8px; margin: 10px 0 14px 0;
  }
  .kpi-tile {
    background: #F5F4F2; border: 1px solid #E1E0DF; border-radius: 10px;
    padding: 10px 12px;
  }
  .kpi-tile-label {
    color: #786D79; font-size: 0.6rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 1.1px; margin-bottom: 3px;
  }
  .kpi-tile-value {
    color: #1A0725; font-size: 1.0rem; font-weight: 800;
    letter-spacing: -0.3px;
  }
  .kpi-pos { color: #1B7E4F !important; }
  .kpi-neg { color: #B43A3A !important; }
  .kpi-warn { color: #A55A00 !important; }
  /* Verdict-line pattern: sig + rec inline */
  .verdict-line {
    display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
    padding: 10px 14px; background: #FAF9F8;
    border-left: 3px solid #6442BD; border-radius: 0 8px 8px 0;
    margin: 8px 0 12px 0;
  }
  .pill {
    display: inline-block; padding: 4px 10px; border-radius: 16px;
    font-size: 0.7rem; font-weight: 700; letter-spacing: 0.4px;
  }
  .pill-pos  { background:#E8F3EC; color:#1B7E4F; border:1px solid #1B7E4F; }
  .pill-neg  { background:#FBEAEA; color:#B43A3A; border:1px solid #B43A3A; }
  .pill-warn { background:#FBF2E5; color:#A55A00; border:1px solid #C97A1C; }
  .pill-info { background:#EFE9FA; color:#411260; border:1px solid #6442BD; }

  /* Tool pills */
  .tool-pill {
    display: inline-flex; align-items: center; gap: 5px;
    background: #F5F4F2; border: 1px solid #E1E0DF; border-radius: 20px;
    padding: 3px 10px; font-size: 0.72rem; color: #786D79;
    margin: 2px 4px 2px 0;
  }
  .tool-pill b { color: #6442BD; }

  /* Verdict card */
  .verdict-card {
    background: #FFFFFF; border: 1px solid #E1E0DF; border-radius: 14px;
    padding: 20px; margin-bottom: 12px;
    box-shadow: 0 1px 2px rgba(26,7,37,0.04);
  }
  .verdict-card h4 {
    color: #6442BD; font-size: 0.65rem; text-transform: uppercase;
    letter-spacing: 1.4px; font-weight: 700; margin: 0 0 6px 0;
  }
  .verdict-title { color: #1A0725; font-size: 1.0rem; font-weight: 700; margin: 0 0 12px 0; }

  /* Significance badges */
  .badge-sig {
    background:#E8F3EC; color:#1B7E4F; border:1px solid #1B7E4F;
    padding:6px 12px; border-radius:20px; font-size:0.74rem;
    font-weight:700; letter-spacing:0.4px; display:inline-block;
  }
  .badge-nosig {
    background:#FBF2E5; color:#A55A00; border:1px solid #C97A1C;
    padding:6px 12px; border-radius:20px; font-size:0.74rem;
    font-weight:700; letter-spacing:0.4px; display:inline-block;
  }
  .badge-na {
    background:#F5F4F2; color:#786D79; border:1px solid #E1E0DF;
    padding:6px 12px; border-radius:20px; font-size:0.74rem;
    font-weight:700; letter-spacing:0.4px; display:inline-block;
  }

  /* Recommendation badges */
  .rec-badge {
    padding:6px 12px; border-radius:20px; font-size:0.74rem;
    font-weight:800; letter-spacing:0.8px; display:inline-block;
    margin-left:6px;
  }
  .rec-SCALE      { background:#E8F3EC; color:#1B7E4F; border:1px solid #1B7E4F; }
  .rec-GREENLIGHT { background:#E8F3EC; color:#1B7E4F; border:2px solid #1B7E4F; font-size:0.8rem; }
  .rec-EXTEND     { background:#EFE9FA; color:#411260; border:1px solid #6442BD; }
  .rec-ITERATE    { background:#FBF2E5; color:#A55A00; border:1px solid #C97A1C; }
  .rec-WATCH      { background:#F5F4F2; color:#411260; border:1px solid #786D79; }
  .rec-RETHINK    { background:#FBEAEA; color:#B43A3A; border:1px solid #B43A3A; }
  .rec-STOP       { background:#FBEAEA; color:#B43A3A; border:1px solid #B43A3A; }

  /* Metric tiles */
  .metric-row { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin:14px 0 4px 0; }
  .metric-box {
    background:#F5F4F2; border:1px solid #E1E0DF; border-radius:10px;
    padding:11px 14px;
  }
  .metric-label {
    color:#786D79; font-size:0.62rem; text-transform:uppercase;
    letter-spacing:1.2px; margin-bottom:4px; font-weight:700;
  }
  .metric-value { color:#1A0725; font-size:1.1rem; font-weight:800; letter-spacing:-0.3px; }
  .metric-sub   { color:#8B858E; font-size:0.68rem; margin-top:3px; }
  .metric-pos   { color:#1B7E4F !important; }
  .metric-neg   { color:#B43A3A !important; }
  .metric-warn  { color:#A55A00 !important; }

  /* Inputs */
  div[data-testid="stTextInput"] input {
    background:#FFFFFF !important; border:1px solid #D6D4D2 !important;
    border-radius:10px !important; color:#1A0725 !important;
    font-size:0.9rem !important; padding:12px 16px !important;
  }
  div[data-testid="stTextInput"] input:focus {
    border-color:#6442BD !important;
    box-shadow:0 0 0 3px rgba(100,66,189,0.12) !important;
  }
  div[data-testid="stTextInput"] input::placeholder { color:#A7A1A8 !important; }

  /* Buttons */
  .stButton > button {
    background:#1A0725 !important; color:#FFFFFF !important; border:none !important;
    border-radius:10px !important; padding:12px 18px !important;
    font-weight:600 !important; font-size:0.86rem !important; width:100% !important;
    transition: all 0.15s ease;
    box-shadow: 0 1px 2px rgba(26,7,37,0.12);
  }
  .stButton > button:hover {
    background:#6442BD !important;
    transform: translateY(-1px);
    box-shadow: 0 3px 8px rgba(100,66,189,0.25) !important;
  }
  .stButton > button:focus { box-shadow: 0 0 0 3px rgba(100,66,189,0.2) !important; }

  /* Dividers */
  hr { border-color:#E1E0DF !important; margin:16px 0 !important; }

  /* Scrollbars */
  ::-webkit-scrollbar { width:6px; height:6px; }
  ::-webkit-scrollbar-thumb { background:#D6D4D2; border-radius:4px; }
  ::-webkit-scrollbar-thumb:hover { background:#786D79; }

  /* Streamlit chrome */
  #MainMenu, footer, header { visibility:hidden; }
  .block-container { padding-top:1.5rem !important; padding-bottom:2rem !important; max-width:100% !important; }
  div[data-testid="stSidebar"] { display:none; }

  /* Empty state */
  .empty-state {
    text-align:center; padding:64px 20px;
    background:#FFFFFF; border:1px dashed #D6D4D2; border-radius:14px;
  }
  .empty-state-mark {
    width:54px; height:54px; border-radius:14px; background:#1A0725;
    color:#FFFFFF; display:inline-flex; align-items:center; justify-content:center;
    font-size:1.5rem; font-weight:800; margin-bottom:14px;
  }

  /* Eyebrow labels everywhere */
  .eyebrow {
    color:#6442BD; font-size:0.62rem; font-weight:700;
    letter-spacing:1.4px; text-transform:uppercase;
  }
</style>
""", unsafe_allow_html=True)

# ── Scenario definitions ──────────────────────────────────────────────────────

SCENARIOS = [
    {
        "id": "pre",
        "icon": "📋",
        "stage": "Pre-Campaign",
        "title": "Size a New Campaign",
        "question": (
            "I want to run a new Best Buy co-marketing campaign targeting New Purchasers "
            "— customers who have never bought on the app or checkout. We have around 200,000 "
            "eligible customers. How large does my test need to be, how long will it take to "
            "reach statistical significance, and what incremental revenue should I expect if we "
            "see a 15% lift over the historical baseline?"
        ),
    },
    {
        "id": "during",
        "icon": "📡",
        "stage": "During Campaign",
        "title": "Live Campaign Check",
        "question": (
            "Our App Deals email campaign launched January 25th and has been running for "
            "14 days. Treatment arm: 193,126 customers, 7.73% conversion rate. "
            "Control arm: 96,742 customers, 7.68% conversion rate. "
            "Are we statistically significant yet? If not, what specifically needs to change "
            "to get there — more users, longer run time, or different audience?"
        ),
    },
    {
        "id": "post",
        "icon": "✅",
        "stage": "Post-Campaign",
        "title": "Final Campaign Read",
        "question": (
            "The App Deals July 4th campaign has finished. "
            "Treatment: 140,197 customers, 9.03% CVR. "
            "Control: 69,823 customers, 8.65% CVR. "
            "Was the result statistically significant? What were the true incremental "
            "customers and revenue — and should we scale this campaign?"
        ),
    },
    {
        "id": "roi",
        "icon": "📊",
        "stage": "ROI Planning",
        "title": "Spend & ROI Matrix",
        "question": (
            "Show me the ROI planning matrix across all our CVR tiers. "
            "I want to see estimated spend, expected TTV, NTM increase, and ROI "
            "at different conversion rate scenarios — and tell me which scenario "
            "gives the best outcome and why."
        ),
    },
    {
        "id": "readme",
        "icon": "📖",
        "stage": "Formula Guide",
        "title": "How It All Works",
        "question": (
            "Can you explain all the formulas and methodology the agent uses? "
            "I want to understand: how statistical significance is calculated, "
            "what iCustomers and iTTV mean, how sample size is determined, "
            "what cannibalization rate tells us, and how the SCALE / EXTEND / "
            "ITERATE / STOP / RETHINK / WATCH recommendations are made."
        ),
    },
]

# ── Zip Co strategic goals (for executive report tab) ────────────────────────

ZIP_GOALS = [
    {
        "icon": "📱",
        "goal": "App Growth",
        "desc": "Drive incremental app installs and first purchases through co-marketing",
        "metric": "i_customers",
        "threshold": 50,
        "positive": "Contributes to new app customer activation targets",
        "negative": "Insufficient volume — review segment targeting or offer structure",
    },
    {
        "icon": "💰",
        "goal": "TTV & Revenue",
        "desc": "Increase total transaction value through incremental customer activation",
        "metric": "i_ttv",
        "threshold": 10_000,
        "positive": "Meaningful TTV contribution — supports quarterly GMV targets",
        "negative": "Insufficient TTV lift — consider higher AOV or broader segments",
    },
    {
        "icon": "📈",
        "goal": "NTM Efficiency",
        "desc": "Deliver positive net transaction margin on every incremental conversion",
        "metric": "roi_pct",
        "threshold": 100,
        "positive": "Unit economics confirmed — strong positive ROI per conversion",
        "negative": "ROI at risk — review incentive cost relative to conversion yield",
    },
    {
        "icon": "🤝",
        "goal": "Partner Confidence",
        "desc": "Prove brand partner co-marketing ROI to secure next campaign budget cycle",
        "metric": "is_sig",
        "threshold": True,
        "positive": "Statistical significance gives partners a data-backed case to reinvest",
        "negative": "Without significance, next partner cycle budget will be difficult to secure",
    },
]

NEXT_STEPS = {
    "SCALE": [
        "📣 Expand to full eligible audience — remove holdout, push to all qualified customers",
        "💰 Increase campaign budget proportionally to capture full audience at same ROI",
        "🤝 Share results deck with brand partner — strong ROI case for next co-marketing cycle",
        "📊 Set up ongoing monthly CVR tracking with this campaign as the new benchmark",
        "🎯 Build a look-alike audience from converters for v2 targeting",
    ],
    "GREENLIGHT": [
        "🚀 Launch the campaign — test is well-powered with a clear, testable hypothesis",
        "📅 Schedule a mid-point check at day 11 to assess early CVR signal",
        "📊 Set a significance alert: notify the team when |t-stat| crosses 1.645 (90% CI)",
        "🔒 Lock the audience on day 1 — no additions after go-live to maintain arm integrity",
        "📝 Document the baseline CVR before launch so the control arm is clean",
    ],
    "EXTEND": [
        "⏳ Extend the run window by 7–14 days — directional signal is positive, needs more time",
        "📊 Monitor t-statistic daily — stop early and call SCALE if it crosses 1.96",
        "👥 Do NOT add new users mid-test — it dilutes the significance calculation",
        "🔍 Check for cannibalization from concurrent campaigns running in the same segment",
        "📅 Set a hard stop date: if t-stat hasn't moved by day +14, re-evaluate the hypothesis",
    ],
    "ITERATE": [
        "✏️ Redesign the offer mechanic — current incentive may not be compelling enough",
        "🎯 Test a higher discount or cashback tier to unlock conversion in this segment",
        "📊 Run a new test with updated creative, measured against this baseline as control",
        "🔄 Consider a different audience segment — this cohort may be price-insensitive",
        "📝 Document learnings: what the data reveals about segment offer elasticity",
    ],
    "WATCH": [
        "👀 Monitor daily for the next 5 days — no action yet, let the test breathe",
        "📊 Review the 7-day rolling CVR delta every morning; escalate if no movement",
        "🔍 Ensure control group isolation — no other campaigns touching the same audience",
        "📅 Set a review date: if still no signal at 14 days, escalate to ITERATE",
        "📝 Capture baseline engagement metrics now for future comparison",
    ],
    "RETHINK": [
        "⚠️ Hypothesis needs revision — treatment underperformed control",
        "🎯 Audit the targeting: are we reaching the right customers at the right moment?",
        "💡 Workshop alternative offer structures with marketing and product teams",
        "📊 Analyse the control group's natural CVR — it may be unusually elevated",
        "🔄 Pause scaling plans — retest with revised hypothesis before committing further budget",
    ],
    "STOP": [
        "🛑 Stop the campaign — effect size is too small to ever reach significance",
        "💰 Reallocate budget to SCALE-ready campaigns in the current portfolio",
        "📝 Document the null result — it's a signal that this offer/segment doesn't pair well",
        "🎯 Review the targeting hypothesis: this segment may not respond to this offer type",
        "📊 Archive test parameters as a negative benchmark for future experiment design",
    ],
    "SIZE_AND_LAUNCH": [
        "📐 Validate the sample size calculation with your data science team before launch",
        "🗓️ Book the test slot in the campaign calendar — avoid seasonal or promotional overlap",
        "🔒 Brief the Braze team on holdout group configuration before go-live",
        "📊 Set up the measurement framework before launch, not after — agree on the primary metric",
        "🤝 Align with the brand partner on test timeline and reporting cadence",
    ],
}

# ── Session state ─────────────────────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []
if "verdict" not in st.session_state:
    st.session_state.verdict = {}
if "active_scenario" not in st.session_state:
    st.session_state.active_scenario = None
if "pending_question" not in st.session_state:
    st.session_state.pending_question = None
if "pre_mode" not in st.session_state:
    st.session_state.pre_mode = None   # None = chooser, "demo" = hard-coded, "new" = custom form

# ── Helpers ───────────────────────────────────────────────────────────────────

def render_tool_pill(name: str, input_data: dict):
    arg_str = ", ".join(f"{k}={repr(v)[:20]}" for k, v in list(input_data.items())[:2])
    st.markdown(f'<span class="tool-pill">⚙ <b>{name}</b>({arg_str})</span>', unsafe_allow_html=True)


def extract_verdict(text: str, tool_results: list) -> dict:
    v = dict(st.session_state.verdict)
    for result_str in tool_results:
        try:
            data = json.loads(result_str)
            if "is_significant" in data:
                v.update({
                    "is_sig": data.get("is_significant"),
                    "t_stat": data.get("t_statistic"),
                    "confidence": data.get("confidence_label", ""),
                    "recommendation": data.get("recommendation", ""),
                    "i_customers": data.get("i_customers"),
                    "i_ttv": data.get("i_ttv"),
                    "cannibalization": data.get("cannibalization_rate"),
                    "days_to_sig": data.get("days_to_sig"),
                })
            if "CVR_T_STAT" in data:
                v.update({
                    "is_sig": data.get("stat_sig"),
                    "t_stat": data.get("CVR_T_STAT"),
                    "i_customers": data.get("iCustomers"),
                    "i_ttv": data.get("iTTV"),
                    "campaign_name": data.get("display_name", data.get("name", "")),
                })
            if "required_n_per_arm" in data:
                v.update({
                    "is_sig": None,
                    "required_n": data.get("required_n_per_arm"),
                    "days_to_sig": data.get("estimated_days_to_sig"),
                    "expected_i_customers": data.get("expected_i_customers"),
                    "expected_i_ttv": data.get("expected_i_ttv"),
                })
            # ROI matrix result
            if "fixed_roi_pct" in data:
                scenarios = data.get("scenarios", [])
                # Pull NTM from highest CVR scenario
                best = max(scenarios, key=lambda s: s.get("cvr", 0)) if scenarios else {}
                min_sample = data.get("min_sample_by_lift", [])
                smallest = min_sample[0] if min_sample else {}
                v.update({
                    "is_sig": None,
                    "recommendation": "SIZE_AND_LAUNCH",
                    "roi_pct": data.get("fixed_roi_pct"),
                    "best_ntm": best.get("ntm_increase"),
                    "best_cvr": best.get("cvr_pct"),
                    "min_n_per_arm": smallest.get("n_per_arm"),
                    "min_lift_delta": smallest.get("lift_pp"),
                })
        except Exception:
            pass
    for rec in ["GREENLIGHT", "SCALE", "EXTEND", "ITERATE", "WATCH", "RETHINK", "STOP"]:
        if rec in text.upper():
            v["recommendation"] = rec
            break
    return v


def render_verdict_panel():
    v = st.session_state.verdict
    if not v:
        st.markdown("""
        <div class="verdict-card">
          <h4>Campaign Verdict</h4>
          <p style="color:#786D79; font-size:0.83rem; margin:8px 0 0 0; line-height:1.5;">
            Run a scenario or ask a question to see live analysis here.
          </p>
        </div>""", unsafe_allow_html=True)
        return

    is_sig = v.get("is_sig")
    sig_badge = ('<span class="badge-sig">🟢 SIGNIFICANT</span>' if is_sig is True else
                 '<span class="badge-nosig">🔴 NOT YET SIG</span>' if is_sig is False else
                 '<span class="badge-na">🟡 SIZING MODE</span>')

    rec = v.get("recommendation", "")
    rec_html = f'<span class="rec-badge rec-{rec}">{rec}</span>' if rec else ""
    name = v.get("campaign_name", "")
    name_html = f'<p class="verdict-title">{name}</p>' if name else ""

    st.markdown(f"""
    <div class="verdict-card">
      <h4>Campaign Verdict</h4>
      {name_html}{sig_badge} {rec_html}
    </div>""", unsafe_allow_html=True)

    metrics = []
    t = v.get("t_stat")
    if t is not None:
        cls = "metric-pos" if abs(t) >= 1.96 else ("metric-warn" if abs(t) >= 1.2 else "metric-neg")
        metrics.append((cls, "T-Statistic", f"{t:.3f}", "need |t| > 1.96 for 95% CI"))

    conf = v.get("confidence")
    if conf:
        metrics.append(("", "Confidence", conf, "of a real effect"))

    ic = v.get("i_customers")
    if ic is not None:
        metrics.append(("metric-pos" if ic > 0 else "metric-neg", "iCustomers", f"{ic:,}", "incremental converters"))

    it = v.get("i_ttv")
    if it is not None:
        metrics.append(("metric-pos" if it > 0 else "metric-neg", "Incremental TTV",
                        f"${abs(it):,.0f}", "generated by campaign"))

    eic = v.get("expected_i_customers")
    if eic is not None:
        metrics.append(("metric-pos", "Expected iCustomers", f"{eic:,}", "if 15% lift achieved"))

    eit = v.get("expected_i_ttv")
    if eit is not None:
        metrics.append(("metric-pos", "Expected iTTV", f"${eit:,.0f}", "projected revenue"))

    cn = v.get("cannibalization")
    if cn is not None:
        cls = "metric-pos" if cn < 0.4 else ("metric-warn" if cn < 0.6 else "metric-neg")
        metrics.append((cls, "Cannibalization", f"{cn*100:.1f}%", "organic share of conversions"))

    rn = v.get("required_n")
    if rn is not None:
        metrics.append(("", "Required N / Arm", f"{rn:,}", "for 80% power at 95% CI"))

    ds = v.get("days_to_sig")
    if ds is not None:
        label = "Est. Days to Sig" if is_sig is None else "Days Needed (at current rate)"
        metrics.append(("metric-warn", label, str(ds), "to reach significance"))

    # ROI matrix metrics
    roi = v.get("roi_pct")
    if roi is not None:
        metrics.append(("metric-pos", "Fixed ROI", f"{roi:.1f}%", "per incremental conversion"))

    best_ntm = v.get("best_ntm")
    best_cvr = v.get("best_cvr")
    if best_ntm is not None:
        metrics.append(("metric-pos", f"NTM @ {best_cvr or '15%'}", f"${best_ntm:,.0f}", "at highest CVR scenario"))

    min_n = v.get("min_n_per_arm")
    min_lift = v.get("min_lift_delta")
    if min_n is not None:
        metrics.append(("metric-warn", f"Min N/Arm ({min_lift})", f"{min_n:,}", "smallest detectable lift"))

    if metrics:
        html = '<div class="metric-row">'
        for cls, label, val, sub in metrics:
            html += f"""
            <div class="metric-box">
              <div class="metric-label">{label}</div>
              <div class="metric-value {cls}">{val}</div>
              <div class="metric-sub">{sub}</div>
            </div>"""
        html += "</div>"
        st.markdown(html, unsafe_allow_html=True)


def render_executive_report():
    """Executive summary report tab — what we did, results, and what's next."""
    v = st.session_state.verdict
    msgs = st.session_state.messages

    if not v:
        st.markdown("""
        <div class="empty-state" style="margin-top:18px;">
          <div class="empty-state-mark">📋</div>
          <div class="eyebrow" style="margin-bottom:6px;">No Report Yet</div>
          <div style="font-size:1.1rem;color:#1A0725;font-weight:700;">Run a campaign scenario first</div>
          <div style="font-size:0.82rem;margin-top:8px;color:#786D79;">
            Click any scenario button above, then switch back here for your executive report.
          </div>
        </div>""", unsafe_allow_html=True)
        return

    # ── Pull context ──────────────────────────────────────────────────────────
    rec          = v.get("recommendation", "")
    is_sig       = v.get("is_sig")
    t_stat       = v.get("t_stat")
    confidence   = v.get("confidence", "")
    i_customers  = v.get("i_customers")
    i_ttv        = v.get("i_ttv")
    cann         = v.get("cannibalization")
    campaign_name = v.get("campaign_name", "")
    days_to_sig  = v.get("days_to_sig")
    required_n   = v.get("required_n")
    roi_pct      = v.get("roi_pct")
    exp_ic       = v.get("expected_i_customers")
    exp_ittv     = v.get("expected_i_ttv")

    # Infer campaign stage
    if rec in ("SIZE_AND_LAUNCH", "GREENLIGHT"):
        stage, stage_icon, stage_color = "Pre-Campaign", "📋", "#6442BD"
    elif is_sig is False and t_stat is not None:
        stage, stage_icon, stage_color = "During Campaign", "📡", "#A55A00"
    else:
        stage, stage_icon, stage_color = "Post-Campaign", "✅", "#1B7E4F"

    # Last question as context
    last_q = next((m["content"] for m in reversed(msgs) if m["role"] == "user"
                   and isinstance(m["content"], str)), "")

    from datetime import date
    today = date.today().strftime("%B %d, %Y")

    # ── Report header ─────────────────────────────────────────────────────────
    st.markdown(f"""
    <div style="background:#FFFFFF;border:1px solid #E1E0DF;border-radius:14px;
                padding:22px 28px;margin-bottom:18px;
                box-shadow:0 1px 3px rgba(26,7,37,0.06);">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;">
        <div>
          <div class="eyebrow">Zip Co · Growth Analytics</div>
          <div style="font-size:1.25rem;font-weight:800;color:#1A0725;margin:4px 0 2px 0;
                      letter-spacing:-0.4px;">📋 Executive Campaign Report</div>
          <div style="color:#786D79;font-size:0.78rem;">Generated {today} · Campaign Intelligence Agent</div>
        </div>
        <div style="text-align:right;">
          <span style="background:{stage_color}18;color:{stage_color};border:1px solid {stage_color};
                       padding:5px 12px;border-radius:20px;font-size:0.7rem;font-weight:700;
                       letter-spacing:0.8px;">{stage_icon} {stage.upper()}</span>
        </div>
      </div>
      {f'<div style="margin-top:12px;padding:10px 14px;background:#F5F4F2;border-radius:8px;font-size:0.8rem;color:#786D79;font-style:italic;">&ldquo;{last_q[:200]}{"…" if len(last_q)>200 else ""}&rdquo;</div>' if last_q else ""}
    </div>""", unsafe_allow_html=True)

    # ── Section 1: Statistical results ───────────────────────────────────────
    st.markdown('<div class="eyebrow" style="margin-bottom:8px;">1 · Statistical Results</div>',
                unsafe_allow_html=True)

    sig_color = "#1B7E4F" if is_sig else ("#B43A3A" if is_sig is False else "#786D79")
    sig_label = "🟢 SIGNIFICANT" if is_sig else ("🔴 NOT YET SIG" if is_sig is False else "🟡 SIZING MODE")

    stat_cols = st.columns(4)
    def _stat_tile(col, label, value, sub="", color="#1A0725"):
        col.markdown(f"""
        <div class="metric-box">
          <div class="metric-label">{label}</div>
          <div class="metric-value" style="color:{color};">{value}</div>
          <div class="metric-sub">{sub}</div>
        </div>""", unsafe_allow_html=True)

    _stat_tile(stat_cols[0], "Significance", sig_label, "two-proportion Z-test", sig_color)
    _stat_tile(stat_cols[1], "T-Statistic",
               f"{t_stat:.3f}" if t_stat is not None else "—",
               "need |t| > 1.96 for 95% CI",
               "#1B7E4F" if t_stat and abs(t_stat) >= 1.96 else ("#A55A00" if t_stat else "#786D79"))
    _stat_tile(stat_cols[2], "Confidence Level",
               confidence or (f"~{int(min(99,max(50,abs(t_stat or 0)*40)))}%" if t_stat else "—"),
               "of a real incremental effect")
    _stat_tile(stat_cols[3], "Recommendation",
               rec or "—", "based on t-stat + cannibalization",
               "#1B7E4F" if rec in ("SCALE","GREENLIGHT") else
               ("#A55A00" if rec in ("EXTEND","ITERATE","WATCH") else
                "#B43A3A" if rec in ("RETHINK","STOP") else "#6442BD"))

    # ── Derived metrics (used across sections 2–4) ────────────────────────────
    ic_val    = i_customers if i_customers is not None else exp_ic
    ittv_val  = i_ttv       if i_ttv       is not None else exp_ittv
    ic_label  = "iCustomers"       if i_customers is not None else "Expected iCustomers"
    ittv_label = "Incremental TTV" if i_ttv       is not None else "Expected iTTV"
    actual_roi    = roi_pct or 424.3
    incr_pct      = (1 - cann) * 100           if cann is not None else None
    per_cust      = ittv_val / ic_val           if (ittv_val and ic_val and ic_val > 0) else None
    net_margin    = 126.50 * 0.4144 - 10        # fixed Zip unit economics: $42.42 net per conversion
    t_str         = f"{t_stat:.3f} ({confidence})" if t_stat is not None else "—"
    ic_str        = f"{ic_val:,}"              if ic_val   is not None else "—"
    ittv_str      = f"${ittv_val:,.0f}"        if ittv_val is not None else "—"
    req_n_str     = f"{required_n:,}"          if required_n is not None else "—"
    exp_ic_str    = f"{exp_ic:,}"              if exp_ic   is not None else "—"
    exp_ittv_str  = f"${exp_ittv:,.0f}"        if exp_ittv is not None else "—"

    # ── Section 2: Business impact ────────────────────────────────────────────
    st.markdown('<div class="eyebrow" style="margin:18px 0 8px 0;">2 · Business Impact</div>',
                unsafe_allow_html=True)

    impact_cols = st.columns(4)

    # iCustomers — show with % incremental context
    ic_sub = (f"{incr_pct:.0f}% truly incremental · {100-incr_pct:.0f}% cannibalized"
              if incr_pct is not None
              else ("expected if hypothesis holds" if i_customers is None else "incremental converters"))
    ic_display = (f"{ic_val:+,} ({incr_pct:.0f}% incr.)" if (ic_val and incr_pct)
                  else (f"{ic_val:+,}" if ic_val is not None else "—"))

    # iTTV — show with per-customer value
    ittv_sub = (f"${per_cust:.0f} avg per iCustomer · {actual_roi:.0f}% ROI"
                if per_cust else
                ("projected at $163 avg TTV/conversion" if i_ttv is None else "total incremental TTV"))
    ittv_display = (f"${abs(ittv_val):,.0f} (${per_cust:.0f}/cust)" if (ittv_val and per_cust)
                    else (f"${abs(ittv_val):,.0f}" if ittv_val is not None else "—"))

    _stat_tile(impact_cols[0], ic_label, ic_display, ic_sub,
               "#1B7E4F" if ic_val and ic_val > 0 else "#786D79")
    _stat_tile(impact_cols[1], ittv_label, ittv_display, ittv_sub,
               "#1B7E4F" if ittv_val and ittv_val > 0 else "#786D79")
    _stat_tile(impact_cols[2], "Cannibalization",
               f"{cann*100:.1f}% ({incr_pct:.0f}% net-new)" if cann is not None and incr_pct else
               (f"{cann*100:.1f}%" if cann is not None else "—"),
               "organic share of all conversions",
               "#1B7E4F" if cann is not None and cann < 0.4 else
               "#A55A00" if cann is not None and cann < 0.6 else "#B43A3A")
    if roi_pct is not None or days_to_sig is None:
        _stat_tile(impact_cols[3], "Fixed ROI", f"{actual_roi:.1f}%",
                   f"${net_margin:.2f} net margin per conversion", "#1B7E4F")
    elif days_to_sig:
        _stat_tile(impact_cols[3], "Days to Significance", str(days_to_sig),
                   "at current daily conversion rate", "#A55A00")
    elif required_n:
        _stat_tile(impact_cols[3], "Required N / Arm", req_n_str,
                   "for 80% power at 95% CI", "#A55A00")

    # ── Section 3: Strategic alignment with Zip Co goals ─────────────────────
    st.markdown('<div class="eyebrow" style="margin:18px 0 8px 0;">3 · Strategic Alignment — Zip Co Growth Agenda</div>',
                unsafe_allow_html=True)

    goal_html = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:4px;">'
    for g in ZIP_GOALS:
        mk  = g["metric"]
        val = v.get(mk)

        if mk == "is_sig":
            if val is True:
                light = "🟢"
                stat_line = f"t = {t_str} → statistically confirmed"
                msg = g["positive"]
            elif val is False:
                light = "🔴"
                stat_line = f"t = {t_str} (need |t| > 1.96 for 95% CI)"
                msg = g["negative"]
            else:
                light = "🟡"
                stat_line = "Significance to be measured post-launch"
                msg = "Sizing mode — significance will be assessed once the test runs"
        elif mk == "roi_pct":
            display_roi = val or actual_roi
            light = "🟢"
            stat_line = f"{display_roi:.1f}% ROI · ${net_margin:.2f} net per incremental conversion"
            msg = g["positive"]
        elif mk == "i_customers":
            ic_use = val if val is not None else v.get("expected_i_customers")
            if ic_use is None:
                light, stat_line, msg = "🟡", "No data yet", "Run the scenario to populate"
            else:
                pct_incr = f" ({incr_pct:.0f}% truly incremental)" if incr_pct else ""
                light = "🟢" if ic_use >= g["threshold"] * 2 else ("🟡" if ic_use >= g["threshold"] else "🔴")
                stat_line = f"+{ic_use:,} iCustomers{pct_incr}"
                msg = g["positive"] if ic_use >= g["threshold"] else g["negative"]
        elif mk == "i_ttv":
            ittv_use = val if val is not None else v.get("expected_i_ttv")
            if ittv_use is None:
                light, stat_line, msg = "🟡", "No data yet", "Run the scenario to populate"
            else:
                pc_str = f" (${per_cust:.0f}/iCustomer)" if per_cust else ""
                light = "🟢" if ittv_use >= g["threshold"] * 2 else ("🟡" if ittv_use >= g["threshold"] else "🔴")
                stat_line = f"+${ittv_use:,.0f} iTTV{pc_str}"
                msg = g["positive"] if ittv_use >= g["threshold"] else g["negative"]
        else:
            light, stat_line, msg = "🟡", "—", g["positive"]

        goal_html += f"""
        <div style="background:#FFFFFF;border:1px solid #E1E0DF;border-radius:10px;padding:12px 14px;">
          <div style="font-size:1.1rem;margin-bottom:4px;">{light}</div>
          <div style="font-size:0.72rem;font-weight:700;color:#1A0725;margin-bottom:2px;">
            {g['icon']} {g['goal']}
          </div>
          <div style="font-size:0.78rem;font-weight:700;color:#411260;margin-bottom:4px;">{stat_line}</div>
          <div style="font-size:0.68rem;color:#786D79;">{msg}</div>
        </div>"""
    goal_html += "</div>"
    st.markdown(goal_html, unsafe_allow_html=True)

    # ── Section 4: Data-driven next steps ─────────────────────────────────────
    st.markdown('<div class="eyebrow" style="margin:18px 0 8px 0;">4 · Recommended Next Steps</div>',
                unsafe_allow_html=True)

    # Generate steps with actual numbers
    def _steps_for_rec(rec: str) -> list[str]:
        if rec == "SCALE":
            return [
                f"📣 Scale budget to the full eligible audience — at {actual_roi:.0f}% ROI, each additional activation returns <b>${net_margin:.2f} net margin</b>",
                f"💰 Current result: <b>{ic_str} iCustomers</b>, <b>{ittv_str} iTTV</b>"
                f"{f' ({incr_pct:.0f}% truly incremental)' if incr_pct is not None else ''}"
                f" — proportional scaling should multiply these figures",
                f"🤝 Share <b>t = {t_str}</b> result with brand partner — {confidence} confidence is the data package needed to unlock the next co-marketing budget cycle",
                f"📊 Set <b>{confidence} CI</b> (t = {f'{t_stat:.3f}' if t_stat is not None else '—'}) as the performance benchmark — reject any future test that doesn't clear this bar",
                f"🎯 Seed v2 look-alike from the <b>{ic_str} incremental converters</b> ({incr_pct:.0f}% net-new · {100-incr_pct:.0f}% cannibalized)" if incr_pct is not None else
                f"🎯 Seed v2 look-alike from the {ic_str} incremental converters — highest-propensity customers as v2 seed audience",
            ]
        if rec == "GREENLIGHT":
            return [
                f"🚀 Launch — you need <b>{req_n_str} per arm</b> ({required_n*2:,} total) to detect the target lift with 80% power at 95% CI" if required_n else
                "🚀 Launch the test — well-powered with a clear, measurable hypothesis",
                f"📅 Schedule the mid-point check at <b>day {(days_to_sig or 22) // 2}</b> — if |t| < 1.0 at that point, prepare to stop early",
                f"📊 Set a significance alert at |t| = <b>1.645 (90% CI)</b> as early signal; call the test at <b>1.96 (95% CI)</b>",
                f"🎯 If hypothesis holds: expect <b>+{exp_ic_str} iCustomers</b> and <b>+{exp_ittv_str} iTTV</b> over ~{days_to_sig or 22} days" if (exp_ic or exp_ittv) else
                f"🎯 Document expected lift %: align with partner on success metrics before launch to avoid post-hoc disputes",
                "🔒 Lock audience on day 1 — no additions or removals after go-live; it invalidates the significance calculation",
            ]
        if rec == "EXTEND":
            return [
                f"⏳ Extend <b>7–14 more days</b> — current t = <b>{t_str}</b>, needs 1.96 for 95% CI; signal is directionally positive",
                f"📊 Monitor t-statistic daily — stop early and call <b>SCALE</b> the moment it crosses 1.96 (don't wait for planned end date)",
                f"📅 Set a hard stop date: if t-stat hasn't moved by day +14, reclassify as <b>STOP</b> — don't let sunk-cost bias extend indefinitely",
                f"👥 Do <b>not</b> add new users mid-test — it resets the variance calculation and inflates the required sample size",
                f"🔍 Check for audience bleed: verify no overlapping campaigns are hitting the <b>control arm</b> in this segment",
            ]
        if rec == "STOP":
            n_days = days_to_sig or 608
            opp_cost = int(n_days * (ittv_val / 14 if ittv_val else 3200))
            return [
                f"🛑 Stop now — t = <b>{t_str}</b>, would need ~<b>{n_days} more days</b> at this effect size to reach significance",
                f"💰 Opportunity cost of running to planned end date: ~<b>${opp_cost:,.0f}</b> in foregone iTTV that could fund a winning concept",
                f"🔄 Redirect this audience (currently at <b>{ic_str} iCustomers</b>) to the highest-performing campaign in the portfolio",
                f"📝 Document the null result: this segment's baseline CVR is near its ceiling — the offer mechanic isn't the unlock",
                f"📊 Archive t = {t_str} as the negative benchmark; require any replacement test to show |t| > 0.8 within 7 days as a viability gate",
            ]
        if rec in ("RETHINK",):
            return [
                f"⚠️ Hypothesis needs revision — treatment underperformed control at t = <b>{t_str}</b>",
                f"🎯 Audit targeting: the {ic_str} negative iCustomers signal suggests the offer may be repelling otherwise-converting customers",
                f"💡 Workshop a higher-value offer: if current mechanic doesn't clear {confidence} CI, try a {actual_roi:.0f}%+ ROI-preserving alternative",
                f"📊 Run a diagnostic holdout for 3 days with a new creative variant before committing to a full retest",
                f"🔄 Pause all scaling plans — do not invest further until a revised hypothesis clears at least <b>90% CI (t > 1.645)</b>",
            ]
        if rec == "SIZE_AND_LAUNCH":
            return [
                f"📐 Validate sizing: <b>{req_n_str} per arm</b> ({required_n*2:,} total) for 80% power at 95% CI, ~<b>{days_to_sig or 22} days</b> to significance" if required_n else
                "📐 Confirm sample size calculation with the data science team before launch",
                f"🎯 Expected outcome if hypothesis holds: <b>+{exp_ic_str} iCustomers</b>, <b>+{exp_ittv_str} iTTV</b> at {actual_roi:.0f}% ROI",
                f"📅 Book the test slot in the campaign calendar — avoid BFCM, major holidays, or any concurrent campaign touching this segment",
                f"🔒 Brief the Braze team on holdout group configuration — the <b>{required_n:,}-per-arm</b> split must be enforced on day 1" if required_n else
                "🔒 Brief Braze on holdout group configuration before go-live",
                f"📊 Agree on the primary metric and success threshold before launch — propose <b>95% CI (t > 1.96)</b> as the call criterion",
            ]
        # Default: WATCH / ITERATE
        return [
            f"👀 Monitor daily — current t = <b>{t_str}</b>; no action until signal emerges",
            f"📊 Review rolling 7-day CVR delta each morning; escalate if it hasn't moved by day 14",
            f"🔍 Ensure control group isolation — verify no other campaigns are touching the same audience segment",
            f"📅 Set a review date: escalate to <b>ITERATE</b> (redesign offer) if still no signal after 14 days",
            f"📝 Capture the current baseline as the benchmark for any future test in this segment",
        ]

    steps = _steps_for_rec(rec)
    rec_color = ("#1B7E4F" if rec in ("SCALE","GREENLIGHT") else
                 "#A55A00" if rec in ("EXTEND","ITERATE","WATCH","SIZE_AND_LAUNCH") else
                 "#B43A3A")
    rec_bg    = ("#E8F3EC" if rec in ("SCALE","GREENLIGHT") else
                 "#FBF2E5" if rec in ("EXTEND","ITERATE","WATCH","SIZE_AND_LAUNCH") else
                 "#FBEAEA")

    steps_html = f"""
    <div style="background:{rec_bg};border:1px solid {rec_color};border-radius:12px;
                padding:16px 20px;margin-bottom:4px;">
      <div style="font-size:0.72rem;font-weight:700;color:{rec_color};letter-spacing:0.8px;
                  text-transform:uppercase;margin-bottom:10px;">
        Playbook: {rec}
      </div>
      <ol style="margin:0;padding-left:18px;">"""
    for step in steps:
        steps_html += f'<li style="margin:7px 0;font-size:0.82rem;color:#1A0725;line-height:1.55;">{step}</li>'
    steps_html += "</ol></div>"
    st.markdown(steps_html, unsafe_allow_html=True)

    # ── Section 5: Stakeholder explainer ─────────────────────────────────────
    with st.expander("📖  How to read this report — plain-language guide for stakeholders", expanded=False):
        st.markdown(f"""
<div style="font-size:0.84rem;color:#1A0725;line-height:1.7;">

### What are we actually measuring?

Every campaign we run is split into two groups: a **Target (treatment) arm** that receives the
offer, and a **Control arm** that doesn't. The difference in conversion rate between those two
groups is the raw signal we analyse.

The challenge is simple: **was the difference real, or just random chance?** The metrics below
answer that question.

---

### 🔢 The key numbers — what they mean

| Metric | Plain-language meaning | What to look for |
|---|---|---|
| **T-Statistic** | A score that measures how "loud" the signal is compared to random noise. Think of it like a signal-to-noise ratio. | **\|t\| > 1.96** = 95% sure the effect is real. The current result is **t = {f"{t_stat:.3f}" if t_stat is not None else "—"}**. |
| **Confidence Level** | How certain we are that the lift is real and not a fluke. | **95%+** is our call threshold. **99%** means we're very confident. Current: **{confidence or "sizing mode"}**. |
| **iCustomers** | Incremental customers — the number of people who *only converted because of our campaign*. Not every conversion counts; customers who would have purchased anyway are excluded. | Higher is better. Current result: **{ic_str}**. |
| **Incremental TTV** | The extra transaction value *created by the campaign* after subtracting what would have happened organically. | Higher is better. Current: **{ittv_str}**. |
| **Cannibalization Rate** | The % of conversions in the target arm that would have happened *without* the campaign. A 46% cannibalization rate means 54% of conversions were genuinely new. | **Below 40%** is healthy. **Above 60%** means the campaign is mostly taking credit for organic behaviour. Current: **{f"{cann*100:.1f}%" if cann is not None else "—"}**. |
| **ROI %** | Return on the incentive spend. A 424% ROI means for every $10 we spend on incentives, we get $52.43 in gross revenue back — or $42.43 net. | Anything **above 100%** is profitable. Zip's fixed unit economics give us **{actual_roi:.0f}% ROI** per incremental conversion at current AOV and margins. |

---

### 🚦 What do the traffic lights mean?

| Light | Meaning |
|---|---|
| 🟢 **Green** | The metric is tracking well — at or above the target threshold. Good news for stakeholders. |
| 🟡 **Amber** | The metric is borderline, the campaign is in sizing mode, or we don't have enough data yet. Monitor and revisit. |
| 🔴 **Red** | The metric is below threshold or the result is not statistically significant. Action is needed before investing further. |

---

### 📋 What do the recommendations mean?

| Recommendation | What it means for budget & planning |
|---|---|
| 🟢 **SCALE** | Results are statistically confirmed. Expand audience and budget — the recipe works. |
| 🟢 **GREENLIGHT** | The test design is solid. Approve launch — the sample size and timeline are well-powered. |
| 🟡 **EXTEND** | Signal is directionally positive but not yet significant. Run longer before deciding. |
| 🟡 **ITERATE** | The idea has merit but execution needs adjustment. Redesign the offer or audience before scaling. |
| 🟡 **WATCH** | Too early to call. No action — check back in 7 days. |
| 🔴 **RETHINK** | The campaign underperformed control. Pause investment; revisit the hypothesis. |
| 🔴 **STOP** | The lift isn't there and more time won't fix it. Cut losses and reallocate to winning campaigns. |

---

### 💡 Why does this matter to Zip Co?

Every dollar we spend on campaign incentives competes with other growth investments. This
framework ensures we only **scale campaigns that are provably incremental** — not ones that
look good on a dashboard but are really just crediting conversions that were going to happen
anyway. The iCustomers and cannibalization metrics are what separate a real win from a
vanity metric.

</div>""", unsafe_allow_html=True)

    # ── Footer ────────────────────────────────────────────────────────────────
    st.markdown(f"""
    <div style="margin-top:18px;padding:12px 16px;border-top:1px solid #E1E0DF;
                display:flex;justify-content:space-between;align-items:center;">
      <div style="font-size:0.7rem;color:#8B858E;">
        Zip Co · Growth Analytics · Campaign Intelligence Agent · {today}
      </div>
      <div style="font-size:0.7rem;color:#8B858E;">
        Data: 40 Braze BAU campaigns · Two-proportion Z-test · 95% CI threshold
      </div>
    </div>""", unsafe_allow_html=True)


# ── Layout ────────────────────────────────────────────────────────────────────

_now = datetime.now().strftime("%d %b %Y · %H:%M")
try:
    _last_author = subprocess.check_output(
        ["git", "log", "-1", "--pretty=format:%an"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        stderr=subprocess.DEVNULL,
    ).decode().strip() or "—"
    _last_datetime = subprocess.check_output(
        ["git", "log", "-1", "--pretty=format:%ad", "--date=format:%d %b %Y · %H:%M"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        stderr=subprocess.DEVNULL,
    ).decode().strip() or _now
except Exception:
    _last_author, _last_datetime = "—", _now
st.markdown(f"""
<div class="zip-header">
  <div class="zip-logo-wrap">
    <!-- Official Zip Co wordmark — pulled directly from zip.co -->
    <div class="zip-wordmark">{ZIP_WORDMARK_SVG}</div>
    <div class="zip-pipe"></div>
    <div>
      <div class="zip-eyebrow">Growth Analytics</div>
      <div class="zip-logo">Campaign Intelligence<span class="dot">.</span></div>
      <div class="zip-subtitle">A/B Testing &amp; Incrementality Agent · Zip Co</div>
    </div>
  </div>
  <div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px;">
    <span class="zip-badge">● Live Demo</span>
    <span style="color:#786D79;font-size:0.68rem;letter-spacing:0.3px;">🕐 Last updated by: <b style="color:#411260;">{_last_author}</b> · {_last_datetime}</span>
  </div>
</div>
""", unsafe_allow_html=True)

# Scenario buttons row
c1, c2, c3, c4, c5 = st.columns(5)
for col, sc in zip([c1, c2, c3, c4, c5], SCENARIOS):
    with col:
        active = "🔵 " if st.session_state.active_scenario == sc["id"] else ""
        if st.button(f"{sc['icon']} {active}{sc['stage']}: {sc['title']}", key=f"sc_{sc['id']}"):
            if sc["id"] == "pre":
                # PRE opens a chooser — don't fire the question yet
                st.session_state.active_scenario = "pre"
                st.session_state.pre_mode = None
            else:
                st.session_state.pending_question = sc["question"]
                st.session_state.active_scenario  = sc["id"]
                st.session_state.pre_mode = None
            st.rerun()

# ── PRE-CAMPAIGN CHOOSER (shown when PRE button is active) ────────────────────
_SEGMENT_OPTIONS = {
    "App Deals  ·  8.94% baseline":            ("App_Deals",            0.0894),
    "Best Buy New Purchasers  ·  1.06%":        ("Best_Buy_New",         0.01056),
    "Fashion Nova Loyalist  ·  6.00%":          ("Fashion_Nova_Loyalist", 0.0600),
    "App Deals Seasonal  ·  8.00%":             ("App_Deals_Seasonal",    0.0800),
    "App Deals High Intent  ·  10.00%":         ("App_Deals_High_Intent", 0.1000),
    "BAU Billpay  ·  20.79%":                   ("BAU_Billpay",           0.2079),
    "Custom (enter baseline manually)":          ("Custom",               0.05),
}

if st.session_state.active_scenario == "pre":
    st.markdown("""
    <div style="background:#FFFFFF;border:1px solid #D6D4D2;border-radius:12px;
                padding:18px 22px;margin:10px 0 6px 0;">
      <div class="eyebrow" style="margin-bottom:10px;">📋 Pre-Campaign — choose your path</div>
    </div>""", unsafe_allow_html=True)

    demo_col, divider_col, new_col = st.columns([5, 1, 6])

    with demo_col:
        st.markdown("""
        <div style="background:#F5F4F2;border:1px solid #E1E0DF;border-radius:10px;
                    padding:14px 16px;height:100%;">
          <div style="font-size:0.8rem;font-weight:700;color:#1A0725;margin-bottom:4px;">
            📋 Best Buy Demo
          </div>
          <div style="font-size:0.74rem;color:#786D79;line-height:1.5;">
            Run the pre-loaded Best Buy New Purchasers scenario with real historical data
            — instantly shows sizing, days to significance, and expected iTTV.
          </div>
        </div>""", unsafe_allow_html=True)
        st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
        if st.button("▶ Run Best Buy Demo", key="pre_run_demo", use_container_width=True):
            pre_sc = next(s for s in SCENARIOS if s["id"] == "pre")
            st.session_state.pending_question = pre_sc["question"]
            st.session_state.pre_mode = "demo"
            st.rerun()

    with divider_col:
        st.markdown("""
        <div style="display:flex;justify-content:center;align-items:center;height:100%;
                    padding-top:20px;">
          <div style="color:#D6D4D2;font-size:1.1rem;font-weight:300;">or</div>
        </div>""", unsafe_allow_html=True)

    with new_col:
        st.markdown("""
        <div style="background:#EFE9FA;border:1px solid #6442BD;border-radius:10px;
                    padding:14px 16px;">
          <div style="font-size:0.8rem;font-weight:700;color:#411260;margin-bottom:4px;">
            🆕 Size a New Campaign
          </div>
          <div style="font-size:0.74rem;color:#6442BD;line-height:1.5;">
            Answer 3 questions and the agent will calculate exactly what you need.
          </div>
        </div>""", unsafe_allow_html=True)

        with st.form("new_campaign_sizer", clear_on_submit=False):
            camp_name = st.text_input("Campaign name (optional)",
                                      placeholder="e.g. Spring BNPL Promo")
            seg_label = st.selectbox("What segment are you targeting?",
                                     list(_SEGMENT_OPTIONS.keys()))
            seg_key, auto_baseline = _SEGMENT_OPTIONS[seg_label]

            pop = st.number_input("How many eligible customers do you have?",
                                  min_value=1_000, max_value=10_000_000,
                                  value=100_000, step=5_000,
                                  format="%d")
            lift_pct = st.select_slider("What conversion lift are you targeting?",
                                        options=[5, 10, 15, 20, 25, 30],
                                        value=15,
                                        format_func=lambda x: f"+{x}%")

            # Editable baseline — auto-filled from segment
            baseline_input = st.number_input(
                f"Baseline CVR % (auto-filled from segment)",
                min_value=0.1, max_value=50.0,
                value=round(auto_baseline * 100, 2),
                step=0.1, format="%.2f"
            )

            submitted = st.form_submit_button("🔍 Size this campaign →",
                                              use_container_width=True)
            if submitted:
                name_str = camp_name.strip() or seg_label.split("·")[0].strip()
                baseline_cvr = baseline_input / 100
                target_cvr   = baseline_cvr * (1 + lift_pct / 100)
                question = (
                    f"[CUSTOM_SIZING] "
                    f"Campaign: {name_str} | Segment: {seg_key} | "
                    f"Population: {int(pop)} | Lift: {lift_pct}% | "
                    f"Baseline CVR: {baseline_cvr:.5f}\n\n"
                    f"I want to size a new **{name_str}** campaign targeting the "
                    f"{seg_key.replace('_', ' ')} segment. We have **{int(pop):,} eligible customers**. "
                    f"What sample size do I need, how long will it take to reach statistical "
                    f"significance, and what incremental customers and TTV should I expect "
                    f"if we see a **{lift_pct}% relative lift** over the "
                    f"**{baseline_cvr*100:.2f}% historical baseline CVR**?"
                )
                st.session_state.pending_question = question
                st.session_state.pre_mode = "new"
                st.rerun()

st.markdown("<hr>", unsafe_allow_html=True)

tab_chat, tab_report = st.tabs(["💬 Campaign Analysis", "📋 Executive Report"])

with tab_chat:
  left, right = st.columns([3, 1], gap="large")

  with right:
    render_verdict_panel()
    use_mock = os.getenv("USE_MOCK_DATA", "").lower() == "true" or not os.getenv("TABLEAU_PAT_NAME")
    dot_color = '#1B7E4F' if not use_mock else '#6442BD'
    label = 'Tableau Live' if not use_mock else 'Real Campaign Snapshot'
    st.markdown(f"""
    <div style="background:#FFFFFF;border:1px solid #E1E0DF;border-radius:10px;padding:12px 14px;margin-top:4px;
                box-shadow:0 1px 2px rgba(26,7,37,0.04);">
      <div class="eyebrow">Data Source</div>
      <div style="color:#1A0725;font-size:0.85rem;font-weight:700;margin-top:5px;">
        <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{dot_color};margin-right:6px;"></span>
        {label}
      </div>
      <div style="color:#8B858E;font-size:0.7rem;margin-top:4px;">
        40 real Braze BAU campaigns · Scraped 2026-05-13
      </div>
    </div>""", unsafe_allow_html=True)

  with left:
      # ── INPUT: moved to TOP, sticky-feeling location ──────────────────────
      inp_col, btn_col = st.columns([5, 1])
      with inp_col:
          user_input = st.text_input("", key="chat_input",
                                     placeholder="Ask about any campaign, stat sig, sizing…",
                                     label_visibility="collapsed")
      with btn_col:
          send = st.button("Send ↑", key="send_btn")

      # Resolve which question to run this turn (button click or scenario button)
      question = st.session_state.pop("pending_question", None) or (
          user_input.strip() if send and user_input.strip() else None
      )

      # If a new question was just asked, push it into messages BEFORE rendering
      # so it appears immediately in the (reversed) history with a streaming slot.
      if question:
          st.session_state.messages.append({"role": "user", "content": question})

      # Small controls row: turn count + clear-history
      if st.session_state.messages:
          hdr_a, hdr_b = st.columns([4, 1])
          with hdr_a:
              n_turns = sum(1 for m in st.session_state.messages if m["role"] == "user")
              st.markdown(
                  f'<div style="margin:14px 0 6px 0;"><span class="eyebrow">Chat history · {n_turns} turn{"s" if n_turns != 1 else ""} · newest on top</span></div>',
                  unsafe_allow_html=True,
              )
          with hdr_b:
              if st.button("Clear", key="clear_btn"):
                  st.session_state.messages = []
                  st.session_state.verdict  = {}
                  st.session_state.active_scenario = None
                  st.rerun()

      # ── Render messages, NEWEST TURN FIRST ─────────────────────────────────
      if not st.session_state.messages:
          _logo = (
              f'<img src="data:image/png;base64,{ZIP_SQUARE_LOGO_B64}" alt="Zip" '
              f'style="width:54px;height:54px;border-radius:14px;'
              f'box-shadow:0 2px 6px rgba(26,7,37,0.12);margin-bottom:14px;"/>'
              if ZIP_SQUARE_LOGO_B64
              else '<div class="empty-state-mark">Z</div>'
          )
          st.markdown(f"""
          <div class="empty-state" style="margin-top:18px;">
            {_logo}
            <div class="eyebrow" style="margin-bottom:6px;">Ready</div>
            <div style="font-size:1.1rem;color:#1A0725;font-weight:700;">
              Ask about any Braze campaign
            </div>
            <div style="font-size:0.82rem;margin-top:8px;color:#786D79;">
              Click a scenario above or type a question in the box above
            </div>
          </div>""", unsafe_allow_html=True)
      else:
          # Group messages into turns: each user message starts a new turn
          turns: list[list[dict]] = []
          current: list[dict] = []
          for m in st.session_state.messages:
              if m["role"] == "user":
                  if current:
                      turns.append(current)
                  current = [m]
              else:
                  current.append(m)
          if current:
              turns.append(current)

          # Stream-placeholder context for the *newest* turn if we just received a question
          stream_ctx: dict | None = None

          # Render newest first
          for idx_rev, turn in enumerate(reversed(turns)):
              is_newest     = (idx_rev == 0)
              turn_number   = len(turns) - idx_rev
              has_assistant = any(m["role"] == "assistant" for m in turn)

              # Turn divider (above every non-newest turn)
              if idx_rev > 0:
                  st.markdown(
                      '<hr style="border:none;border-top:1px dashed #D6D4D2;margin:22px 0 16px 0;">',
                      unsafe_allow_html=True,
                  )
              # Turn label
              label_color = "#6442BD" if is_newest else "#8B858E"
              label_text  = f"Turn {turn_number}" + ("  ·  newest" if is_newest else "")
              st.markdown(
                  f'<div style="color:{label_color};font-size:0.62rem;font-weight:700;'
                  f'letter-spacing:1.4px;text-transform:uppercase;margin:4px 0 6px 0;">'
                  f'{label_text}</div>',
                  unsafe_allow_html=True,
              )

              # Render messages within the turn (user first, then assistant)
              for m in turn:
                  if m["role"] == "user":
                      content = m["content"] if isinstance(m["content"], str) else str(m["content"])
                      st.markdown(f'<div class="msg-user">{content}</div>', unsafe_allow_html=True)
                  elif m["role"] == "assistant":
                      if isinstance(m["content"], list):
                          for block in m["content"]:
                              if isinstance(block, dict):
                                  if block.get("type") == "text" and block.get("text"):
                                      st.markdown(
                                          f'<div class="msg-agent">{render_md(block["text"])}</div>',
                                          unsafe_allow_html=True,
                                      )
                                  elif block.get("type") == "tool_use":
                                      render_tool_pill(block["name"], block.get("input", {}))
                      elif isinstance(m["content"], str):
                          st.markdown(
                              f'<div class="msg-agent">{render_md(m["content"])}</div>',
                              unsafe_allow_html=True,
                          )

              # If this is the newest turn AND there's no assistant response yet,
              # create the streaming placeholder right here.
              if is_newest and not has_assistant and question:
                  stream_ctx = {"placeholder": st.empty()}

      # ── Streaming dispatch ────────────────────────────────────────────────
      if question and stream_ctx is not None:
          agent_msgs = []
          for m in st.session_state.messages:
              if m["role"] == "user":
                  agent_msgs.append({
                      "role": "user",
                      "content": m["content"] if isinstance(m["content"], str) else str(m["content"]),
                  })
              elif m["role"] == "assistant":
                  txt = ""
                  if isinstance(m["content"], list):
                      txt = " ".join(b.get("text", "") for b in m["content"]
                                     if isinstance(b, dict) and b.get("type") == "text")
                  elif isinstance(m["content"], str):
                      txt = m["content"]
                  if txt:
                      agent_msgs.append({"role": "assistant", "content": txt})

          placeholder = stream_ctx["placeholder"]
          accumulated = ""
          tool_results_turn: list[str] = []
          tool_calls_turn:   list[dict] = []

          placeholder.markdown(
              '<div class="msg-agent" style="color:#786D79;">⚡ Analysing…</div>',
              unsafe_allow_html=True,
          )

          for event in stream_response(agent_msgs):
              if event["type"] == "text":
                  accumulated += event["text"]
                  placeholder.markdown(
                      f'<div class="msg-agent">{render_md(accumulated)}'
                      f'<span style="color:#6442BD">▌</span></div>',
                      unsafe_allow_html=True,
                  )
              elif event["type"] == "tool_use":
                  tool_calls_turn.append(event)
              elif event["type"] == "tool_result":
                  tool_results_turn.append(event["result"])
              elif event["type"] == "done":
                  placeholder.markdown(
                      f'<div class="msg-agent">{render_md(accumulated)}</div>',
                      unsafe_allow_html=True,
                  )

          # Save assistant response
          blocks = [{"type": "tool_use", "name": tc["name"], "input": tc["input"]}
                    for tc in tool_calls_turn]
          if accumulated:
              blocks.append({"type": "text", "text": accumulated})
          st.session_state.messages.append({"role": "assistant", "content": blocks or accumulated})
          st.session_state.verdict = extract_verdict(accumulated, tool_results_turn)
          st.rerun()

with tab_report:
    render_executive_report()

# build-stamp: 2026-05-13 18:00 UTC
