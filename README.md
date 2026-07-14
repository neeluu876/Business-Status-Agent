# Business Status Verification Agent

An agentic pipeline that verifies whether a company incorrectly flagged as
**"out of business" (OOB)** in enterprise data (e.g. D&B, CRM, or firmographic
feeds) is actually still active — and prioritizes which records a data team
should fix first.

This is a generalized, public version of a data-quality problem I work on
professionally: enterprise datasets frequently mis-flag active companies as
defunct due to stale or fragmented signals, which quietly corrupts sales
pipelines, risk models, and reporting. Manually reviewing every flagged
record doesn't scale — so this project automates the triage.

## What it does

1. **Collects signals** for a company (website activity, state filing status,
   news mentions, social activity, headcount trend).
2. **Reasons over the signals** using an LLM agent (Claude) to classify the
   company's true status, with a transparent explanation — falling back to a
   hand-built rule engine if no API key is configured, so the project runs
   out of the box.
3. **Prioritizes a worklist**: given a batch of companies, ranks them by how
   likely the current flag is *wrong* and how much remediation impact fixing
   it would have — the same logic used to decide which of thousands of
   flagged records to correct first.

## Why this matters (the real-world version)

At scale, this kind of pipeline is what lets a small data team fix tens of
thousands of mis-flagged records without manually reviewing each one —
cutting remediation time dramatically while improving data quality that
sales, risk, and reporting teams all depend on.

## Architecture

```
company name
     │
     ▼
 signals.py  ──►  raw signals (web, filings, news, social, headcount)
     │
     ▼
  agent.py   ──►  LLM reasoning (or rule-based fallback)
     │              │
     │              ▼
     │        {status, confidence, reasoning, recommended_action}
     ▼
prioritize_worklist()  ──►  ranked remediation queue
```

## Running it

```bash
pip install -r requirements.txt

# CLI, single company (works with zero setup):
python agent.py "Acme Logistics LLC"

# Full interactive demo:
streamlit run app.py
```

To enable LLM-based reasoning instead of the rule-based fallback:

```bash
export ANTHROPIC_API_KEY=your_key_here
streamlit run app.py
```

## Tech stack

Python · Anthropic Claude API · Streamlit · Pandas

## Notes on the demo data

Signals are deterministically simulated per company name so the project is
fully runnable without external API keys or network access. In a production
deployment, each signal source in `signals.py` is swapped for a real
connector (e.g. Secretary of State filing APIs, a news API, or an internal
Snowflake/Salesforce query) — the agent and prioritization logic don't change.
