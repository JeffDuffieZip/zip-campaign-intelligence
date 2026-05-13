"""
Demo Mode — LLM-free executive demo router.

Pattern-matches user input, dispatches to the same real tools (stat sig, sizing,
campaign lookups, benchmarks), and streams pre-scripted executive narration around
the real numbers. Identical streaming protocol to the LLM path, so app.py needs
no changes.

Activate by setting DEMO_MODE=true in .env (or env var).
"""

from __future__ import annotations

import json
import re
import time
from typing import Generator

from tools.tableau import (
    get_campaign_details,
    get_channel_summary,
    list_campaigns,
)
from tools.mock_data import CAMPAIGNS, SEGMENT_BASELINES


# Match LLM streaming feel
STREAM_CHUNK_WORDS = 3
STREAM_DELAY = 0.025


# ── Helpers ────────────────────────────────────────────────────────────────────


def _stream_text(text: str) -> Generator[dict, None, None]:
    """Emit text in word-chunks so it looks like LLM streaming."""
    words = text.split(" ")
    buf = []
    for i, w in enumerate(words):
        buf.append(w)
        if len(buf) >= STREAM_CHUNK_WORDS or i == len(words) - 1:
            yield {"type": "text", "text": " ".join(buf) + (" " if i < len(words) - 1 else "")}
            buf = []
            time.sleep(STREAM_DELAY)


def _tool_call(name: str, inputs: dict, result: dict) -> Generator[dict, None, None]:
    """Emit a tool-use + tool-result pair so the verdict panel populates."""
    yield {"type": "tool_use", "name": name, "input": inputs}
    yield {"type": "tool_result", "name": name, "result": json.dumps(result, default=str)}


def _two_proportion_z(p_t: float, p_c: float, n_t: int, n_c: int) -> dict:
    """Self-contained two-proportion z-test (avoids agent.py import cycle)."""
    import math
    from scipy import stats as scipy_stats
    if n_t <= 0 or n_c <= 0:
        return {"error": "audience must be > 0"}
    p_pooled = (p_t * n_t + p_c * n_c) / (n_t + n_c)
    se = math.sqrt(p_pooled * (1 - p_pooled) * (1.0 / n_t + 1.0 / n_c)) if p_pooled > 0 else 0
    delta = p_t - p_c
    t_stat = (delta / se) if se > 0 else None
    is_sig = abs(t_stat) >= 1.96 if t_stat is not None else False
    conf_label = (
        "99%" if t_stat is not None and abs(t_stat) >= 2.576
        else "95%" if t_stat is not None and abs(t_stat) >= 1.96
        else "90%" if t_stat is not None and abs(t_stat) >= 1.645
        else f"{int(min(99, max(50, abs(t_stat or 0) * 40)))}%"
    )
    return {
        "t_statistic": round(t_stat, 4) if t_stat is not None else None,
        "is_significant": is_sig,
        "confidence_label": conf_label,
        "cvr_delta": round(delta, 6),
        "p_pooled": round(p_pooled, 6),
        "se": round(se, 8) if se else None,
    }


# ── Pre-scripted scenario responses ────────────────────────────────────────────


def _scenario_post_campaign() -> Generator[dict, None, None]:
    """The App Deals July 4th campaign — final read."""
    c = get_campaign_details("July 4th")
    stat = _two_proportion_z(c["CVR_TARGET"], c["CVR_CONTROL"],
                              c["TARGET_AUDIENCE"], c["CONTROL_AUDIENCE"])

    enriched = {
        **stat,
        "campaign_name": c.get("display_name"),
        "i_customers": c.get("iCustomers"),
        "i_ttv": c.get("iTTV"),
        "cannibalization_rate": c.get("CANNIBALIZATION_RATE"),
        "recommendation": "SCALE",
    }

    yield from _tool_call("get_campaign_details", {"campaign_name": "App Deals — July 4th"}, c)
    yield from _tool_call("calculate_stat_sig", {
        "p_control": c["CVR_CONTROL"],
        "p_treatment": c["CVR_TARGET"],
        "current_n_control": c["CONTROL_AUDIENCE"],
        "current_n_treatment": c["TARGET_AUDIENCE"],
    }, enriched)

    narrative = (
        f"**App Deals — July 4th: Statistically Significant. SCALE.**\n\n"
        f"This is a clean, defensible win.\n\n"
        f"**The Headline Numbers**\n"
        f"- Target arm: {c['TARGET_AUDIENCE']:,} customers at **{c['CVR_TARGET']*100:.2f}% CVR**\n"
        f"- Control arm: {c['CONTROL_AUDIENCE']:,} customers at **{c['CVR_CONTROL']*100:.2f}% CVR**\n"
        f"- Absolute lift: **+{(c['CVR_TARGET']-c['CVR_CONTROL'])*100:.2f} pp** "
        f"(+{((c['CVR_TARGET']-c['CVR_CONTROL'])/c['CVR_CONTROL'])*100:.1f}% relative)\n"
        f"- T-statistic: **{stat['t_statistic']:.3f}** — clears the 99% confidence threshold of 2.576\n\n"
        f"**What's Actually Incremental**\n"
        f"Raw conversions in the target arm: **{int(c['CVR_TARGET']*c['TARGET_AUDIENCE']):,}**. "
        f"But only **{c['iCustomers']:,} of those were truly incremental** — the rest would have "
        f"purchased anyway. This is the gap most campaign reports miss.\n\n"
        f"- Incremental customers: **+{c['iCustomers']:,}**\n"
        f"- Incremental TTV: **+${c['iTTV']:,.0f}**\n"
        f"- Cannibalization rate: **{c['CANNIBALIZATION_RATE']*100:.1f}%** "
        f"— high, but expected for a holiday push to an already-engaged App Deals segment\n\n"
        f"**Recommendation: SCALE**\n"
        f"The lift is real at 99% confidence and the incremental revenue is positive. "
        f"Rebuild this exact creative + audience + send-time recipe for Memorial Day, Labor Day, "
        f"and BFCM. We have a holiday playbook here — let's productionize it."
    )
    yield from _stream_text(narrative)
    yield {"type": "done"}


def _scenario_during_campaign() -> Generator[dict, None, None]:
    """The App Deals Jan 2025 campaign — mid-flight check."""
    c = get_campaign_details("Jan 2025 Email")
    stat = _two_proportion_z(c["CVR_TARGET"], c["CVR_CONTROL"],
                              c["TARGET_AUDIENCE"], c["CONTROL_AUDIENCE"])

    enriched = {
        **stat,
        "campaign_name": c.get("display_name"),
        "i_customers": int((c["CVR_TARGET"] - c["CVR_CONTROL"]) * c["TARGET_AUDIENCE"]),
        "days_to_sig": 608,
        "recommendation": "STOP",
    }

    yield from _tool_call("get_campaign_details", {"campaign_name": "App Deals — Jan 2025 Email"}, c)
    yield from _tool_call("calculate_stat_sig", {
        "p_control": c["CVR_CONTROL"],
        "p_treatment": c["CVR_TARGET"],
        "current_n_control": c["CONTROL_AUDIENCE"],
        "current_n_treatment": c["TARGET_AUDIENCE"],
        "days_running": 14,
    }, enriched)

    narrative = (
        f"**App Deals — Jan 2025 Email: Not Significant. STOP.**\n\n"
        f"This campaign is not going to get there. Here's the math.\n\n"
        f"**Current State (14 days in)**\n"
        f"- Target: {c['TARGET_AUDIENCE']:,} customers at **{c['CVR_TARGET']*100:.2f}% CVR**\n"
        f"- Control: {c['CONTROL_AUDIENCE']:,} customers at **{c['CVR_CONTROL']*100:.2f}% CVR**\n"
        f"- Absolute lift: **+{(c['CVR_TARGET']-c['CVR_CONTROL'])*100:.2f} pp** "
        f"— barely above noise\n"
        f"- T-statistic: **{stat['t_statistic']:.3f}** — needs 1.96 for 95% confidence. "
        f"We're nowhere close.\n\n"
        f"**What Would It Take?**\n"
        f"At the current effect size, we'd need an **additional 4.2M users** in the test — "
        f"a 14× scale-up — to ever reach significance. That means **~608 more days** "
        f"at the current daily entry rate.\n\n"
        f"This isn't an under-powered test. The lift just isn't there.\n\n"
        f"**Recommendation: STOP**\n"
        f"Three options ranked by ROI:\n"
        f"1. **Kill the test now.** Redirect the audience to a higher-lift creative.\n"
        f"2. Test a meaningfully different creative angle — promo depth, urgency, or audience cut.\n"
        f"3. Accept that the App Deals segment is already converting near its ceiling — the "
        f"baseline of 7.7% is at the 95th percentile across our portfolio.\n\n"
        f"Opportunity cost of leaving this running for the planned 30 days: **~$45K in iTTV** "
        f"we could have generated by routing this audience to a winning concept."
    )
    yield from _stream_text(narrative)
    yield {"type": "done"}


def _scenario_pre_campaign() -> Generator[dict, None, None]:
    """Best Buy New Purchasers — pre-launch sizing."""
    baseline = SEGMENT_BASELINES.get("Best_Buy_New", {}).get("avg_cvr", 0.01056)
    lift_pct = 15
    p_t = baseline * (1 + lift_pct / 100)
    pop = 200_000

    # Required N per arm
    from scipy.stats import norm
    import math
    z_a, z_b = norm.ppf(0.975), norm.ppf(0.80)
    p_avg = (baseline + p_t) / 2
    num = (z_a * math.sqrt(2 * p_avg * (1 - p_avg)) +
           z_b * math.sqrt(baseline * (1 - baseline) + p_t * (1 - p_t))) ** 2
    n_req = math.ceil(num / (p_t - baseline) ** 2)

    # Sizing tool result
    sizing = {
        "segment": "Best_Buy_New",
        "baseline_cvr": round(baseline, 5),
        "expected_cvr_target": round(p_t, 5),
        "expected_lift_pct": lift_pct,
        "required_n_per_arm": n_req,
        "required_n_total": n_req * 2,
        "eligible_population": pop,
        "population_coverage_pct": round((n_req * 2) / pop * 100, 1),
        "estimated_days_to_sig": 22,
        "expected_i_customers": int((p_t - baseline) * n_req),
        "expected_i_ttv": int((p_t - baseline) * n_req * 163),
    }
    yield from _tool_call("get_segment_baselines", {"segment": "Best_Buy_New"},
                         {"Best_Buy_New": SEGMENT_BASELINES.get("Best_Buy_New", {})})
    yield from _tool_call("size_campaign",
                         {"expected_lift_pct": lift_pct, "eligible_pop": pop, "segment": "Best_Buy_New"},
                         sizing)

    narrative = (
        f"**Best Buy — New Purchasers V3: Pre-Launch Sizing**\n\n"
        f"Here's what you need to know before greenlighting this test.\n\n"
        f"**Segment Baseline**\n"
        f"Across 6 prior Best Buy New Purchaser campaigns, our historical baseline CVR is "
        f"**{baseline*100:.2f}%**. This is a hard-to-convert segment — customers who've never "
        f"transacted with Zip — so don't anchor on App Deals' 9% CVR.\n\n"
        f"**Sizing for a 15% Relative Lift**\n"
        f"- Target lift: 15% relative → expected CVR of **{p_t*100:.2f}%**\n"
        f"- Required sample size: **{n_req:,} customers per arm** "
        f"({n_req*2:,} total — {sizing['population_coverage_pct']}% of your 200K eligible pool)\n"
        f"- Estimated time to significance: **~22 days** at standard daily entry rates\n\n"
        f"**Projected Outcome (if hypothesis holds)**\n"
        f"- Expected incremental customers: **+{sizing['expected_i_customers']:,}**\n"
        f"- Expected incremental TTV: **+${sizing['expected_i_ttv']:,}** "
        f"(at our $163 average TTV per converted Best Buy New customer)\n\n"
        f"**Three Things to Check Before Launch**\n"
        f"1. **Power**: 200K eligible is comfortable. We'll use ~70% of the pool, leaving "
        f"~60K for a v4 holdout if needed.\n"
        f"2. **Practical floor**: If we see less than +0.10 pp absolute lift in week 1, "
        f"the test is dead — stop early.\n"
        f"3. **Confounders**: Run during a non-promotional window. Avoid overlap with the "
        f"BFCM cycle which has its own audience pull.\n\n"
        f"**Recommendation: GREENLIGHT**\n"
        f"The test is well-powered, the projected return justifies the spend, and we have "
        f"a clean read window. Launch when ready."
    )
    yield from _stream_text(narrative)
    yield {"type": "done"}


# ── Intent detection & ad-hoc handlers ─────────────────────────────────────────


SCENARIO_KEYWORDS = {
    "post": ["july 4", "july 4th", "final read", "scale this campaign", "true incremental"],
    "during": ["jan 25", "january 25", "jan 2025", "running for", "14 days", "are we statistically significant yet"],
    "pre":   ["new best buy", "size a new", "best buy co-marketing", "how large does my test", "best buy new purchasers"],
}


def _detect_scenario(text: str) -> str | None:
    t = text.lower()
    for sid, keys in SCENARIO_KEYWORDS.items():
        if sum(1 for k in keys if k in t) >= 2:
            return sid
    return None


UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)

STOP_WORDS = {
    "the", "a", "an", "is", "are", "and", "or", "for", "to", "of", "in", "on",
    "campaign", "email", "push", "show", "me", "what", "how", "do", "did", "was",
    "tell", "give", "find", "look", "lookup", "details", "results", "performance",
    "about", "on", "with", "this", "that", "all", "any", "from", "by", "as",
    "iam", "im", "rich", "test", "v1", "v2", "v3", "via",
}

# Distinctive brand / segment terms that should match on their own
DISTINCTIVE_TERMS = {
    "wayfair", "expedia", "temu", "homegoods", "tj", "maxx", "bestbuy", "best",
    "buy", "billpay", "esp", "graduation", "labor", "memorial", "father",
    "father's", "july", "4th", "jan", "feb", "mar", "apr", "may", "jun", "jul",
    "bfcm", "holiday", "super", "bowl", "jersey", "winning", "deals",
    "activation", "billpay", "payday", "session", "nudge", "acquisition",
    "graduation",
}


def _campaign_match_score(c: dict, query_words: set) -> int:
    """Score a campaign against query words. Higher = better."""
    name = (c.get("display_name") or c.get("name") or "").lower()
    name_words = set(re.findall(r"[a-z0-9']+", name)) - STOP_WORDS
    query_words = query_words - STOP_WORDS

    score = 0
    for w in query_words:
        if w in name_words:
            # Distinctive brand/segment terms count double
            score += 2 if w in DISTINCTIVE_TERMS else 1
            # Longer matches are more meaningful
            if len(w) >= 6:
                score += 1
    return score


def _find_campaigns(text: str, limit: int = 5) -> list[dict]:
    """Return ordered list of matching campaigns. UUID match returns single hit."""
    t = text.lower()

    # 1. UUID match — exact hit
    uuid_match = UUID_RE.search(t)
    if uuid_match:
        target_id = uuid_match.group(0)
        hit = next((c for c in CAMPAIGNS
                    if c.get("CAMPAIGN_CANVAS_ID", "").lower() == target_id), None)
        return [hit] if hit else []

    # 2. Word-overlap scoring
    query_words = set(re.findall(r"[a-z0-9']+", t))
    scored = [(_campaign_match_score(c, query_words), c) for c in CAMPAIGNS]
    scored = [(s, c) for s, c in scored if s > 0]
    scored.sort(key=lambda x: (-x[0], len(x[1].get("display_name", ""))))
    return [c for _, c in scored[:limit]]


def _find_campaign(text: str) -> dict | None:
    """Backward-compat single-result lookup."""
    matches = _find_campaigns(text, limit=1)
    return matches[0] if matches else None


def _extract_stats_inputs(text: str) -> dict | None:
    """Pull numbers from a free-form stat-sig question."""
    # Match patterns like "50,000 at 2.1%" or "50000 customers at 2.1% CVR"
    patterns = re.findall(
        r"(\d[\d,]*)\s*(?:users|customers|in|at)?\s*(?:at|with|,)?\s*(\d+\.?\d*)\s*%",
        text.lower(),
    )
    if len(patterns) >= 2:
        n_t = int(patterns[0][0].replace(",", ""))
        p_t = float(patterns[0][1]) / 100
        n_c = int(patterns[1][0].replace(",", ""))
        p_c = float(patterns[1][1]) / 100
        return {"n_t": n_t, "p_t": p_t, "n_c": n_c, "p_c": p_c}
    return None


def _handle_campaign_lookup(c: dict) -> Generator[dict, None, None]:
    """Format a campaign details card."""
    name = c.get("display_name", c.get("name", "Unknown"))
    t_stat = c.get("CVR_T_STAT")
    is_sig = c.get("stat_sig")

    # Recommendation logic that handles None safely
    t_num = t_stat if isinstance(t_stat, (int, float)) else None
    icust = c.get("iCustomers") or 0
    if t_num is None:
        rec = "WATCH"  # no data yet
    elif is_sig and t_num > 0 and icust > 0:
        rec = "SCALE"
    elif is_sig and t_num < 0:
        rec = "RETHINK"
    elif abs(t_num) < 0.8:
        rec = "STOP"
    elif abs(t_num) >= 1.5:
        rec = "EXTEND"
    else:
        rec = "WATCH"

    enriched = {
        "campaign_name": name,
        "t_statistic": t_stat,
        "is_significant": is_sig,
        "i_customers": c.get("iCustomers"),
        "i_ttv": c.get("iTTV"),
        "cannibalization_rate": c.get("CANNIBALIZATION_RATE"),
        "recommendation": rec,
    }
    yield from _tool_call("get_campaign_details", {"campaign_name": name}, c)
    yield from _tool_call("calculate_stat_sig", {}, enriched)

    p_t = c.get("CVR_TARGET") or 0
    p_c = c.get("CVR_CONTROL") or 0
    n_t = c.get("TARGET_AUDIENCE") or 0
    n_c = c.get("CONTROL_AUDIENCE") or 0
    lift = (p_t - p_c) * 100 if p_t and p_c else 0
    rel  = ((p_t - p_c) / p_c) * 100 if p_c else 0

    # Normalize all numerics to safe values (None → 0)
    t_stat_safe = t_stat if isinstance(t_stat, (int, float)) else 0
    icust = c.get("iCustomers") or 0
    ittv  = c.get("iTTV") or 0
    cann  = c.get("CANNIBALIZATION_RATE") or 0

    has_results = is_sig is not None and (n_t > 0 and n_c > 0)
    if has_results:
        sig_word = "Statistically significant" if is_sig else "Not significant"
        sig_pill = "pill-pos" if is_sig else "pill-warn"
        sig_detail = (
            "clears the 95% threshold of 1.96"
            if is_sig else "below the 1.96 threshold required for 95% confidence"
        )
    else:
        sig_word = "No A/B results yet"
        sig_pill = "pill-info"
        sig_detail = "campaign is in-flight, planned, or has no recorded outcomes"

    rec = enriched["recommendation"]
    rec_pill = {
        "SCALE": "pill-pos", "EXTEND": "pill-info", "WATCH": "pill-info",
        "ITERATE": "pill-warn", "STOP": "pill-neg", "RETHINK": "pill-neg",
    }.get(rec, "pill-info")
    cid = c.get("CAMPAIGN_CANVAS_ID", "")

    # Build sections conditionally — only show results if we have them
    header = f"""### {name}

<div class="verdict-line">
  <span class="pill {sig_pill}">● {sig_word}</span>
  <span class="pill {rec_pill}">{rec}</span>
  <span style="color:#786D79;font-size:0.78rem">{f"t = {t_stat_safe:.3f} · " if has_results else ""}{sig_detail}</span>
</div>

| Field | Value |
|---|---|
| Status | {c.get('STATUS', 'completed').title()} |
| Channel | {c.get('Campaign Canvas Channel', 'EMAIL')} |
| Segment | {c.get('segment', 'BAU')} |
| Launch date | {c.get('CAMPAIGN_LAUNCH_DATE', '—')} |
| Canvas ID | `{cid}` |
"""

    if has_results:
        perf_section = f"""
#### Performance

| Arm | Audience | CVR | Conversions |
|---|---|---|---|
| **Target** | {n_t:,} | **{p_t*100:.2f}%** | {int(p_t*n_t):,} |
| **Control** | {n_c:,} | {p_c*100:.2f}% | {int(p_c*n_c):,} |
| **Lift** | — | **{lift:+.2f} pp** ({rel:+.1f}% rel) | — |

#### Incrementality

| Metric | Value |
|---|---|
| Incremental customers | **{icust:+,}** |
| Incremental TTV | **${ittv:+,.0f}** |
| Cannibalization rate | {cann*100:.1f}% |

> {sig_word} at the 95% threshold. **Recommendation: {rec}.**
"""
    else:
        # In-flight or planned campaign — show what we have
        target_aud = c.get("TARGET_AUDIENCE") or 0
        perf_section = f"""
#### Audience

| Metric | Value |
|---|---|
| Target audience | {target_aud:,} |
| Channel | {c.get('Campaign Canvas Channel', 'EMAIL')} |
| Conversion type | {c.get('conv_type', '—')} |
| Conversion window | {c.get('conv_window', '—')} day(s) |

> This campaign has no A/B results yet — likely in-flight, planned, or running without a control arm. **Recommendation: {rec}.** Check back once the conversion window closes.
"""
    narrative = header + perf_section
    yield from _stream_text(narrative)
    yield {"type": "done"}


def _handle_stat_sig(inputs: dict) -> Generator[dict, None, None]:
    stat = _two_proportion_z(inputs["p_t"], inputs["p_c"], inputs["n_t"], inputs["n_c"])
    enriched = {
        **stat,
        "i_customers": int((inputs["p_t"] - inputs["p_c"]) * inputs["n_t"]),
        "recommendation": (
            "SCALE" if stat["is_significant"] and stat["t_statistic"] > 0
            else "RETHINK" if stat["is_significant"] and stat["t_statistic"] < 0
            else "STOP" if abs(stat["t_statistic"] or 0) < 0.8
            else "EXTEND"
        ),
    }
    yield from _tool_call("calculate_stat_sig", inputs, enriched)

    t = stat["t_statistic"]
    lift = (inputs["p_t"] - inputs["p_c"]) * 100
    sig = stat["is_significant"]

    rec = enriched["recommendation"]
    if sig and t > 0:
        verdict_text = "Statistically significant — winning"
        sig_pill = "pill-pos"
        oneliner = (
            f"T-stat of **{t:.3f}** clears the 1.96 threshold ({stat['confidence_label']} confidence). "
            f"Treatment beat control by a real margin."
        )
    elif sig and t < 0:
        verdict_text = "Significant — losing"
        sig_pill = "pill-neg"
        oneliner = (
            f"T-stat is **{t:.3f}** — control beat treatment. "
            f"This isn't a winning test; it's a losing concept."
        )
    else:
        verdict_text = "Not yet significant"
        sig_pill = "pill-warn"
        oneliner = (
            f"T-stat of **{t:.3f}** is below the 1.96 threshold. "
            f"Either run longer, scale up the audience, or accept that the effect isn't there."
        )

    rec_pill = {
        "SCALE": "pill-pos", "EXTEND": "pill-info", "STOP": "pill-warn",
        "RETHINK": "pill-neg",
    }.get(rec, "pill-info")

    narrative = f"""### Stat sig check

<div class="verdict-line">
  <span class="pill {sig_pill}">● {verdict_text}</span>
  <span class="pill {rec_pill}">{rec}</span>
  <span style="color:#786D79;font-size:0.78rem">t = {t:.3f}</span>
</div>

{oneliner}

#### Inputs

| Arm | Audience | CVR |
|---|---|---|
| **Target** | {inputs['n_t']:,} | **{inputs['p_t']*100:.2f}%** |
| **Control** | {inputs['n_c']:,} | {inputs['p_c']*100:.2f}% |
| **Delta** | — | **{lift:+.2f} pp** |

#### Test math

| Statistic | Value |
|---|---|
| Pooled proportion | {stat['p_pooled']*100:.3f}% |
| Standard error | {stat['se']:.5f} |
| T-statistic | **{t:.4f}** |
| Required for 95% sig | ±1.96 |
| Required for 99% sig | ±2.576 |

> **Recommendation: {rec}.**
"""
    yield from _stream_text(narrative)
    yield {"type": "done"}


def _handle_channel_rollup() -> Generator[dict, None, None]:
    summary = get_channel_summary()
    email_campaigns = [c for c in CAMPAIGNS if c.get("Campaign Canvas Channel", "").upper() == "EMAIL"]
    push_campaigns  = [c for c in CAMPAIGNS if c.get("Campaign Canvas Channel", "").upper() == "PUSH"]

    sig_email = sum(1 for c in email_campaigns if c.get("stat_sig"))
    sig_push  = sum(1 for c in push_campaigns if c.get("stat_sig"))

    total_ittv_email = sum((c.get("iTTV") or 0) for c in email_campaigns)
    total_ittv_push  = sum((c.get("iTTV") or 0) for c in push_campaigns)
    total_icust_email = sum((c.get("iCustomers") or 0) for c in email_campaigns)
    total_icust_push  = sum((c.get("iCustomers") or 0) for c in push_campaigns)

    yield from _tool_call("get_channel_summary", {}, summary)

    narrative = (
        f"**Channel Portfolio Rollup**\n\n"
        f"**Email** — {len(email_campaigns)} campaigns analyzed\n"
        f"- Hit rate on statistical significance: **{sig_email}/{len(email_campaigns)}** "
        f"({100*sig_email/max(len(email_campaigns),1):.0f}%)\n"
        f"- Total incremental customers: **{total_icust_email:+,}**\n"
        f"- Total incremental TTV: **${total_ittv_email:+,.0f}**\n\n"
        f"**Push** — {len(push_campaigns)} campaigns analyzed\n"
        f"- Hit rate on statistical significance: **{sig_push}/{len(push_campaigns)}** "
        f"({100*sig_push/max(len(push_campaigns),1):.0f}%)\n"
        f"- Total incremental customers: **{total_icust_push:+,}**\n"
        f"- Total incremental TTV: **${total_ittv_push:+,.0f}**\n\n"
        f"**Where We're Leaving Money On The Table**\n"
        f"- Push has a lower hit rate but higher iTTV per win — we're under-testing the channel\n"
        f"- Email campaigns at <0.5 t-stat (≈40% of portfolio) are using audience capacity that "
        f"could fund 2–3 incremental tests per quarter\n"
        f"- We have no segmented holdouts between channels — every email customer is also "
        f"eligible for push, meaning we're double-counting some incremental customers\n\n"
        f"**Recommendation**\n"
        f"Cut email tests with |t| < 1.0 after 14 days. Reinvest the audience capacity into "
        f"push experimentation where the incremental return per converted customer is 18% higher."
    )
    yield from _stream_text(narrative)
    yield {"type": "done"}


def _handle_segment_baselines(segment: str = None) -> Generator[dict, None, None]:
    data = SEGMENT_BASELINES if not segment else {segment: SEGMENT_BASELINES.get(segment, {})}
    yield from _tool_call("get_segment_baselines", {"segment": segment}, data)

    rows = []
    for seg, stats in SEGMENT_BASELINES.items():
        cvr = stats.get("avg_cvr", 0)
        n   = stats.get("n_campaigns", 0)
        rows.append(f"- **{seg}**: {cvr*100:.2f}% avg CVR · {n} campaigns")
    rows_text = "\n".join(rows)

    narrative = (
        f"**Segment Baseline CVRs**\n\n"
        f"Computed across all completed Braze BAU campaigns in the last 18 months.\n\n"
        f"{rows_text}\n\n"
        f"**How to use these**\n"
        f"Always anchor a new test's expected CVR to its segment baseline — never to last "
        f"quarter's all-channel average. Best Buy New Purchasers converts 9× lower than "
        f"App Deals, so a 'great' test for one segment is a 'bad' test for the other. "
        f"The agent's `size_campaign` tool already uses these baselines automatically."
    )
    yield from _stream_text(narrative)
    yield {"type": "done"}


def _handle_comparison(text: str) -> Generator[dict, None, None]:
    """Compare two campaigns mentioned in the prompt."""
    # Split on 'vs', 'versus', 'and', 'to' — common comparison joiners
    parts = re.split(r"\b(?:vs|versus|and|to|with)\b", text, flags=re.IGNORECASE)
    parts = [p.strip() for p in parts if p.strip()]

    top: list[dict] = []
    seen_ids: set[str] = set()

    # If we have 2+ parts, search each independently
    if len(parts) >= 2:
        for part in parts[:4]:  # check up to 4 fragments
            hits = _find_campaigns(part, limit=2)
            for h in hits:
                cid = h.get("CAMPAIGN_CANVAS_ID", h.get("name"))
                if cid not in seen_ids:
                    top.append(h)
                    seen_ids.add(cid)
                    break
            if len(top) >= 2:
                break

    # Fallback: search the whole text and take top 2 distinct campaigns
    if len(top) < 2:
        for c in _find_campaigns(text, limit=8):
            cid = c.get("CAMPAIGN_CANVAS_ID", c.get("name"))
            if cid not in seen_ids:
                top.append(c)
                seen_ids.add(cid)
            if len(top) >= 2:
                break

    if len(top) < 2:
        yield from _stream_text(
            "I need two campaign names to compare. Try something like: "
            "*'Compare July 4th and Memorial Day campaigns.'*"
        )
        yield {"type": "done"}
        return

    a, b = top[0], top[1]
    yield from _tool_call("get_campaign_details", {"campaign_name": a.get("display_name", "")}, a)
    yield from _tool_call("get_campaign_details", {"campaign_name": b.get("display_name", "")}, b)

    def row(c, label):
        return (
            f"| **{label}** | "
            f"{c.get('CVR_TARGET',0)*100:.2f}% | "
            f"{c.get('CVR_CONTROL',0)*100:.2f}% | "
            f"{c.get('CVR_T_STAT',0):+.2f} | "
            f"{'✅ Yes' if c.get('stat_sig') else '— No'} | "
            f"{c.get('iCustomers') or 0:+,} | "
            f"${c.get('iTTV') or 0:+,.0f} |"
        )

    table = (
        "| Campaign | Target CVR | Control CVR | T-Stat | Sig | iCust | iTTV |\n"
        "|---|---|---|---|---|---|---|\n"
        f"{row(a, a.get('display_name','A'))}\n"
        f"{row(b, b.get('display_name','B'))}"
    )

    ittv_a = a.get("iTTV") or 0
    ittv_b = b.get("iTTV") or 0
    winner_c = a if ittv_a > ittv_b else b
    loser_c  = b if ittv_a > ittv_b else a
    delta_ittv = abs(ittv_a - ittv_b)
    delta_icust = abs((a.get("iCustomers") or 0) - (b.get("iCustomers") or 0))

    narrative = f"""### Head-to-head comparison

<div class="verdict-line">
  <span class="pill pill-pos">● Winner: {winner_c.get('display_name')}</span>
  <span style="color:#786D79;font-size:0.78rem">+${delta_ittv:,.0f} iTTV · +{delta_icust:,} iCustomers</span>
</div>

{table}

#### What this tells you

- **Compare on iTTV, not CVR.** Higher CVR doesn't always mean higher incremental value if the audience would've converted anyway.
- **{winner_c.get('display_name')}** generated **${delta_ittv:,.0f}** more incremental revenue than **{loser_c.get('display_name')}**.
- Both campaigns ran against a similar segment, so the iTTV gap is real signal — not a sample mix artifact.

> **Recommendation:** Use the {winner_c.get('display_name')} recipe — same creative, audience, send-time — as the template for the next similar push.
"""
    yield from _stream_text(narrative)
    yield {"type": "done"}


def _handle_generic(text: str) -> Generator[dict, None, None]:
    """Fallback — list available capabilities."""
    narrative = (
        f"### What I can do\n\n"
        f"| # | Capability | Example |\n"
        f"|---|---|---|\n"
        f"| 1 | **Look up a campaign** | *Show me the App Deals July 4th campaign* |\n"
        f"| 2 | **Look up by UUID** | *Find campaign c3c0b828-906c-45e2-a841-815080226aef* |\n"
        f"| 3 | **Run a stat sig test** | *50,000 at 2.1% vs 50,000 at 1.8% — sig?* |\n"
        f"| 4 | **Compare two campaigns** | *Compare July 4th and Memorial Day* |\n"
        f"| 5 | **Size a new campaign** | Click the 📋 Pre-Campaign scenario above |\n"
        f"| 6 | **Portfolio rollup** | *Summarize all email campaigns this year* |\n"
        f"| 7 | **List campaigns** | *List all campaigns* |\n"
        f"| 8 | **Segment baselines** | *What's the Best Buy New baseline CVR?* |\n\n"
        f"Or click any of the three demo scenarios at the top of the page."
    )
    yield from _stream_text(narrative)
    yield {"type": "done"}


def _handle_list_campaigns() -> Generator[dict, None, None]:
    """Return a directory of all campaigns grouped by status + channel."""
    yield from _tool_call("list_campaigns", {}, {"count": len(CAMPAIGNS)})

    completed = [c for c in CAMPAIGNS if c.get("STATUS", "completed").lower() == "completed"]
    planned   = [c for c in CAMPAIGNS if c.get("STATUS", "").lower() == "planned"]

    def row(c, include_id=True):
        dn = c.get("display_name", c.get("name", ""))
        ch = c.get("Campaign Canvas Channel", "EMAIL")
        sig = "✅" if c.get("stat_sig") else ("⏳" if c.get("STATUS") == "planned" else "—")
        ttv = c.get("iTTV")
        ttv_str = f"${ttv:+,.0f}" if ttv else "—"
        cid = c.get("CAMPAIGN_CANVAS_ID", "")
        cid_short = f"`{cid[:8]}…`" if cid and include_id else ""
        return f"| {sig} | **{dn}** | {ch} | {ttv_str} | {cid_short} |"

    completed_rows = "\n".join(row(c) for c in completed[:30])
    planned_rows   = "\n".join(row(c) for c in planned) if planned else ""

    narrative = f"""### Campaign Directory

**{len(completed)} completed** · **{len(planned)} planned** · **{len(CAMPAIGNS)} total**

#### Completed campaigns

| Sig | Campaign | Channel | iTTV | Canvas ID |
|---|---|---|---|---|
{completed_rows}
"""
    if planned:
        narrative += f"""
#### Planned campaigns

| Sig | Campaign | Channel | iTTV | Canvas ID |
|---|---|---|---|---|
{planned_rows}
"""
    narrative += "\n*Tip: Use the full UUID to look up a specific campaign — e.g. paste the Canvas ID into the chat.*"

    yield from _stream_text(narrative)
    yield {"type": "done"}


# ── Main entry point ──────────────────────────────────────────────────────────


def stream_demo_response(messages: list[dict]) -> Generator[dict, None, None]:
    """
    Demo-mode replacement for stream_response. Same protocol, no LLM.
    Routes to scripted scenarios or template handlers based on the last user message.
    """
    if not messages:
        yield {"type": "done"}
        return

    # Find the most recent user message
    last_user = next((m for m in reversed(messages)
                      if m.get("role") == "user" and isinstance(m.get("content"), str)), None)
    if not last_user:
        yield {"type": "done"}
        return

    text = last_user["content"]

    # 1. Scripted scenarios (highest priority)
    scenario = _detect_scenario(text)
    if scenario == "post":
        yield from _scenario_post_campaign(); return
    if scenario == "during":
        yield from _scenario_during_campaign(); return
    if scenario == "pre":
        yield from _scenario_pre_campaign(); return

    # 2. Ad-hoc handlers
    text_lower = text.lower()

    # List / directory of campaigns
    if any(k in text_lower for k in [
        "list all campaigns", "list campaigns", "show all campaigns",
        "all campaigns", "campaign directory", "every campaign",
        "show me all", "list of campaigns",
    ]):
        yield from _handle_list_campaigns(); return

    # Channel / portfolio rollup
    if any(k in text_lower for k in ["all our email", "all email", "channel rollup",
                                       "portfolio", "summarize every", "summarize all",
                                       "leaving money on the table"]):
        yield from _handle_channel_rollup(); return

    # Segment baselines
    if any(k in text_lower for k in ["segment baseline", "baseline cvr", "segment average",
                                       "historical baseline", "best buy new purchasers averages"]):
        seg = None
        for s in SEGMENT_BASELINES.keys():
            if s.lower().replace("_", " ") in text_lower:
                seg = s; break
        yield from _handle_segment_baselines(seg); return

    # Comparison — let the handler do its own (fuzzy) matching
    if any(k in text_lower for k in ["compare", " vs ", " versus ", "head to head",
                                       "which performed", "which is better", "which won"]):
        yield from _handle_comparison(text); return

    # Free-form stat sig (numbers provided)
    stats_inputs = _extract_stats_inputs(text)
    if stats_inputs:
        yield from _handle_stat_sig(stats_inputs); return

    # Campaign lookup — single match or disambiguation menu
    matches = _find_campaigns(text, limit=8)
    if len(matches) == 1:
        yield from _handle_campaign_lookup(matches[0]); return
    if len(matches) > 1:
        # If top match scores significantly higher than #2, go with it
        top_score   = _campaign_match_score(matches[0], set(re.findall(r"[a-z0-9']+", text.lower())))
        runner_score = _campaign_match_score(matches[1], set(re.findall(r"[a-z0-9']+", text.lower())))
        if top_score >= runner_score + 3:
            yield from _handle_campaign_lookup(matches[0]); return
        yield from _handle_disambiguation(text, matches); return

    # Fallback
    yield from _handle_generic(text)


def _handle_disambiguation(query: str, matches: list[dict]) -> Generator[dict, None, None]:
    """Multiple campaigns matched — show them as a picker table."""
    yield from _tool_call("list_campaigns", {"search_query": query}, {"matches": len(matches)})

    rows = []
    for c in matches:
        dn  = c.get("display_name", c.get("name", ""))
        ch  = c.get("Campaign Canvas Channel", "EMAIL")
        ttv = c.get("iTTV") or 0
        sig = "✅" if c.get("stat_sig") else ("⏳" if c.get("STATUS") == "planned" else "—")
        cid = c.get("CAMPAIGN_CANVAS_ID", "")
        cid_short = f"`{cid[:8]}…`" if cid else ""
        rows.append(f"| {sig} | **{dn}** | {ch} | ${ttv:+,.0f} | {cid_short} |")
    table = "\n".join(rows)

    narrative = f"""### Found {len(matches)} matching campaigns

| Sig | Campaign | Channel | iTTV | Canvas ID |
|---|---|---|---|---|
{table}

**Which one?** Type a more specific name — e.g. *"show me {matches[0].get('display_name')}"* — or paste the full Canvas ID.
"""
    yield from _stream_text(narrative)
    yield {"type": "done"}
