"""
Zip Campaign Intelligence Agent — Executive Demo UI
Run: streamlit run app.py
"""

import json
import os

import markdown as md_lib
import streamlit as st
from dotenv import load_dotenv

from agent import stream_response

load_dotenv()


def render_md(text: str) -> str:
    """Convert markdown to HTML with extensions for tables, fenced code, line-breaks."""
    if not text:
        return ""
    return md_lib.markdown(
        text,
        extensions=["tables", "fenced_code", "nl2br", "sane_lists"],
        output_format="html5",
    )

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Zip · Campaign Intelligence",
    page_icon="⚡",
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
  .zip-logo-wrap { display:flex; align-items:center; gap:14px; }
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

# ── Session state ─────────────────────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []
if "verdict" not in st.session_state:
    st.session_state.verdict = {}
if "active_scenario" not in st.session_state:
    st.session_state.active_scenario = None
if "pending_question" not in st.session_state:
    st.session_state.pending_question = None

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
    sig_badge = ('<span class="badge-sig">● SIGNIFICANT</span>' if is_sig is True else
                 '<span class="badge-nosig">○ NOT YET SIG</span>' if is_sig is False else
                 '<span class="badge-na">◇ SIZING MODE</span>')

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


# ── Layout ────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="zip-header">
  <div class="zip-logo-wrap">
    <div class="zip-mark">Z</div>
    <div>
      <div class="zip-eyebrow">Growth Analytics</div>
      <div class="zip-logo">Campaign Intelligence<span class="dot">.</span></div>
      <div class="zip-subtitle">A/B Testing &amp; Incrementality Agent · Zip Co</div>
    </div>
  </div>
  <span class="zip-badge">● Live Demo</span>
</div>
""", unsafe_allow_html=True)

# Scenario buttons row
c1, c2, c3, c4, c5 = st.columns(5)
for col, sc in zip([c1, c2, c3, c4, c5], SCENARIOS):
    with col:
        active = "🔵 " if st.session_state.active_scenario == sc["id"] else ""
        if st.button(f"{sc['icon']} {active}{sc['stage']}: {sc['title']}", key=f"sc_{sc['id']}"):
            st.session_state.pending_question = sc["question"]
            st.session_state.active_scenario  = sc["id"]
            st.rerun()

st.markdown("<hr>", unsafe_allow_html=True)

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
    # ── INPUT: moved to TOP, sticky-feeling location ────────────────────────
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

    # ── Render messages, NEWEST TURN FIRST ───────────────────────────────────
    if not st.session_state.messages:
        st.markdown("""
        <div class="empty-state" style="margin-top:18px;">
          <div class="empty-state-mark">Z</div>
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
            is_newest    = (idx_rev == 0)
            turn_number  = len(turns) - idx_rev
            has_assistant = any(m["role"] == "assistant" for m in turn)

            # Turn divider (above every non-newest turn)
            if idx_rev > 0:
                st.markdown(
                    '<hr style="border:none;border-top:1px dashed #D6D4D2;margin:22px 0 16px 0;">',
                    unsafe_allow_html=True,
                )
            # Turn label
            label_color = "#6442BD" if is_newest else "#8B858E"
            label_text = f"Turn {turn_number}" + ("  ·  newest" if is_newest else "")
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

# ── Streaming dispatch (only when we have a pending question + placeholder) ──

if question and stream_ctx is not None:
    # Build agent history (excluding the just-appended user message handled separately)
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
    blocks = [{"type": "tool_use", "name": tc["name"], "input": tc["input"]} for tc in tool_calls_turn]
    if accumulated:
        blocks.append({"type": "text", "text": accumulated})
    st.session_state.messages.append({"role": "assistant", "content": blocks or accumulated})
    st.session_state.verdict = extract_verdict(accumulated, tool_results_turn)
    st.rerun()

# build-stamp: 2026-05-13 16:37 UTC
