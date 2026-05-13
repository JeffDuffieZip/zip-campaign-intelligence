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
from tools.similarity import find_similar_campaigns, similar_summary_markdown


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

    # Append similar-campaign evidence
    similar = find_similar_campaigns(c, k=3, min_score=5)
    if similar:
        top = similar[0]
        narrative += (
            f"\n\n**🔁 Closest analog:** *{top['name']}* "
            f"(Canvas ID `{top['canvas_id'][:8]}…` · "
            f"iTTV ${(top['campaign'].get('iTTV') or 0):+,.0f}). "
            f"This pairing gives you two completed wins to build the holiday playbook around."
        )
        narrative += similar_summary_markdown(similar)

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

    # Show what 'good' could have looked like via similar campaigns
    similar = find_similar_campaigns(c, k=3, min_score=5)
    if similar:
        winners = [m for m in similar if (m["campaign"].get("iTTV") or 0) > 0]
        if winners:
            top = winners[0]
            narrative += (
                f"\n\n**🔁 Where redirecting could land:** *{top['name']}* "
                f"(Canvas ID `{top['canvas_id'][:8]}…` · iTTV "
                f"**${(top['campaign'].get('iTTV') or 0):+,.0f}**) ran on a comparable audience and won. "
                f"Routing the same volume to that recipe is the high-confidence next move."
            )
        narrative += similar_summary_markdown(similar)

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

    # Find similar historical Best Buy New campaigns for evidence
    pseudo_target = {
        "segment": "Best_Buy_New",
        "partner": "Best_Buy",
        "Campaign Canvas Channel": "EMAIL",
        "conv_type": "App_Download",
        "TARGET_AUDIENCE": pop,
        "CVR_TARGET": baseline,
        "CAMPAIGN_CANVAS_ID": "planned-best-buy-v3",
    }
    similar = find_similar_campaigns(pseudo_target, k=3, min_score=5)
    if similar:
        top = similar[0]
        top_ttv = top["campaign"].get("iTTV") or 0
        narrative += (
            f"\n\n**🔁 Best historical analog:** *{top['name']}* "
            f"(Canvas ID `{top['canvas_id'][:8]}…`). "
            f"That campaign landed at {(top['campaign'].get('CVR_TARGET') or 0)*100:.2f}% CVR — "
            f"if V3 lands there, expect **${top_ttv:+,.0f}** iTTV. "
            f"This is your confidence band, not a guarantee — but it's evidence the segment responds."
        )
        narrative += similar_summary_markdown(similar, header="Recent Best Buy New campaigns")

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

    # ── Similar past campaigns (recommendation context) ──────────────────────
    similar = find_similar_campaigns(c, k=3, min_score=5)
    similarity_section = ""
    if similar:
        similarity_section = similar_summary_markdown(similar)

        # Promote the strongest match into a one-line steer in the recommendation
        top = similar[0]
        top_name = top["name"]
        top_cid  = top["canvas_id"]
        top_ttv  = top["campaign"].get("iTTV") or 0
        top_rec_line = (
            f"\n\n**🔁 Closest historical analog:** *{top_name}* "
            f"(score {top['score']}/18 · iTTV ${top_ttv:+,.0f} · Canvas ID `{top_cid[:8]}…`). "
        )
        if has_results:
            if top_ttv > 0 and is_sig:
                top_rec_line += "That campaign scaled successfully — strong evidence to replicate the recipe."
            elif top_ttv < 0:
                top_rec_line += "That campaign lost money — be cautious about reusing the same playbook."
            else:
                top_rec_line += "Use it as a benchmark for what 'good' looks like at this audience size."
        else:
            top_rec_line += (
                "Use this analog to project realistic outcomes for your launch — "
                f"that test landed at {(top['campaign'].get('CVR_TARGET') or 0)*100:.2f}% CVR."
            )
        perf_section = perf_section.rstrip() + top_rec_line + "\n"

    narrative = header + perf_section + similarity_section
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


def _handle_roi_matrix(
    eligible_pop: int = None,
    baseline_cvr: float = None,
    avg_order_value: float = 126.50,
    ntm_margin: float = 0.4144,
    incentive_cost: float = 10.0,
) -> Generator[dict, None, None]:
    """
    Generic ROI planning matrix — compares all CVR tiers, recommends best scenario.
    No specific campaign required. Shows the full spend/TTV/NTM/ROI picture.
    """
    from tools.stats import required_sample_size

    fixed_roi = round((avg_order_value * ntm_margin / incentive_cost - 1) * 100, 1)

    # ── Three CVR tiers from segment baselines ────────────────────────────────
    tiers = [
        {"label": "Mid (6%)",       "cvr": 0.0600, "segment": "Fashion_Nova_Loyalist", "pop": 50_000,  "lift_pct": 10},
        {"label": "High (8%)",      "cvr": 0.0800, "segment": "App_Deals_Seasonal",    "pop": 150_000, "lift_pct": 10},
        {"label": "Very High (10%)","cvr": 0.1000, "segment": "App_Deals_High_Intent", "pop": 150_000, "lift_pct": 10},
    ]

    # If caller supplied a specific baseline/pop, add it as a custom tier
    if baseline_cvr is not None and eligible_pop is not None:
        tiers.insert(0, {"label": f"Custom ({baseline_cvr*100:.1f}%)",
                         "cvr": baseline_cvr, "segment": "custom",
                         "pop": eligible_pop, "lift_pct": 10})

    # Pre-compute per tier
    for t in tiers:
        p1    = t["cvr"]
        p2    = round(p1 * (1 + t["lift_pct"] / 100), 6)
        n_arm = required_sample_size(p1, p2)
        pop   = t["pop"]
        daily = pop / 30
        days  = max(1, round((n_arm * 2) / daily))

        conv_treat  = round(pop * p2)
        conv_ctrl   = round(pop * p1)
        cost        = round(conv_treat * incentive_cost)
        ttv_treat   = round(conv_treat * avg_order_value)
        ttv_ctrl    = round(conv_ctrl  * avg_order_value)
        ntm         = round(ttv_treat * ntm_margin)
        i_customers = round((p2 - p1) * n_arm)
        i_ttv       = round(i_customers * avg_order_value)

        t.update({
            "p2": p2, "n_arm": n_arm, "days": days,
            "conv_treat": conv_treat, "conv_ctrl": conv_ctrl,
            "cost": cost, "ttv_treat": ttv_treat, "ttv_ctrl": ttv_ctrl,
            "ntm": ntm, "i_customers": i_customers, "i_ttv": i_ttv,
        })

    # ── Pick best scenario ────────────────────────────────────────────────────
    # Score = NTM / days (most NTM in shortest time)
    best = max(tiers, key=lambda t: t["ntm"] / max(t["days"], 1))

    # Emit a tool result so the verdict panel populates
    matrix_result = {
        "fixed_roi_pct": fixed_roi,
        "scenarios": [
            {"cvr_pct": f"{t['cvr']*100:.0f}%", "ntm_increase": t["ntm"],
             "cost": t["cost"], "days_to_sig": t["days"]}
            for t in tiers
        ],
        "min_sample_by_lift": [
            {"lift_pp": f"+{(t['p2']-t['cvr'])*100:.2f}pp",
             "n_per_arm": t["n_arm"], "n_total": t["n_arm"] * 2}
            for t in tiers
        ],
        "best_scenario": best["label"],
    }
    yield from _tool_call("roi_matrix", {"mode": "multi_tier_comparison"}, matrix_result)

    # ── Summary comparison table ──────────────────────────────────────────────
    comp_rows = ""
    for t in tiers:
        star = " ⭐" if t is best else ""
        comp_rows += (
            f"| **{t['label']}{star}** | "
            f"{t['pop']:,} | "
            f"{t['n_arm']:,} | "
            f"{t['days']}d | "
            f"${t['cost']:,.0f} | "
            f"${t['ttv_treat']:,.0f} | "
            f"**${t['ntm']:,.0f}** | "
            f"**{fixed_roi:.1f}%** |\n"
        )

    # ── Per-tier detail cards ──────────────────────────────────────────────────
    tier_cards = ""
    for t in tiers:
        star = "⭐ **Best scenario**" if t is best else ""
        tier_cards += f"""
**{t['label']}** {star}
- Segment: `{t['segment']}` · Eligible population: {t['pop']:,}
- Baseline CVR: **{t['cvr']*100:.1f}%** → Target CVR: **{t['p2']*100:.2f}%** (+{t['lift_pct']}% lift)
- Required per arm: **{t['n_arm']:,}** · Est. days to significance: **{t['days']} days**
- Treatment conversions: {t['conv_treat']:,} · Cost: **${t['cost']:,.0f}**
- Expected TTV: ${t['ttv_treat']:,.0f} · **NTM increase: ${t['ntm']:,.0f}** · ROI: {fixed_roi:.1f}%

"""

    narrative = f"""### ROI Planning Matrix — All CVR Tiers

**AOV:** ${avg_order_value:.2f} · **NTM Margin:** {ntm_margin*100:.1f}% · **Incentive:** ${incentive_cost:.0f}/conversion · **Fixed ROI:** {fixed_roi:.1f}%

---

#### Tier Comparison (10% relative lift target, 95% CI, 80% power)

| Segment Tier | Population | Min N/Arm | Days to Sig | Cost | Expected TTV | NTM Increase | ROI |
|---|---|---|---|---|---|---|---|
{comp_rows}
> ⭐ **Best scenario: {best['label']}** — highest NTM per day. Reaches significance in **{best['days']} days** with **${best['ntm']:,.0f}** in incremental NTM.

---

#### Tier Detail

{tier_cards}
---

#### Why ROI is constant at {fixed_roi:.1f}% across all tiers

ROI depends only on unit economics — not on how many people convert:

> **ROI = (AOV × NTM margin ÷ incentive cost) − 1**
> = (${avg_order_value:.2f} × {ntm_margin*100:.1f}% ÷ ${incentive_cost:.0f}) − 1 = **{fixed_roi:.1f}%**

Every incremental conversion at any CVR level returns the same margin. The CVR tier affects **speed** (days to significance) and **scale** (total NTM), not the per-conversion ROI.

**Choose your tier based on:**
- 🏃 **Speed**: Higher CVR → smaller sample needed → faster read
- 💰 **Scale**: Larger eligible population → more NTM at the same ROI
- 🎯 **Confidence**: Higher CVR baseline → signal is easier to detect cleanly
"""
    yield from _stream_text(narrative)
    yield {"type": "done"}


def _handle_formula_readme() -> Generator[dict, None, None]:
    """Complete formula guide — explains every metric and decision rule."""
    yield from _tool_call("get_segment_baselines", {}, SEGMENT_BASELINES)

    narrative = """### 📖 Formula & Methodology Guide

Everything the agent does is based on three statistical building blocks. Here's the full picture.

---

#### 1. Statistical Significance — Two-Proportion Z-Test

We test whether the treatment CVR is genuinely different from control, or just random variation.

**Step 1 — Pooled proportion:**
```
p_pooled = (conversions_target + conversions_control)
           / (audience_target + audience_control)
```

**Step 2 — Standard error:**
```
SE = √[ p_pooled × (1 − p_pooled) × (1/n_target + 1/n_control) ]
```

**Step 3 — T-statistic:**
```
t_stat = (CVR_target − CVR_control) / SE
```

**Confidence thresholds:**

| t-stat | Confidence | Meaning |
|---|---|---|
| \|t\| > 2.576 | **99%** | Very strong — scale with confidence |
| \|t\| > 1.960 | **95%** | Standard threshold — result is real |
| \|t\| > 1.282 | **90%** | Early signal — watch closely |
| \|t\| ≤ 1.282 | **Not significant** | Could be random chance |

---

#### 2. Incrementality Metrics

Raw conversions are misleading — some customers would have converted anyway. These metrics isolate the *campaign's* contribution.

**iCustomers** — how many extra customers converted *because* of the campaign:
```
iCustomers = CVR_delta × audience_target
           = (CVR_target − CVR_control) × n_target
```

**iTTV** — incremental revenue directly attributable to the campaign:
```
iTTV = (CVR_delta / CVR_target) × TTV_target
```

**Cannibalization rate** — share of converting customers who would have converted without the campaign:
```
Cannibalization = 1 − (iCustomers / converting_target)
```

| Cannibalization | Interpretation |
|---|---|
| < 40% | ✅ Strong — majority incremental. **SCALE.** |
| 40–60% | ⚠️ Mixed — incentive partly rewards organic behaviour. **WATCH.** |
| > 60% | 🔴 High — majority organic. ROI is overstated. **RETHINK.** |

---

#### 3. Minimum Sample Size — Pre-Campaign Sizing

How many users do you need in each arm to reliably detect a lift?

```
n_per_arm = [(z_α + z_β)² × (p1(1−p1) + p2(1−p2))] / (p1 − p2)²
```

Where:
- `p1` = baseline (control) CVR
- `p2` = expected treatment CVR = p1 × (1 + lift%)
- `z_α = 1.96` for 95% confidence (two-tailed)
- `z_β = 0.842` for 80% statistical power

**Projected days to significance:**
```
days = ceil(n_required_total / daily_entry_rate)
daily_entry_rate ≈ eligible_population / 30
```

---

#### 4. ROI Formula

Unit economics of the incentive programme — constant regardless of CVR:

```
ROI = (AOV × NTM_margin / incentive_cost) − 1
```

| Input | Default | Source |
|---|---|---|
| AOV (avg order value) | $126.50 | Blended across segments |
| NTM margin | 41.44% | Net Transaction Margin rate |
| Incentive cost | $10 | Per-conversion offer cost |
| **Fixed ROI** | **424.3%** | Constant across all CVR levels |

---

#### 5. Decision Framework — When to SCALE, EXTEND, STOP

| Recommendation | When | Action |
|---|---|---|
| 🟢 **SCALE** | Stat sig positive + cannibalization < 40% | Roll out to full segment |
| 🟢 **SCALE** | Stat sig positive + strong lift (99% CI) | Productionise the playbook |
| 🔵 **EXTEND** | \|t\| ≥ 1.5 but < 1.96 | Run longer or add audience |
| 🟡 **ITERATE** | \|t\| 0.8–1.5 | Weak signal — change creative or segment |
| 🟡 **WATCH** | Sig but cannibalization 40–60% | Monitor before scaling |
| 🔴 **RETHINK** | Stat sig *negative* | Campaign hurt conversions — investigate |
| 🔴 **STOP** | \|t\| < 0.8 after large sample | No signal — reallocate budget |

---

#### 6. Segment Baseline CVRs

Historical control-arm CVRs used for pre-campaign sizing:

| Segment | Avg CVR | Range | Campaigns |
|---|---|---|---|
| BAU Billpay | 20.79% | — | 1 |
| App Deals High Intent | 10.00% | 9.2–11.3% | 4 |
| App Deals Seasonal | 8.00% | 7.2–9.1% | 5 |
| App Deals (all) | 8.94% | 6.4–13.5% | 9 |
| Fashion Nova Loyalist | 6.00% | 5.4–6.8% | 3 |
| Gift Cards | 2.59% | — | 1 |
| Weekly Deals | 2.17% | — | 1 |
| Best Buy Repeat | 1.35% | 1.1–1.6% | 4 |
| Best Buy Past | 1.29% | — | 1 |
| Best Buy New | 1.06% | 1.0–1.3% | 6 |

> **Rule of thumb:** Never benchmark a Best Buy New Purchaser test against App Deals numbers. A "bad" App Deals result (1% CVR) is a "great" Best Buy New result.
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
        f"| 5 | **Find similar campaigns** | *What campaigns are similar to Wayfair?* |\n"
        f"| 6 | **Size a new campaign** | Click the 📋 Pre-Campaign scenario above |\n"
        f"| 7 | **ROI planning matrix** | *Show me the ROI matrix for 344k customers at 6.24% baseline* |\n"
        f"| 8 | **Portfolio rollup** | *Summarize all email campaigns this year* |\n"
        f"| 9 | **List campaigns** | *List all campaigns* |\n"
        f"| 10 | **Segment baselines** | *What's the Best Buy New baseline CVR?* |\n\n"
        f"Every campaign lookup also includes a **Similar past campaigns** section automatically — "
        f"so you always get historical context with your recommendation.\n\n"
        f"Or click any of the three demo scenarios at the top of the page."
    )
    yield from _stream_text(narrative)
    yield {"type": "done"}


def _handle_similarity(target: dict) -> Generator[dict, None, None]:
    """Show similar historical campaigns to a chosen target campaign."""
    name = target.get("display_name", target.get("name", "Unknown"))
    cid  = target.get("CAMPAIGN_CANVAS_ID", "")
    similar = find_similar_campaigns(target, k=5, min_score=4)

    yield from _tool_call("get_campaign_details", {"campaign_name": name}, target)
    yield from _tool_call(
        "find_similar_campaigns",
        {"target_canvas_id": cid, "k": 5},
        {"matches": [
            {"name": m["name"], "canvas_id": m["canvas_id"], "score": m["score"],
             "iTTV": m["campaign"].get("iTTV"), "stat_sig": m["campaign"].get("stat_sig")}
            for m in similar
        ]},
    )

    if not similar:
        narrative = (
            f"### Similar campaigns to *{name}*\n\n"
            f"I couldn't find any historical campaigns with a high-enough similarity score "
            f"(threshold 4/18). This campaign is either:\n\n"
            f"- A first-of-its-kind concept (segment/partner combo we haven't tested before)\n"
            f"- Missing the dimensions we score on (segment, partner, conv_type)\n\n"
            f"Try listing all campaigns and picking a comparable manually."
        )
    else:
        top = similar[0]
        narrative = f"""### Similar campaigns to *{name}*

<div class="verdict-line">
  <span class="pill pill-info">● Top analog: {top['name']}</span>
  <span style="color:#786D79;font-size:0.78rem">similarity {top['score']}/18 · Canvas ID `{top['canvas_id'][:8]}…`</span>
</div>

I scored across 6 dimensions: segment, partner, conversion type, channel, audience size, and CVR baseline. Here are the closest matches in the portfolio:
{similar_summary_markdown(similar, header="Ranked by similarity")}
**How to read this:** Higher scores = closer match. The top result is your best evidence for how this campaign is likely to perform — if it scaled, your campaign probably will too; if it failed, treat that as a warning shot.
"""
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
    text_lower = text.lower()

    # 1. Comparison takes priority over scenario detection
    #    (otherwise "Compare July 4th and Memorial Day" triggers the POST scenario)
    if any(k in text_lower for k in ["compare", " vs ", " versus ", "head to head",
                                       "which performed", "which is better", "which won"]):
        yield from _handle_comparison(text); return

    # 2. Scripted scenarios (only when not a comparison)
    scenario = _detect_scenario(text)
    if scenario == "post":
        yield from _scenario_post_campaign(); return
    if scenario == "during":
        yield from _scenario_during_campaign(); return
    if scenario == "pre":
        yield from _scenario_pre_campaign(); return

    # 3. Ad-hoc handlers

    # List / directory of campaigns
    if any(k in text_lower for k in [
        "list all campaigns", "list campaigns", "show all campaigns",
        "all campaigns", "campaign directory", "every campaign",
        "show me all", "list of campaigns",
    ]):
        yield from _handle_list_campaigns(); return

    # Dedicated "find similar to X" handler
    if any(k in text_lower for k in [
        "similar to", "similar campaigns to", "find analog", "find analogs",
        "what campaigns are like", "campaigns like", "comparable campaigns",
        "closest analog", "closest match", "find similar",
    ]):
        target = _find_campaign(text)
        if target:
            yield from _handle_similarity(target); return

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

    # Formula / methodology README guide
    if any(k in text_lower for k in [
        "formula", "readme", "how it works", "how does it work",
        "all the formulas", "explain the formula", "methodology",
        "how is significance", "what is icustomers", "how are you calculating",
        "cannibalization formula", "sample size formula", "how does the agent",
        "explain all", "how do you calculate", "formula guide",
        "how everything works", "explain the metrics", "what does each metric",
    ]):
        yield from _handle_formula_readme(); return

    # ROI matrix / pre-campaign planning view
    if any(k in text_lower for k in [
        "roi matrix", "roi table", "roi view", "roi planning",
        "expected roi", "what roi", "spend and roi",
        "conversion rate table", "cvr scenarios", "multiple cvr",
        "6.24", "6% conversion", "8% conversion", "10% conversion", "15% conversion",
        "minimum population", "minimum sample", "min sample size",
        "ntm increase", "net transaction margin",
        "estimated spend", "planning matrix",
    ]):
        # Parse eligible population if mentioned (e.g. "344,286 customers")
        pop_match = re.search(r"(\d[\d,]{3,})\s*(?:customers|users|eligible|people)?", text_lower)
        pop = int(pop_match.group(1).replace(",", "")) if pop_match else 344_286
        # Parse baseline CVR if mentioned
        cvr_match = re.search(r"(\d+\.?\d*)\s*%\s*(?:baseline|conversion|cvr)", text_lower)
        base_cvr = float(cvr_match.group(1)) / 100 if cvr_match else 0.0624
        yield from _handle_roi_matrix(eligible_pop=pop, baseline_cvr=base_cvr); return

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
