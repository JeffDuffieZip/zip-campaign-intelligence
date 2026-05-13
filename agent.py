"""
Campaign A/B Testing & Incrementality Agent
Zip Co. — Marketing Data Products

Tools:
  list_campaigns      – browse all 40 real Braze BAU campaigns
  get_campaign_details – full stats for one campaign
  get_campaign_variants – per-variant breakdown
  get_channel_summary  – aggregate email/push/IAM numbers
  get_benchmarks       – percentile benchmarks for any metric
  calculate_stat_sig   – power analysis (pre/during/post)
  size_campaign        – pre-campaign audience & duration estimator
  get_segment_baselines – historical CVR baselines by segment
"""

import json
import math
import os
from typing import Generator

import anthropic
from dotenv import load_dotenv

from tools.tableau import (
    get_channel_summary,
    list_campaigns,
    get_campaign_details,
    get_campaign_variants,
    get_benchmarks,
)
from tools.stats import analyze_stat_sig_requirements, required_sample_size

load_dotenv()

MODEL = "claude-sonnet-4-6"

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are the Zip Campaign Intelligence Agent — an expert marketing analyst for Zip Co., a buy-now-pay-later fintech.

You help marketing stakeholders answer three critical questions about Braze A/B test campaigns:
- BEFORE: How large does the audience need to be, and how long will it take?
- DURING: Are we significant yet? What specifically needs to change to get there faster?
- AFTER: Was the result statistically significant — and was it truly incremental?

## Statistical Significance Framework
- **t-statistic** = CVR_delta / Standard_Error
- **95% CI (standard)**: |t_stat| > 1.960  → p-value < 0.05
- **90% CI (early read)**: |t_stat| > 1.282 → p-value < 0.10
- **99% CI (high stakes)**: |t_stat| > 2.576 → p-value < 0.01
- Always report the CONFIDENCE LEVEL (e.g. "99% confident"), not just "significant"

## Incrementality Metrics (only report when stat sig)
- **iCustomers** = cvr_abs_delta × n_target  → customers who converted BECAUSE of the campaign
- **iTTV** = (cvr_abs_delta / cvr_target) × ttv_target → revenue directly attributable to campaign
- **Cannibalization rate** = 1 − (iCustomers / converting_target)
  - < 40% → Strong signal, mostly incremental. SCALE.
  - 40–60% → Mixed. Incentive partially rewarding organic behaviour.
  - > 60% → Majority organic. ROI overstated. RETHINK audience or reduce incentive.
- **Organic rate** = cvr_control (what would have happened without the campaign)

## Campaign Naming Convention
`YYYY-MM-DD / segment / geo_or_occasion / channel / conversion_type / partner / window`
- Conv window in name = 3Day, 5Day, 7Day, 30Day
- Channel: Multi = Email + Push + IAM combined

## Customer Segments
- **New Purchaser**: Never completed any purchase. Baseline CVR ~1.06%
- **Repeat Purchaser**: Has prior purchases, re-engagement. Baseline CVR ~1.35%
- **Past/Latent Purchaser**: Last order 12–24 months ago. Baseline CVR ~1.29%
- **CO2App**: Checkout-only, never used app. Baseline CVR ~2.5%
- **App_Deals / BAU**: Broad app-engaged segment. Baseline CVR ~8–21%
- **BAU_Billpay**: High-intent billpay users. Baseline CVR ~20.8%

## Decision Framework
Given stat sig result, recommend:
- **SCALE** → sig positive, cannibalization < 40%, lift > 15%
- **ITERATE** → approaching sig (|t| 1.2–1.96), change audience size or sub-segment
- **RETHINK** → sig negative or cannibalization > 60%
- **EXTEND** → trending positive but needs more time/users
- **STOP** → clearly not working, t-stat < 0.5 after large sample
- **WATCH** → sig but cannibalization 40–60%, monitor before scaling

## Pre-Campaign Sizing Formula
n_per_arm = ((z_alpha + z_beta)² × (p1(1-p1) + p2(1-p2))) / (p1-p2)²
- z_alpha = 1.96 (95% CI), z_beta = 0.842 (80% power)
- days_to_sig = n_required_total / daily_entry_rate

## Response Style for Executive Audience
1. **One-sentence verdict** at the top (stat sig status + key number)
2. **3–4 bullet metrics** (formatted cleanly: CVR, lift %, iCustomers, iTTV)
3. **Recommendation badge**: SCALE / ITERATE / RETHINK / EXTEND / STOP / WATCH
4. **Why**: 1–2 sentences of plain-English context
5. For "during" campaigns: always include "X more users needed" or "X more days"

Use markdown. Keep responses concise — executives need the verdict in 30 seconds.
Spell out statistical significance on first mention: "statistically significant (we're 95%+ confident the result isn't due to random chance)".
"""

# ── Tool schemas ──────────────────────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "name": "list_campaigns",
        "description": "List all Braze BAU campaigns with stat sig status, channel, and audience size. Use to explore what campaigns exist.",
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "enum": ["EMAIL", "PUSH", "IAM", "MULTI"],
                            "description": "Filter by channel. Omit for all."}
            },
            "required": [],
        },
    },
    {
        "name": "get_campaign_details",
        "description": "Full performance metrics for one campaign: audience, CVR target/control, CVR delta, t-statistic, confidence level, iCustomers, iTTV, cannibalization rate. Use for post-campaign reads and during-campaign checks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_name": {"type": "string",
                                  "description": "Partial or full campaign name (e.g. 'July_4th', 'Best_Buy/Past_Purchasers')."}
            },
            "required": ["campaign_name"],
        },
    },
    {
        "name": "get_campaign_variants",
        "description": "Per-variant (treatment vs control) breakdown for a campaign. Returns CVR, audience, conversions, and T-stat per arm.",
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_name": {"type": "string", "description": "Partial campaign name."}
            },
            "required": ["campaign_name"],
        },
    },
    {
        "name": "get_channel_summary",
        "description": "Aggregate channel performance across all BAU campaigns: email sends, push sends, IAM impressions, avg click/open/unsub rates.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_benchmarks",
        "description": "Percentile benchmarks (p25/p50/p75/p90) for any metric across all campaigns. Use to contextualise a result — e.g. 'Is a 2.9 t-stat good?'",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {"type": "string",
                           "description": "Metric name. Examples: 'CVR_T_STAT', 'iCustomers', 'iTTV', 'CVR_DELTA'."},
                "channel": {"type": "string", "enum": ["EMAIL", "PUSH", "MULTI"],
                            "description": "Restrict to channel. Omit for all."},
            },
            "required": ["metric"],
        },
    },
    {
        "name": "calculate_stat_sig",
        "description": "Statistical power analysis for a running or completed A/B test. Returns: current confidence level, p-value, whether stat sig is reached, iCustomers, iTTV, cannibalization rate, and how many more users or days are needed if not yet significant.",
        "input_schema": {
            "type": "object",
            "properties": {
                "p_control":          {"type": "number", "description": "Control CVR as decimal (e.g. 0.0865 for 8.65%)."},
                "p_treatment":        {"type": "number", "description": "Treatment CVR as decimal."},
                "current_n_control":  {"type": "integer", "description": "Users in control arm."},
                "current_n_treatment":{"type": "integer", "description": "Users in treatment arm."},
                "ttv_target":         {"type": "number", "description": "Total transaction value for treatment arm (for iTTV calc). Optional."},
                "days_running":       {"type": "integer", "description": "Days the campaign has been running. Used for days-to-sig projection.", "default": 0},
                "alpha":              {"type": "number", "description": "Significance level. Default 0.05 (95% CI).", "default": 0.05},
                "power_target":       {"type": "number", "description": "Desired power. Default 0.80.", "default": 0.80},
            },
            "required": ["p_control", "p_treatment", "current_n_control", "current_n_treatment"],
        },
    },
    {
        "name": "size_campaign",
        "description": "Pre-campaign planning tool. Given a segment baseline CVR, expected lift, and eligible population, returns: required sample size per arm, total audience needed, estimated days to significance, and expected iCustomers/iTTV.",
        "input_schema": {
            "type": "object",
            "properties": {
                "segment":          {"type": "string",
                                     "description": "Segment name (e.g. 'Best_Buy_New', 'App_Deals', 'BAU_Billpay'). Used to look up baseline CVR if p_baseline not provided."},
                "p_baseline":       {"type": "number",
                                     "description": "Baseline (control) CVR as decimal. If omitted, uses segment historical average."},
                "expected_lift_pct":{"type": "number",
                                     "description": "Expected % lift over baseline. E.g. 15 for 15% lift."},
                "eligible_pop":     {"type": "integer",
                                     "description": "Total eligible customers available for the test."},
                "avg_order_value":  {"type": "number",
                                     "description": "Average order value in dollars. Default 163.", "default": 163},
                "incentive_cost":   {"type": "number",
                                     "description": "Per-customer incentive cost. Default 10.", "default": 10},
                "alpha":            {"type": "number", "description": "Significance level. Default 0.05.", "default": 0.05},
                "power_target":     {"type": "number", "description": "Desired power. Default 0.80.", "default": 0.80},
            },
            "required": ["expected_lift_pct", "eligible_pop"],
        },
    },
    {
        "name": "get_segment_baselines",
        "description": "Historical CVR baselines for each customer segment, derived from real Braze BAU campaigns. Use to inform pre-campaign sizing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "segment": {"type": "string",
                            "description": "Segment name to look up. Omit to return all segments."}
            },
            "required": [],
        },
    },
]

# ── Tool implementations ──────────────────────────────────────────────────────

def _size_campaign(
    expected_lift_pct: float,
    eligible_pop: int,
    segment: str = None,
    p_baseline: float = None,
    avg_order_value: float = 163.0,
    incentive_cost: float = 10.0,
    alpha: float = 0.05,
    power_target: float = 0.80,
) -> dict:
    from tools.mock_data import SEGMENT_BASELINES

    # Resolve baseline CVR
    if p_baseline is None:
        if segment and segment in SEGMENT_BASELINES:
            p_baseline = SEGMENT_BASELINES[segment]["avg_cvr"]
        else:
            # Default to overall mean
            p_baseline = 0.05

    p_treatment = p_baseline * (1 + expected_lift_pct / 100)
    n_per_arm = required_sample_size(p_baseline, p_treatment, alpha=alpha, power=power_target)
    n_total = n_per_arm * 2

    # Feasibility
    feasible = n_total <= eligible_pop
    coverage_pct = (n_total / eligible_pop * 100) if eligible_pop > 0 else 0

    # Daily entry rate: assume 30-day ramp across eligible pop
    daily_rate = eligible_pop / 30
    days_to_sig = math.ceil(n_total / daily_rate) if daily_rate > 0 else 999

    # Expected incrementals
    cvr_delta = p_treatment - p_baseline
    i_customers = round(cvr_delta * n_per_arm)
    i_ttv = round(i_customers * avg_order_value)

    # Expected spend
    expected_spend = round(n_per_arm * incentive_cost)
    projected_roi = round((i_ttv / expected_spend * 100) if expected_spend > 0 else 0, 1)

    return {
        "segment":              segment or "custom",
        "baseline_cvr":         round(p_baseline, 6),
        "expected_cvr_target":  round(p_treatment, 6),
        "expected_lift_pct":    expected_lift_pct,
        "required_n_per_arm":   n_per_arm,
        "required_n_total":     n_total,
        "eligible_population":  eligible_pop,
        "population_feasible":  feasible,
        "population_coverage_pct": round(coverage_pct, 1),
        "daily_entry_rate_est": round(daily_rate),
        "estimated_days_to_sig": days_to_sig,
        "expected_i_customers": i_customers,
        "expected_i_ttv":       i_ttv,
        "expected_spend":       expected_spend,
        "projected_roi_pct":    projected_roi,
        "alpha":                alpha,
        "power_target":         power_target,
    }


def _get_segment_baselines(segment: str = None) -> dict:
    from tools.mock_data import SEGMENT_BASELINES
    if segment:
        key = segment.replace(" ", "_")
        if key in SEGMENT_BASELINES:
            return {key: SEGMENT_BASELINES[key]}
        # fuzzy
        matches = {k: v for k, v in SEGMENT_BASELINES.items()
                   if segment.lower() in k.lower()}
        return matches if matches else {"error": f"Segment {segment!r} not found", "available": list(SEGMENT_BASELINES.keys())}
    return SEGMENT_BASELINES


def _calculate_stat_sig_enriched(
    p_control: float,
    p_treatment: float,
    current_n_control: int,
    current_n_treatment: int,
    ttv_target: float = None,
    days_running: int = 0,
    alpha: float = 0.05,
    power_target: float = 0.80,
) -> dict:
    result = analyze_stat_sig_requirements(
        p_control=p_control,
        p_treatment=p_treatment,
        current_n_control=current_n_control,
        current_n_treatment=current_n_treatment,
        days_running=days_running,
        alpha=alpha,
        power_target=power_target,
    )

    # Add incrementality metrics
    cvr_delta = p_treatment - p_control
    i_customers = round(cvr_delta * current_n_treatment)

    i_ttv = None
    if ttv_target and p_treatment > 0 and current_n_treatment > 0:
        # ttv_target = total TTV of treatment arm (all conversions)
        # incremental share = cvr_delta / cvr_treatment
        i_ttv = round((cvr_delta / p_treatment) * ttv_target)
    elif i_customers and i_customers > 0:
        # Fallback: iCustomers × default AOV ($163)
        i_ttv = round(i_customers * 163)

    converting_target = round(p_treatment * current_n_treatment)
    cannibalization = None
    if converting_target > 0 and i_customers is not None:
        cannibalization = round(1 - (i_customers / converting_target), 4)

    result["i_customers"]         = i_customers
    result["i_ttv"]               = i_ttv
    result["cannibalization_rate"] = cannibalization
    result["organic_rate"]        = round(p_control, 6)
    result["confidence_level_pct"] = round((1 - result.get("p_value_approx", 1.0)) * 100, 1) if result.get("p_value_approx") else None

    # Confidence label
    t = abs(result.get("t_statistic", 0) or 0)
    if t >= 2.576:
        result["confidence_label"] = "99%"
    elif t >= 1.960:
        result["confidence_label"] = "95%"
    elif t >= 1.645:
        result["confidence_label"] = "90%"
    elif t >= 1.282:
        result["confidence_label"] = "87%"
    else:
        result["confidence_label"] = f"~{round(t / 1.96 * 95)}%"

    # Recommendation — primary driver is t-stat direction, iCustomers, and lift size
    is_sig = result.get("is_significant", False)
    if is_sig:
        if cvr_delta < 0:
            result["recommendation"] = "RETHINK"    # significant negative result
        elif i_customers is not None and i_customers > 0 and abs(t) >= 2.576:
            result["recommendation"] = "SCALE"      # strong positive signal (99% CI)
        elif i_customers is not None and i_customers > 0:
            result["recommendation"] = "SCALE"      # positive at 95% CI
        elif cannibalization is not None and cannibalization > 0.80:
            result["recommendation"] = "WATCH"      # sig but almost entirely organic
        else:
            result["recommendation"] = "WATCH"
    else:
        if t >= 1.5:
            result["recommendation"] = "EXTEND"     # close — more users or time
        elif t >= 0.8:
            result["recommendation"] = "ITERATE"    # weak signal — change something
        else:
            result["recommendation"] = "STOP"       # no signal after large sample

    return result


def _dispatch_tool(name: str, inputs: dict) -> str:
    try:
        if name == "list_campaigns":
            result = list_campaigns(**inputs)
        elif name == "get_campaign_details":
            result = get_campaign_details(**inputs)
        elif name == "get_campaign_variants":
            result = get_campaign_variants(**inputs)
        elif name == "get_channel_summary":
            result = get_channel_summary()
        elif name == "get_benchmarks":
            result = get_benchmarks(**inputs)
        elif name == "calculate_stat_sig":
            result = _calculate_stat_sig_enriched(**inputs)
        elif name == "size_campaign":
            result = _size_campaign(**inputs)
        elif name == "get_segment_baselines":
            result = _get_segment_baselines(**inputs)
        else:
            result = {"error": f"Unknown tool: {name}"}
    except Exception as exc:
        result = {"error": str(exc)}
    return json.dumps(result, default=str)


# ── Streaming agent ───────────────────────────────────────────────────────────

def stream_response(messages: list[dict]) -> Generator[dict, None, None]:
    """
    Run one agent turn. Yields:
      {"type": "text",        "text": "..."}
      {"type": "tool_use",    "name": "...", "input": {...}}
      {"type": "tool_result", "name": "...", "result": "..."}
      {"type": "done"}
    """
    # ── Demo mode — bypass the LLM entirely ─────────────────────────────────
    demo_mode = os.getenv("DEMO_MODE", "").lower() in ("1", "true", "yes", "on")
    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip().strip('"').strip("'")
    is_placeholder = (
        not api_key
        or "YOUR_KEY" in api_key.upper()
        or "..." in api_key
        or "PLACEHOLDER" in api_key.upper()
        or len(api_key) < 50          # real Anthropic keys are ~108 chars
        or not api_key.startswith("sk-ant-")
    )
    # Auto-enable demo mode if no valid key is configured
    if demo_mode or is_placeholder:
        from demo_mode import stream_demo_response
        yield from stream_demo_response(messages)
        return

    if False:  # legacy placeholder branch below
        yield {
            "type": "text",
            "text": (
                "**⚠️ Invalid or missing `ANTHROPIC_API_KEY`**\n\n"
                "The key in `.env` is either empty, still set to a placeholder, or malformed.\n\n"
                "**Fix it in 30 seconds:**\n"
                "1. Get a key at https://console.anthropic.com/settings/keys (starts with `sk-ant-…`, ~108 chars)\n"
                "2. Edit `/Users/jeffduffie/braze-agent/.env` and replace the blank value:\n"
                "   ```\n   ANTHROPIC_API_KEY=sk-ant-...your-actual-key...\n   ```\n"
                "3. Restart Streamlit: `pkill -f streamlit && python3 -m streamlit run app.py`\n\n"
                "*Or run `bash setup.sh` — it walks you through it interactively.*"
            ),
        }
        yield {"type": "done"}
        return

    client  = anthropic.Anthropic(api_key=api_key)
    history = list(messages)

    while True:
        accumulated_text = ""
        tool_uses        = []
        stop_reason      = None

        with client.messages.stream(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=history,
            tools=TOOLS,
        ) as stream:
            for event in stream:
                if hasattr(event, "type"):
                    if event.type == "content_block_delta":
                        if hasattr(event.delta, "text"):
                            accumulated_text += event.delta.text
                            yield {"type": "text", "text": event.delta.text}
                        elif hasattr(event.delta, "type") and event.delta.type == "input_json_delta":
                            if tool_uses:
                                tool_uses[-1]["input_raw"] = (
                                    tool_uses[-1].get("input_raw", "") + event.delta.partial_json
                                )
                    elif event.type == "content_block_start":
                        if hasattr(event.content_block, "type") and event.content_block.type == "tool_use":
                            tool_uses.append({
                                "id":    event.content_block.id,
                                "name":  event.content_block.name,
                                "input": {},
                            })

            for t in tool_uses:
                raw = t.pop("input_raw", "{}")
                try:
                    t["input"] = json.loads(raw)
                except json.JSONDecodeError:
                    t["input"] = {}

            final_msg = stream.get_final_message()
            stop_reason = final_msg.stop_reason

        if stop_reason == "end_turn" or not tool_uses:
            yield {"type": "done"}
            break

        # Build assistant content block
        assistant_content = []
        if accumulated_text:
            assistant_content.append({"type": "text", "text": accumulated_text})
        for t in tool_uses:
            assistant_content.append({
                "type": "tool_use", "id": t["id"],
                "name": t["name"], "input": t["input"]
            })
            yield {"type": "tool_use", "name": t["name"], "input": t["input"]}

        history.append({"role": "assistant", "content": assistant_content})

        # Execute tools and collect results
        tool_results = []
        for t in tool_uses:
            result_str = _dispatch_tool(t["name"], t["input"])
            yield {"type": "tool_result", "name": t["name"], "result": result_str}
            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": t["id"],
                "content":     result_str,
            })

        history.append({"role": "user", "content": tool_results})
