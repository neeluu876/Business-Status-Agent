"""
agent.py
--------
Takes company signals and decides:
  1. status       (Active / Likely Active / Uncertain / Likely Defunct / Defunct)
  2. confidence   (0-100, confidence the company is genuinely ACTIVE)
  3. reasoning    (short explanation)
  4. action       (No action / Flag for review / Escalate for correction)

Two modes:
  - LLM mode (when ANTHROPIC_API_KEY is set): Claude reasons over the signals
    and returns JSON, which is validated before use. Any bad output falls back
    to the rule-based mode.
  - Rule-based mode (no API key): a transparent scoring function.

`prioritize_worklist` ranks a batch by how likely each record's current flag
is wrong, weighted by business impact.
"""

from __future__ import annotations

import json
import os

from signals import CompanySignals, get_signals

STATUS_OPTIONS = ["Active", "Likely Active", "Uncertain", "Likely Defunct", "Defunct"]
ACTION_OPTIONS = [
    "No action needed",
    "Flag for manual review",
    "Escalate: correct OOB flag / remove from active pipeline",
]
MODEL_NAME = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")


def _rule_based_assessment(s: CompanySignals) -> dict:
    """Transparent scoring heuristic used when no LLM key is available."""
    score = 50  # start neutral; score = confidence the company is ACTIVE (0-100)

    if s.website_active:
        score += 20
    else:
        score -= 15

    if s.last_website_update_days_ago <= 30:
        score += 10
    elif s.last_website_update_days_ago >= 365:
        score -= 15

    if s.news_mentions_last_90_days >= 4:
        score += 10
    elif s.news_mentions_last_90_days == 0:
        score -= 5

    if s.state_filing_status == "active":
        score += 20
    elif s.state_filing_status == "dissolved":
        score -= 35
    elif s.state_filing_status == "delinquent":
        score -= 10

    if s.social_media_last_post_days_ago <= 60:
        score += 5
    elif s.social_media_last_post_days_ago >= 365:
        score -= 5

    if s.employee_count_trend == "growing":
        score += 10
    elif s.employee_count_trend == "declining":
        score -= 10

    score = max(0, min(100, score))

    if score >= 80:
        status = "Active"
    elif score >= 60:
        status = "Likely Active"
    elif score >= 40:
        status = "Uncertain"
    elif score >= 20:
        status = "Likely Defunct"
    else:
        status = "Defunct"

    if status in ("Active", "Likely Active"):
        action = ACTION_OPTIONS[0]
    elif status == "Uncertain":
        action = ACTION_OPTIONS[1]
    else:
        action = ACTION_OPTIONS[2]

    reasoning_bits = [
        "website is active" if s.website_active else "website appears inactive or unreachable",
        f"website signal is {s.website_source}",
        f"last updated {s.last_website_update_days_ago}d ago",
        f"state filing status: {s.state_filing_status}",
        f"{s.news_mentions_last_90_days} news mentions in last 90 days",
        f"headcount trend: {s.employee_count_trend}",
    ]
    reasoning = "Based on signals: " + "; ".join(reasoning_bits) + "."

    return {
        "status": status,
        "confidence": score,
        "reasoning": reasoning,
        "recommended_action": action,
        "mode": "rule-based",
    }


def _build_prompt(s: CompanySignals) -> str:
    return f"""You are a data-quality analyst deciding whether a company is still operating.

Company: {s.company_name}

Signals collected:
- Website active: {s.website_active} (source: {s.website_source})
- Days since last website update: {s.last_website_update_days_ago}
- News mentions (last 90 days): {s.news_mentions_last_90_days}
- State filing status: {s.state_filing_status}
- Days since last social media post: {s.social_media_last_post_days_ago}
- Employee count trend: {s.employee_count_trend}

Classify the company's true status and respond with ONLY valid JSON (no markdown fences),
in this exact schema:
{{
  "status": one of {STATUS_OPTIONS},
  "confidence": integer 0-100 (confidence the company is genuinely ACTIVE),
  "reasoning": 1-2 sentence explanation citing the specific signals,
  "recommended_action": one of {ACTION_OPTIONS}
}}"""


def parse_llm_response(raw_text: str) -> dict:
    """Parse and validate the model's JSON. Raises ValueError if it is unusable."""
    text = raw_text.strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"not valid JSON: {exc}") from exc

    if parsed.get("status") not in STATUS_OPTIONS:
        raise ValueError(f"invalid status: {parsed.get('status')!r}")
    if parsed.get("recommended_action") not in ACTION_OPTIONS:
        raise ValueError(f"invalid action: {parsed.get('recommended_action')!r}")
    try:
        confidence = int(parsed["confidence"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("confidence missing or not a number") from exc
    if not isinstance(parsed.get("reasoning"), str) or not parsed["reasoning"].strip():
        raise ValueError("reasoning missing")

    parsed["confidence"] = max(0, min(100, confidence))
    parsed["mode"] = "llm"
    return parsed


def _llm_assessment(s: CompanySignals) -> dict:
    from anthropic import Anthropic

    client = Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=300,
        messages=[{"role": "user", "content": _build_prompt(s)}],
    )
    return parse_llm_response(response.content[0].text)


def assess_company(company_name: str, website: str | None = None,
                   oob_flagged: bool = True, impact: float = 1.0,
                   live_checks: bool = False) -> dict:
    """Collect signals, run the agent, and return a full assessment.

    oob_flagged: True if the record is currently marked out of business.
    impact: relative business value of fixing this record (for prioritization).
    """
    s = get_signals(company_name, website=website, live_checks=live_checks)

    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            result = _llm_assessment(s)
        except Exception as e:  # network error, bad output, auth problem, etc.
            result = _rule_based_assessment(s)
            result["mode"] = f"rule-based (LLM call failed: {e})"
    else:
        result = _rule_based_assessment(s)

    result["company_name"] = company_name
    result["oob_flagged"] = oob_flagged
    result["impact"] = impact
    result["signals"] = s.to_dict()
    return result


def flag_error_likelihood(assessment: dict) -> float:
    """Probability (0-1) that the record's current flag is wrong.

    A record flagged out of business is wrong if the company is really active,
    so the likelihood is the confidence it is active. A record flagged active
    is wrong if the company is really defunct, so it is the opposite.
    """
    active_confidence = assessment["confidence"] / 100
    if assessment.get("oob_flagged", True):
        return active_confidence
    return 1 - active_confidence


def prioritize_worklist(assessments: list[dict]) -> list[dict]:
    """Rank records by (likelihood the flag is wrong) x (impact of fixing it)."""
    for a in assessments:
        a["flag_error_likelihood"] = round(flag_error_likelihood(a), 3)
        a["priority_score"] = round(a["flag_error_likelihood"] * a.get("impact", 1.0), 3)

    ranked = sorted(assessments, key=lambda a: a["priority_score"], reverse=True)
    for i, a in enumerate(ranked, start=1):
        a["priority_rank"] = i
    return ranked


if __name__ == "__main__":
    import sys

    name = sys.argv[1] if len(sys.argv) > 1 else "Acme Logistics LLC"
    print(json.dumps(assess_company(name), indent=2))
