# Zip · Campaign Intelligence Agent

A/B testing & incrementality agent for Braze BAU campaigns. Built for executive
demos and marketing-team self-service.

## Quick start (local)

```bash
bash setup.sh           # one-shot install + launch
```

Then open http://localhost:8501.

## Modes

The app supports two modes, controlled by `.env`:

| Mode | Trigger | What it does |
|---|---|---|
| **Demo Mode** | `DEMO_MODE=true` (default) | LLM-free. Real stats engine + scripted exec narration. No API key needed. |
| **Full LLM** | `DEMO_MODE=false` AND valid `ANTHROPIC_API_KEY` | Live Claude reasoning + tool calling. |

## Deploying to Streamlit Cloud

1. Push this repo to a private GitHub repo
2. Go to https://share.streamlit.io → New app → select repo → `app.py`
3. Advanced settings → add secret: `DEMO_MODE=true`
4. Deploy

## Structure

```
app.py                  # Streamlit UI
agent.py                # LLM agent + tool dispatcher
demo_mode.py            # LLM-free router for demos
tools/
  tableau.py            # Data access (mock or live Tableau)
  stats.py              # Two-prop z-test + power analysis
  mock_data.py          # 41 real Braze BAU campaigns
```
