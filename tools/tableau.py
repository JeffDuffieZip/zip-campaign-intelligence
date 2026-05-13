"""
Data access layer for Braze campaign metrics.

Uses static mock data when TABLEAU_PAT_NAME / TABLEAU_PAT_SECRET are not set
(or when USE_MOCK_DATA=true).  Swaps transparently to live Tableau REST API
once credentials are supplied — no changes needed in the agent or tools.
"""

import os
from typing import Optional

import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# ── Decide at import time whether to use mock data ───────────────────────────

_USE_MOCK = (
    os.getenv("USE_MOCK_DATA", "").lower() == "true"
    or not os.getenv("TABLEAU_PAT_NAME")
    or not os.getenv("TABLEAU_PAT_SECRET")
)


# ── Lazy-load mock data ───────────────────────────────────────────────────────

def _mock_campaigns_df() -> pd.DataFrame:
    from tools.mock_data import CAMPAIGNS
    return pd.DataFrame(CAMPAIGNS)


# ── Live Tableau client (only instantiated when credentials are present) ──────

class _LiveTableauClient:
    """Thin wrapper around Tableau REST API views/{id}/data endpoint."""

    API_VERSION = "3.21"

    VIEW_IDS = {
        "campaign_results":  "854fa34a-383a-4b88-8c4c-83dfc24b69a0",
        "channel_summary":   "b71f7ac2-2c53-4f96-a021-4b7a07cf0f37",
        "campaign_variants": "753b04c5-2493-42e7-a8f3-a703744e7a98",
    }

    def __init__(self):
        import requests as _req
        self._req = _req
        self._server   = os.getenv("TABLEAU_SERVER", "https://us-east-1.online.tableau.com").rstrip("/")
        self._site     = os.getenv("TABLEAU_SITE", "ziptableaucloudus")
        self._pat_name = os.getenv("TABLEAU_PAT_NAME")
        self._pat_secret = os.getenv("TABLEAU_PAT_SECRET")
        self._token: Optional[str] = None
        self._site_id: Optional[str] = None
        self._cache: dict = {}

    def _sign_in(self):
        url = f"{self._server}/api/{self.API_VERSION}/auth/signin"
        body = {"credentials": {
            "personalAccessTokenName":   self._pat_name,
            "personalAccessTokenSecret": self._pat_secret,
            "site": {"contentUrl": self._site},
        }}
        r = self._req.post(url, json=body, headers={"Accept": "application/json"})
        r.raise_for_status()
        creds = r.json()["credentials"]
        self._token   = creds["token"]
        self._site_id = creds["site"]["id"]

    def _ensure_auth(self):
        if not self._token:
            self._sign_in()

    def fetch(self, view_key: str, filters: Optional[dict] = None) -> pd.DataFrame:
        from io import StringIO
        key = f"{view_key}|{tuple(sorted((filters or {}).items()))}"
        if key in self._cache:
            return self._cache[key].copy()
        self._ensure_auth()
        view_id = self.VIEW_IDS[view_key]
        url     = f"{self._server}/api/{self.API_VERSION}/sites/{self._site_id}/views/{view_id}/data"
        params  = {f"vf_{k}": v for k, v in (filters or {}).items()}
        hdrs    = {"x-tableau-auth": self._token, "Accept": "text/csv"}
        r = self._req.get(url, headers=hdrs, params=params)
        if r.status_code == 401:
            self._token = None
            self._sign_in()
            hdrs["x-tableau-auth"] = self._token
            r = self._req.get(url, headers=hdrs, params=params)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        self._cache[key] = df
        return df.copy()


_live_client: Optional[_LiveTableauClient] = None


def _get_live() -> _LiveTableauClient:
    global _live_client
    if _live_client is None:
        _live_client = _LiveTableauClient()
    return _live_client


# ── Public API ────────────────────────────────────────────────────────────────

def get_channel_summary() -> dict:
    """Aggregate channel metrics across all BAU campaigns."""
    if _USE_MOCK:
        from tools.mock_data import CHANNEL_SUMMARY
        return CHANNEL_SUMMARY

    df = _get_live().fetch("channel_summary")
    if df.empty:
        return {}
    row = df.iloc[0]
    return {
        "email_sends":          _int(row.get("EMAIL_SENDS")),
        "push_sends":           _int(row.get("PUSH_SENDS")),
        "iam_impressions":      _int(row.get("IAM_IMPRESSIONS")),
        "avg_email_click_rate": _float(row.get("Avg. Email Click Rate")),
        "avg_email_unsub_rate": _float(row.get("Avg. Email Unsubscribe Rate")),
        "avg_push_open_rate":   _float(row.get("Avg. Push Open Rate")),
    }


def list_campaigns(channel: Optional[str] = None) -> list:
    """List campaigns with key delivery metrics and overall stat sig flag."""
    if _USE_MOCK:
        from tools.mock_data import CAMPAIGNS
        rows = CAMPAIGNS
        if channel:
            rows = [c for c in rows if c.get("Campaign Canvas Channel", "").upper() == channel.upper()]
        result = []
        for c in rows:
            entry = {
                "name":         c.get("display_name", c["name"]),
                "full_name":    c["name"],
                "channel":      c.get("Campaign Canvas Channel", ""),
                "type":         c.get("Campaign Canvas Type", ""),
                "launch_date":  c.get("CAMPAIGN_LAUNCH_DATE", ""),
                "status":       c.get("STATUS", "completed"),
                "segment":      c.get("segment", ""),
                "conv_type":    c.get("conv_type", ""),
                "stat_sig":     c.get("stat_sig"),
                "t_stat":       c.get("CVR_T_STAT"),
                "i_customers":  c.get("iCustomers"),
                "i_ttv":        c.get("iTTV"),
            }
            n = c.get("TARGET_AUDIENCE") or c.get("EMAIL_SENDS") or c.get("PUSH_SENDS")
            if n:
                entry["target_audience"] = n
            result.append(entry)
        return result

    df = _get_live().fetch("campaign_results")
    if df.empty:
        return []
    if channel and "Campaign Canvas Channel" in df.columns:
        df = df[df["Campaign Canvas Channel"].str.upper() == channel.upper()]
    name_col = _find_col(df, ["Campaign Canvas Name", "Campaign Canvas Title"])
    out = []
    for _, row in df.drop_duplicates(subset=[name_col]).iterrows():
        entry = {
            "name":       str(row.get(name_col, "")).strip(),
            "channel":    str(row.get("Campaign Canvas Channel", "")).strip(),
            "launch_date": str(row.get("CAMPAIGN_LAUNCH_DATE", "")).strip(),
        }
        for col in ["EMAIL_SENDS", "PUSH_SENDS", "IAM_IMPRESSIONS"]:
            if col in df.columns:
                entry[col.lower()] = _int(row.get(col))
        out.append(entry)
    return out


def get_campaign_details(campaign_name: str) -> dict:
    """Full delivery + A/B stats for a single campaign. Accepts name, display_name,
    segment, or CAMPAIGN_CANVAS_ID (UUID)."""
    if _USE_MOCK:
        from tools.mock_data import CAMPAIGNS
        query = campaign_name.lower().strip()

        # 1. Exact UUID match (CAMPAIGN_CANVAS_ID)
        uuid_matches = [c for c in CAMPAIGNS
                        if c.get("CAMPAIGN_CANVAS_ID", "").lower() == query]
        if uuid_matches:
            c = uuid_matches[0]
            return {k: v for k, v in c.items()
                    if v is not None and v != "" and not k.startswith("_")}

        # 2. Substring match on name / display_name / segment
        matches = [
            c for c in CAMPAIGNS
            if query in c["name"].lower()
            or query in c.get("display_name", "").lower()
            or query in c.get("segment", "").lower()
        ]
        if not matches:
            available = [
                {"name": c.get("display_name", c["name"]),
                 "canvas_id": c.get("CAMPAIGN_CANVAS_ID", "")}
                for c in CAMPAIGNS
            ]
            return {
                "error": f"Campaign not found: {campaign_name!r}.",
                "hint": "Try a partial name like 'July 4th' or a full CAMPAIGN_CANVAS_ID (UUID).",
                "available_campaigns": available,
            }
        c = matches[0]
        return {k: v for k, v in c.items()
                if v is not None and v != "" and not k.startswith("_")}

    df = _get_live().fetch("campaign_results")
    name_col = _find_col(df, ["Campaign Canvas Name", "Campaign Canvas Title"])
    mask = df[name_col].str.contains(campaign_name, case=False, na=False)
    sub = df[mask]
    if sub.empty:
        return {"error": f"No data for campaign: {campaign_name!r}"}
    row = sub.iloc[0]
    return {col: row[col] for col in df.columns if row.get(col) is not None}


def get_campaign_variants(campaign_name: str) -> list:
    """Per-variant creative metrics for a campaign."""
    if _USE_MOCK:
        from tools.mock_data import CAMPAIGN_VARIANTS
        for key, variants in CAMPAIGN_VARIANTS.items():
            if campaign_name.lower() in key.lower():
                return variants
        return []

    try:
        df = _get_live().fetch("campaign_variants", {"Campaign Canvas Name": campaign_name})
    except Exception:
        df = pd.DataFrame()
    if df.empty:
        return []
    return [
        {col: row[col] for col in df.columns if row.get(col) is not None}
        for _, row in df.iterrows()
    ]


def get_benchmarks(metric: str, channel: Optional[str] = None) -> dict:
    """Percentile benchmarks (p25/p50/p75/p90) for any numeric metric."""
    if _USE_MOCK:
        from tools.mock_data import CAMPAIGNS
        rows = CAMPAIGNS
        if channel:
            rows = [c for c in rows if c.get("Campaign Canvas Channel", "").upper() == channel.upper()]

        # Fuzzy-match metric name across campaign dict keys
        key = _fuzzy_key(metric, rows)
        if key is None:
            all_numeric = sorted({
                k for c in rows for k, v in c.items()
                if isinstance(v, (int, float)) and v != 0
            })
            return {"error": f"Metric {metric!r} not found. Numeric fields available: {all_numeric[:25]}"}

        vals = [c[key] for c in rows if isinstance(c.get(key), (int, float))]
        if not vals:
            return {"error": f"No numeric values for metric {key!r}"}
        arr = np.array(vals, dtype=float)
        return {
            "metric":  key,
            "channel": channel or "ALL",
            "n":       int(len(arr)),
            "min":     round(float(arr.min()), 6),
            "p25":     round(float(np.percentile(arr, 25)), 6),
            "p50":     round(float(np.percentile(arr, 50)), 6),
            "p75":     round(float(np.percentile(arr, 75)), 6),
            "p90":     round(float(np.percentile(arr, 90)), 6),
            "max":     round(float(arr.max()), 6),
            "mean":    round(float(arr.mean()), 6),
        }

    df = _get_live().fetch("campaign_results")
    if channel and "Campaign Canvas Channel" in df.columns:
        df = df[df["Campaign Canvas Channel"].str.upper() == channel.upper()]
    col = _find_col(df, [metric])
    if col not in df.columns:
        return {"error": f"Metric {metric!r} not found."}
    vals = pd.to_numeric(df[col], errors="coerce").dropna()
    if vals.empty:
        return {"error": "No numeric data."}
    return {
        "metric": col, "channel": channel or "ALL", "n": int(len(vals)),
        "min":  round(float(vals.min()), 6),
        "p25":  round(float(np.percentile(vals, 25)), 6),
        "p50":  round(float(np.percentile(vals, 50)), 6),
        "p75":  round(float(np.percentile(vals, 75)), 6),
        "p90":  round(float(np.percentile(vals, 90)), 6),
        "max":  round(float(vals.max()), 6),
        "mean": round(float(vals.mean()), 6),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _int(val) -> Optional[int]:
    try:
        return int(str(val).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _float(val) -> Optional[float]:
    try:
        return float(str(val).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _find_col(df: pd.DataFrame, candidates: list) -> str:
    for c in candidates:
        if c in df.columns:
            return c
    return candidates[0]


def _fuzzy_key(metric: str, rows: list) -> Optional[str]:
    """Find the best-matching key in campaign dicts for a given metric name."""
    if not rows:
        return None
    all_keys = {k for c in rows for k in c.keys()}
    # exact match
    if metric in all_keys:
        return metric
    # case-insensitive
    metric_lower = metric.lower()
    for k in all_keys:
        if k.lower() == metric_lower:
            return k
    # contains
    matches = [k for k in all_keys if metric_lower in k.lower()]
    if matches:
        return matches[0]
    return None
