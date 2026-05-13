"""
Statistical utilities for campaign analysis.

Core capabilities:
- Two-proportion z-test power analysis (sample size / duration to stat sig)
- Current power given observed data
- Effect size and practical significance helpers
"""

import math
import numpy as np
from scipy import stats as scipy_stats


def required_sample_size(
    p_control: float,
    p_treatment: float,
    alpha: float = 0.05,
    power: float = 0.80,
    two_tailed: bool = True,
) -> int:
    """
    Minimum users needed *per arm* to detect the lift from p_control → p_treatment.

    Returns the per-arm sample size (multiply by 2 for total users needed).
    """
    if p_control <= 0 or p_treatment <= 0:
        raise ValueError("CVRs must be positive")
    if abs(p_control - p_treatment) < 1e-10:
        raise ValueError("Control and treatment CVRs are identical — no detectable effect")

    z_alpha = scipy_stats.norm.ppf(1 - alpha / (2 if two_tailed else 1))
    z_beta  = scipy_stats.norm.ppf(power)
    p_avg   = (p_control + p_treatment) / 2

    numerator = (
        z_alpha * math.sqrt(2 * p_avg * (1 - p_avg))
        + z_beta * math.sqrt(p_control * (1 - p_control) + p_treatment * (1 - p_treatment))
    ) ** 2
    denominator = (p_control - p_treatment) ** 2

    return math.ceil(numerator / denominator)


def current_power(
    p_control: float,
    p_treatment: float,
    n_per_arm: int,
    alpha: float = 0.05,
    two_tailed: bool = True,
) -> float:
    """
    Statistical power of the current experiment given the observed N per arm.
    Returns a value between 0 and 1.
    """
    if n_per_arm <= 0 or abs(p_control - p_treatment) < 1e-10:
        return 0.0

    z_alpha   = scipy_stats.norm.ppf(1 - alpha / (2 if two_tailed else 1))
    se_pooled = math.sqrt(2 * ((p_control + p_treatment) / 2) * (1 - (p_control + p_treatment) / 2) / n_per_arm)
    se_obs    = math.sqrt(p_control * (1 - p_control) / n_per_arm + p_treatment * (1 - p_treatment) / n_per_arm)
    ncp       = abs(p_treatment - p_control) / se_obs  # non-centrality parameter

    power = scipy_stats.norm.sf(z_alpha - ncp) + scipy_stats.norm.cdf(-z_alpha - ncp)
    return round(float(power), 4)


def days_to_stat_sig(
    required_n_per_arm: int,
    current_n_per_arm: int,
    days_running: int,
) -> dict:
    """
    Estimate how many more days are needed to reach the required sample size.
    Returns a dict with 'additional_days', 'total_days', and 'daily_rate_per_arm'.
    """
    if days_running <= 0 or current_n_per_arm <= 0:
        return {"error": "Need at least 1 day of running data and positive audience size"}

    daily_rate = current_n_per_arm / days_running
    additional_users = max(0, required_n_per_arm - current_n_per_arm)
    additional_days  = math.ceil(additional_users / daily_rate) if daily_rate > 0 else None

    return {
        "required_n_per_arm":  required_n_per_arm,
        "current_n_per_arm":   current_n_per_arm,
        "daily_rate_per_arm":  round(daily_rate, 1),
        "additional_users_needed": additional_users,
        "additional_days":     additional_days,
        "total_days_estimate": (days_running + additional_days) if additional_days is not None else None,
    }


def analyze_stat_sig_requirements(
    p_control: float,
    p_treatment: float,
    current_n_control: int,
    current_n_treatment: int,
    days_running: int = 0,
    alpha: float = 0.05,
    power_target: float = 0.80,
) -> dict:
    """
    Full power analysis for a running A/B test.
    Computes actual t-statistic from observed data, plus forward-looking
    sample size and timeline projections.
    """
    result: dict = {
        "inputs": {
            "p_control":           round(p_control, 6),
            "p_treatment":         round(p_treatment, 6),
            "relative_lift_pct":   round((p_treatment - p_control) / p_control * 100, 2),
            "current_n_control":   current_n_control,
            "current_n_treatment": current_n_treatment,
            "days_running":        days_running,
            "alpha":               alpha,
            "power_target":        power_target,
        }
    }

    try:
        # ── Actual significance test from observed data ───────────────────────
        cvr_delta = p_treatment - p_control
        p_pooled  = (
            (p_treatment * current_n_treatment + p_control * current_n_control)
            / (current_n_treatment + current_n_control)
        ) if (current_n_treatment + current_n_control) > 0 else 0

        se = math.sqrt(
            p_pooled * (1 - p_pooled) * (1.0 / current_n_treatment + 1.0 / current_n_control)
        ) if (current_n_treatment > 0 and current_n_control > 0 and p_pooled > 0) else None

        t_stat = (cvr_delta / se) if se and se > 0 else None

        # Determine significance thresholds
        z_alpha = scipy_stats.norm.ppf(1 - alpha / 2)  # 1.96 for alpha=0.05
        is_significant = (abs(t_stat) >= z_alpha) if t_stat is not None else False

        # Approximate p-value
        p_value = float(2 * scipy_stats.norm.sf(abs(t_stat))) if t_stat is not None else 1.0

        # Confidence interval on CVR delta
        ci_margin = z_alpha * se if se else None
        ci_lower  = round(cvr_delta - ci_margin, 6) if ci_margin else None
        ci_upper  = round(cvr_delta + ci_margin, 6) if ci_margin else None

        result["t_statistic"]   = round(t_stat, 6) if t_stat is not None else None
        result["p_value_approx"] = round(p_value, 6)
        result["is_significant"] = is_significant
        result["cvr_delta"]     = round(cvr_delta, 6)
        result["cvr_se"]        = round(se, 8) if se else None
        result["cvr_pooled"]    = round(p_pooled, 6)
        result["ci_95_lower"]   = ci_lower
        result["ci_95_upper"]   = ci_upper

        # ── Power and forward-looking projections ─────────────────────────────
        n_per_arm = min(current_n_control, current_n_treatment)
        pow_now   = current_power(p_control, p_treatment, n_per_arm, alpha)
        result["current_power"] = pow_now

        try:
            n_required = required_sample_size(p_control, p_treatment, alpha, power_target)
            result["required_n_per_arm"] = n_required
            result["required_n_total"]   = n_required * 2

            if days_running > 0 and n_per_arm > 0:
                timeline = days_to_stat_sig(n_required, n_per_arm, days_running)
                result["timeline"]            = timeline
                result["days_to_sig"]         = timeline.get("additional_days")
                result["additional_n_needed"] = timeline.get("additional_users_needed")
        except ValueError:
            pass

        # MDE at current N
        if n_per_arm > 0:
            min_detectable = _mde(p_control, n_per_arm, alpha, power_target)
            result["min_detectable_effect"] = {
                "absolute":    round(min_detectable, 6),
                "relative_pct": round(min_detectable / p_control * 100, 2),
            }

    except Exception as e:
        result["error"] = str(e)

    return result


def _mde(p_control: float, n_per_arm: int, alpha: float, power: float) -> float:
    """Binary search for the minimum detectable effect at given N."""
    lo, hi = 1e-6, 1.0 - p_control
    for _ in range(60):
        mid = (lo + hi) / 2
        p_t = p_control + mid
        if p_t >= 1.0:
            hi = mid
            continue
        req = required_sample_size(p_control, p_t, alpha, power)
        if req <= n_per_arm:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2
