"""
agent.py
--------
Core agent that takes raw company signals and decides:
  1. status classification   (Active / Likely Active / Uncertain / Likely Defunct / Defunct)
  2. confidence score         (0-100)
  3. human-readable reasoning
  4. recommended action       (No action / Flag for review / Escalate for correction)

Two modes:
  - LLM mode (default if ANTHROPIC_API_KEY is set): Claude reasons over the
    signals like an analyst would, and returns structured JSON.
  - Rule-based fallback mode (no API key required): a transparent, hand-built
    scoring function so the project is fully runnable/demo-able out of the box.

This mirrors a real enterprise data-quality workflow: cross-referencing
multiple weak signals (web presence, filings, news, socials, headcount trend)
to correct incorrectly-flagged "out of business" records at scale, and to
prioritize which records to fix first.
"""

import os
import json
from signals import CompanySignals

STATUS_OPTIONS = ["Active", "Likely Active", "Uncertain", "Likely Defunct", "Defunct"]


def _rule_based_assessment(s: CompanySignals) -> dict:
    """Transparent scoring heuristic used when no LLM key is available."""
    score = 50  # start neutral, out of 100 "confidence company is ACTIVE"

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
        action = "No action needed"
    elif status == "Uncertain":
        action = "Flag for manual review"
    else:
        action = "Escalate: correct OOB flag / remove from active pipeline"

    reasoning_bits = []
    reasoning_bits.append(
        "website is active" if s.website_active else "website appears inactive/unreachable"
    )
    reasoning_bits.append(f"last updated {s.last_website_update_days_ago}d ago")
    reasoning_bits.append(f"state filing status: {s.state_filing_status}")
    reasoning_bits.append(f"{s.news_mentions_last_90_days} news mentions in last 90 days")
    reasoning_bits.append(f"headcount trend: {s.employee_count_trend}")
    reasoning = "Based on signals — " + "; ".join(reasoning_bits) + "."

    return {
        "status": status,
        "confidence": score,
        "reasoning": reasoning,
        "recommended_action": action,
        "mode": "rule-based",
    }


def _build_prompt(s: CompanySignals) -> str:
    return f"""You are a data-quality analyst verifying whether a company record that has
been auto-flagged as "out of business" (OOB) is actually correct.

Company: {s.company_name}

Signals collected:
- Website active: {s.website_active}
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
  "recommended_action": one of ["No action needed", "Flag for manual review", "Escalate: correct OOB flag / remove from active pipeline"]
}}"""


def _llm_assessment(s: CompanySignals) -> dict:
    from anthropic import Anthropic

    client = Anthropic()  # reads ANTHROPIC_API_KEY from environment
    prompt = _build_prompt(s)

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = response.content[0].text.strip()
    raw_text = raw_text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    parsed = json.loads(raw_text)
    parsed["mode"] = "llm"
    return parsed


def assess_company(company_name: str) -> dict:
    """Main entry point: collect signals, run the agent, return a full assessment."""
    s = get_signals_safe(company_name)

    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            result = _llm_assessment(s)
        except Exception as e:
            result = _rule_based_assessment(s)
            result["mode"] = f"rule-based (LLM call failed: {e})"
    else:
        result = _rule_based_assessment(s)

    result["company_name"] = company_name
    result["signals"] = s.to_dict()
    return result


def get_signals_safe(company_name: str) -> CompanySignals:
    from signals import get_signals
    return get_signals(company_name)


def prioritize_worklist(assessments: list[dict]) -> list[dict]:
    """
    Ranks a batch of assessments by remediation priority:
    priority = uncertainty (distance of confidence from the extremes) weighted
    toward companies currently mis-flagged as high-confidence Defunct/Active,
    since those are the most likely to be *wrong* and highest-value to fix first.
    """
    def priority_score(a: dict) -> float:
        conf = a["confidence"]
        # Highest priority: confidently "Active" signals but currently sitting
        # in a defunct-flagged pipeline (biggest business impact if wrong),
        # and mid-confidence "Uncertain" cases needing review.
        distance_from_middle = abs(conf - 50)
        return distance_from_middle if a["status"] in ("Active", "Defunct") else distance_from_middle * 0.6

    ranked = sorted(assessments, key=priority_score, reverse=True)
    for i, a in enumerate(ranked, start=1):
        a["priority_rank"] = i
    return ranked


if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "Acme Logistics LLC"
    result = assess_company(name)
    print(json.dumps(result, indent=2))
