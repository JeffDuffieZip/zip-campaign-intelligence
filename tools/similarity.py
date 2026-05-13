"""
Campaign similarity engine.

Given a "target" campaign (or a set of attributes), find historically-similar
completed campaigns and return them with a similarity score + human-readable
"why this is similar" explanation.

Dimensions we score on (in priority order):
  1. Same segment (App_Deals, Best_Buy_New, etc.)        — heaviest signal
  2. Same partner / merchant (Best_Buy, Wayfair, etc.)
  3. Same conversion type (App_Purchase, CO_Purchase, …)
  4. Same channel (EMAIL/PUSH/MULTI)
  5. Audience-size proximity (log-scale distance)
  6. CVR proximity (relative distance)

We exclude campaigns with no recorded outcomes (iTTV/CVR_T_STAT both None) so
the matches are useful for recommendations — only completed, instrumented tests.
"""

from __future__ import annotations

import math
from typing import Optional

from tools.mock_data import CAMPAIGNS


# ── Tunable weights ─────────────────────────────────────────────────────────


WEIGHTS = {
    "segment":      5,   # same archetype
    "partner":      3,   # same merchant
    "conv_type":    2,   # same conversion event
    "channel":      2,   # same delivery channel
    "audience_max": 3,   # similar audience size (0-3)
    "cvr_max":      3,   # similar baseline CVR  (0-3)
}


# ── Helpers ─────────────────────────────────────────────────────────────────


def _audience_proximity_score(a: Optional[float], b: Optional[float]) -> int:
    """Score audience-size similarity 0-3 using log-ratio distance."""
    if not a or not b or a <= 0 or b <= 0:
        return 0
    log_ratio = abs(math.log10(a / b))
    if log_ratio < 0.15:   # within ~1.4x
        return 3
    if log_ratio < 0.30:   # within ~2x
        return 2
    if log_ratio < 0.60:   # within ~4x
        return 1
    return 0


def _cvr_proximity_score(a: Optional[float], b: Optional[float]) -> int:
    """Score CVR similarity 0-3 using relative distance."""
    if not a or not b or a <= 0 or b <= 0:
        return 0
    rel = abs(a - b) / max(a, b)
    if rel < 0.15:
        return 3
    if rel < 0.30:
        return 2
    if rel < 0.50:
        return 1
    return 0


def _has_outcomes(c: dict) -> bool:
    """Only consider campaigns with recorded A/B results."""
    return (
        c.get("CVR_T_STAT") is not None
        and c.get("CVR_TARGET") is not None
        and c.get("TARGET_AUDIENCE")
    )


def _explain_match(target: dict, candidate: dict, breakdown: dict) -> list[str]:
    """Plain-English bullets explaining why two campaigns are similar."""
    bullets: list[str] = []
    if breakdown["segment"]:
        bullets.append(f"Same segment ({target.get('segment')})")
    if breakdown["partner"]:
        p = target.get("partner")
        if p and p != "NA":
            bullets.append(f"Same partner ({p})")
    if breakdown["conv_type"]:
        bullets.append(f"Same conversion type ({target.get('conv_type')})")
    if breakdown["channel"]:
        bullets.append(f"Same channel ({target.get('Campaign Canvas Channel')})")
    if breakdown["audience"] >= 2:
        ta = target.get("TARGET_AUDIENCE") or 0
        ca = candidate.get("TARGET_AUDIENCE") or 0
        ratio = max(ta, ca) / max(min(ta, ca), 1)
        bullets.append(f"Similar audience size ({ca:,} vs {ta:,} — within {ratio:.1f}×)")
    if breakdown["cvr"] >= 2:
        tc = target.get("CVR_TARGET") or 0
        cc = candidate.get("CVR_TARGET") or 0
        bullets.append(f"Similar baseline CVR ({cc*100:.2f}% vs {tc*100:.2f}%)")
    return bullets


def _score(target: dict, candidate: dict) -> tuple[int, dict]:
    """Return (total_score, breakdown_dict)."""
    breakdown = {
        "segment":   WEIGHTS["segment"]   if target.get("segment") and target.get("segment") == candidate.get("segment") else 0,
        "partner":   WEIGHTS["partner"]   if target.get("partner") and target.get("partner") != "NA"
                                            and target.get("partner") == candidate.get("partner") else 0,
        "conv_type": WEIGHTS["conv_type"] if target.get("conv_type") and target.get("conv_type") == candidate.get("conv_type") else 0,
        "channel":   WEIGHTS["channel"]   if target.get("Campaign Canvas Channel")
                                            and target.get("Campaign Canvas Channel") == candidate.get("Campaign Canvas Channel") else 0,
        "audience":  _audience_proximity_score(target.get("TARGET_AUDIENCE"), candidate.get("TARGET_AUDIENCE")),
        "cvr":       _cvr_proximity_score(target.get("CVR_TARGET"), candidate.get("CVR_TARGET")),
    }
    total = sum(breakdown.values())
    return total, breakdown


# ── Public API ──────────────────────────────────────────────────────────────


def find_similar_campaigns(
    target: dict,
    k: int = 3,
    min_score: int = 4,
    require_outcomes: bool = True,
) -> list[dict]:
    """
    Return up to *k* most-similar campaigns to the given target.

    Each result is a dict:
      {
        "campaign":         <full campaign record>,
        "score":            <int total score>,
        "breakdown":        {segment, partner, conv_type, channel, audience, cvr},
        "why":              [list of plain-english bullets],
        "name":             <display_name>,
        "canvas_id":        <CAMPAIGN_CANVAS_ID>,
      }

    Set *require_outcomes=False* to include in-flight / planned campaigns too.
    """
    target_id = target.get("CAMPAIGN_CANVAS_ID") or target.get("name")
    pool = [c for c in CAMPAIGNS if (c.get("CAMPAIGN_CANVAS_ID") or c.get("name")) != target_id]
    if require_outcomes:
        pool = [c for c in pool if _has_outcomes(c)]

    scored: list[dict] = []
    for c in pool:
        score, breakdown = _score(target, c)
        if score < min_score:
            continue
        scored.append({
            "campaign":  c,
            "score":     score,
            "breakdown": breakdown,
            "why":       _explain_match(target, c, breakdown),
            "name":      c.get("display_name", c.get("name", "")),
            "canvas_id": c.get("CAMPAIGN_CANVAS_ID", ""),
        })

    scored.sort(key=lambda x: (-x["score"], -(x["campaign"].get("iTTV") or 0)))
    return scored[:k]


def similar_summary_markdown(matches: list[dict], header: str = "Similar past campaigns") -> str:
    """Render a similarity result list as a markdown section ready to drop into a chat reply."""
    if not matches:
        return ""

    rows = []
    for m in matches:
        c = m["campaign"]
        ittv = c.get("iTTV") or 0
        tstat = c.get("CVR_T_STAT") or 0
        sig = "✅" if c.get("stat_sig") else "—"
        cid = m["canvas_id"]
        cid_short = f"`{cid[:8]}…`" if cid else ""
        rows.append(
            f"| {sig} | **{m['name']}** | "
            f"{tstat:+.2f} | "
            f"{(c.get('TARGET_AUDIENCE') or 0):,} | "
            f"{(c.get('CVR_TARGET') or 0)*100:.2f}% | "
            f"${ittv:+,.0f} | "
            f"{cid_short} |"
        )

    why_blocks = []
    for m in matches[:2]:  # only explain top 2 in depth
        bullets = "\n".join(f"  - {b}" for b in m["why"])
        why_blocks.append(f"**{m['name']}** ({m['score']}/18 similarity)\n{bullets}")
    why_section = "\n\n".join(why_blocks)

    table = "\n".join(rows)
    return f"""
#### 📚 {header}

| Sig | Campaign | T-Stat | Audience | CVR | iTTV | Canvas ID |
|---|---|---|---|---|---|---|
{table}

##### Why these are comparable

{why_section}
"""
