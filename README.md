# Zip · Campaign A/B Testing & Incrementality Agent

An AI-powered campaign intelligence tool for Zip Co's Braze BAU campaigns.
Runs two-proportion z-tests, incrementality analysis, and pre-campaign sizing —
with a full executive reporting layer built for stakeholder demos and
marketing-team self-service.

Built for the Zip Co internal hackathon.

🔗 **Live app:** [zip-campaign-intelligence.streamlit.app](https://zip-campaign-intelligence-8rr5s9bam7zettdsmbr33p.streamlit.app/)

---

## Quick start (local)

```bash
bash setup.sh           # one-shot install + launch
```

Then open [http://localhost:8501](http://localhost:8501).

---

## Modes

| Mode | Trigger | What it does |
|---|---|---|
| **Demo Mode** | `DEMO_MODE=true` (default) | LLM-free. Real stats engine + scripted exec narration. No API key needed. |
| **Full LLM** | `DEMO_MODE=false` + valid `ANTHROPIC_API_KEY` | Live Claude reasoning + tool calling. |

---

## What it does

### 💬 Campaign Analysis tab

**Three pre-built demo scenarios:**

| Scenario | Campaign | What you see |
|---|---|---|
| ✅ POST | App Deals — July 4th | Final A/B read · stat sig at 99% CI · SCALE recommendation |
| ⏳ DURING | App Deals — Jan 2025 Email | Mid-flight check · t = 0.485 · 608 days to significance · STOP |
| 📋 PRE | Best Buy New Purchasers | Pre-launch sizing **or** custom campaign sizer |

**Ad-hoc queries (type anything):**
- Look up any of the 41 campaigns by name or Canvas UUID
- Run a stat sig check with raw numbers (e.g. *"50,000 at 2.1% vs 50,000 at 1.8%"*)
- Compare two campaigns head-to-head
- Find historical analogues for any campaign
- Channel/portfolio rollup across email and push
- ROI planning matrix across CVR tiers
- Segment baseline CVRs
- Full formula & methodology guide

**Pre-campaign dual sub-section:**
- **📋 Best Buy Demo** — hard-coded Best Buy New Purchasers sizing (200K pool, 15% lift hypothesis)
- **🆕 Size a New Campaign** — interactive form: pick a segment, set population + lift target, get a dynamic sizing analysis with a plain-English recommendation: **🟢 YES — DO IT** / **🟡 DOABLE** / **🔴 RETHINK**

### 📋 Executive Report tab

Auto-generated from the last campaign analysis. Includes:
- A/B results summary with traffic-light indicators (🟢🟡🔴)
- Incrementality metrics (iCustomers, iTTV, cannibalization rate)
- Strategic alignment with Zip Co's four growth pillars
- Recommended next steps with live numbers
- Stakeholder explainer — plain-language guide to every metric

---

## Key metrics explained

| Metric | What it means |
|---|---|
| **T-statistic** | How many standard deviations the lift is from zero. Needs \|t\| > 1.96 for 95% confidence. |
| **iCustomers** | Customers who converted *because* of the campaign (not organic). = CVR delta × target audience. |
| **iTTV** | Incremental transaction value directly attributable to the campaign. |
| **Cannibalization** | Share of converting customers who would have converted anyway. < 40% = healthy. |
| **Users per group (N/Arm)** | Minimum users needed in *each* arm (control and target) to detect the expected lift. Total N = 2 × N/Arm. |
| **Days to Sig** | Estimated days to reach statistical significance at the current daily entry rate. |
| **ROI** | Fixed at 424.3% based on Zip unit economics: AOV $126.50 × NTM 41.44% ÷ $10 incentive − 1. |

---

## Recommendation labels (plain English)

The sizer always ends with one of three verdicts:

| Verdict | What it means | When you'd see it |
|---|---|---|
| 🟢 **YES — DO IT** | Test design is solid. Sample size is feasible and read window is reasonable. **Launch it.** | Healthy pool coverage (≤80%), ≤30 days to significance |
| 🟡 **DOABLE** | The math works, but with caveats — either the pool is tight or the read window is long. Launch only if you don't have a faster alternative. | Pool 80–100% OR 30–60 days to significance |
| 🔴 **RETHINK** | The current setup won't get you to a clean read. Broaden the audience, lower the confidence bar, or target a higher-lift segment. | Pool >100% OR read window >60 days |

---

## Statistical methodology

**Two-proportion z-test** (95% CI, 80% power):

```
t_stat = (CVR_target − CVR_control) / SE
SE     = √[ p_pooled × (1 − p_pooled) × (1/n_target + 1/n_control) ]
```

**Pre-campaign sample size:**

```
n_per_arm = [(z_α + z_β)² × (p1(1−p1) + p2(1−p2))] / (p1 − p2)²
```
where z_α = 1.96 (95% CI) and z_β = 0.842 (80% power).

**Incrementality:**

```
iCustomers        = (CVR_target − CVR_control) × n_target
iTTV              = (CVR_delta / CVR_target) × TTV_target
Cannibalization   = 1 − (iCustomers / converting_target)
```

---

## Deploying to Streamlit Cloud

1. Push this repo to a private GitHub repo
2. Go to [share.streamlit.io](https://share.streamlit.io) → New app → select repo → `app.py`
3. Advanced settings → add secret: `DEMO_MODE=true`
4. Deploy

---

## Repo structure

```
app.py          — Streamlit UI + executive report tab
agent.py        — LLM agent + tool dispatcher (full mode)
demo_mode.py    — LLM-free pattern-matching router (demo mode)
tools/
  tableau.py    — Data access layer (mock or live Tableau)
  stats.py      — Two-prop z-test + power analysis
  mock_data.py  — 41 real Braze BAU campaigns + segment baselines
  similarity.py — Campaign similarity scoring (6-dimension match)
```
