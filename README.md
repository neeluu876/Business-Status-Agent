# Business Status Verification Agent

A prototype that checks whether a company record marked **"out of business"**
(OOB) is really defunct, and ranks which records are most worth fixing first.

It combines several signals (website, state filing status, news, social
activity, headcount trend), asks an LLM or a rule engine to classify the
company, and then ranks a batch by how likely each record's current flag is
wrong, weighted by business impact.

Most signals in this public demo are **simulated**. The website check can be
**live**. See "What is real and what is simulated" below.

## How it works

```
company name (+ optional website, current OOB flag, impact)
        |
        v
  signals.py   website (live or simulated), filings, news, social, headcount (simulated)
        |
        v
  agent.py     Claude classifies status, or a rule engine does if no API key is set
        |        output: status, confidence active (0-100), reasoning, recommended action
        v
  prioritize_worklist()   rank by likelihood the flag is wrong x impact
```

### Prioritization

For a record flagged OOB, the flag is wrong if the company is actually active,
so the likelihood is the confidence it is active. For a record not flagged OOB,
the likelihood is the opposite. The score is that likelihood times an `impact`
weight, such as account value. The top of the worklist is the records most
likely mis-flagged that matter most.

### Safety around the LLM

The model's JSON is validated before use: status and action must come from the
allowed lists, and confidence must be a number (clamped to 0-100). If the call
fails or the output is invalid, the agent falls back to the rule engine and
records why in the `mode` field.

## What is real and what is simulated

| Signal | Source |
|---|---|
| Website reachable | Live HTTP request if you provide a website and turn on the live check. Otherwise simulated |
| Website last update, filing status, news, social, headcount | Simulated, seeded on the company name |
| LLM reasoning | Real Claude call when `ANTHROPIC_API_KEY` is set |

Because most signals are simulated, outputs show how the pipeline behaves. They
are not statements about real companies. In a real deployment, each source in
`signals.py` would be replaced by a connector, such as a Secretary of State
filing API or a news API.

## Run it

```bash
pip install -r requirements.txt

# Command line, single company (no setup needed):
python agent.py "Acme Logistics LLC"

# Interactive demo:
streamlit run app.py
```

To use Claude for the reasoning step:

```bash
export ANTHROPIC_API_KEY=your_key_here
export ANTHROPIC_MODEL=claude-sonnet-5-5   # optional override
```

On Windows PowerShell, use `$env:ANTHROPIC_API_KEY="your_key_here"`.

### Batch CSV format

| Column | Required | Meaning |
|---|---|---|
| `company_name` | yes | Company to assess |
| `website` | no | Used when the live check is on |
| `oob_flagged` | no | `true` or `false`, default `true` |
| `impact` | no | Relative value of fixing the record, default `1` |

## Tests

```bash
pytest -v
```

The tests cover deterministic signals, the ranking logic, LLM output
validation, the fallback path, and the live website check (with the network
mocked).

## Limitations

- Most signals are simulated, so there is no accuracy measurement against real
  company data.
- The live check only tests whether a website responds. A reachable site does
  not prove the business is operating, and a down site does not prove it closed.
- The rule engine's weights are hand-picked, not learned from data.

## Next steps

- Add real connectors for filing status and news.
- Hand-label a few hundred companies and report precision and recall.
- Compare the LLM's decisions with the rule engine's.
