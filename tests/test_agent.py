import json
import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent  # noqa: E402
import signals  # noqa: E402


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def make(name, confidence, oob_flagged=True, impact=1.0):
    return {"company_name": name, "confidence": confidence, "oob_flagged": oob_flagged,
            "impact": impact, "status": "x"}


def test_signals_are_deterministic():
    a = signals.get_signals("Acme Logistics LLC")
    b = signals.get_signals("Acme Logistics LLC")
    assert a == b
    assert a.website_source == "simulated"


def test_assessment_has_expected_fields():
    result = agent.assess_company("Acme Logistics LLC")
    for key in ("status", "confidence", "reasoning", "recommended_action", "mode", "signals"):
        assert key in result
    assert result["status"] in agent.STATUS_OPTIONS
    assert 0 <= result["confidence"] <= 100


def test_flagged_but_active_ranks_above_flagged_and_defunct():
    ranked = agent.prioritize_worklist([make("defunct", 10), make("active", 90)])
    assert ranked[0]["company_name"] == "active"
    assert ranked[0]["priority_rank"] == 1


def test_impact_breaks_ties_between_equally_likely_errors():
    ranked = agent.prioritize_worklist([make("small", 80, impact=1), make("big", 80, impact=5)])
    assert ranked[0]["company_name"] == "big"


def test_not_flagged_record_is_wrong_when_defunct():
    ranked = agent.prioritize_worklist([
        make("flagged-active-looking", 90, oob_flagged=True),
        make("unflagged-defunct-looking", 5, oob_flagged=False),
        make("unflagged-active-looking", 95, oob_flagged=False),
    ])
    assert ranked[-1]["company_name"] == "unflagged-active-looking"


def test_parse_llm_response_accepts_valid_json():
    raw = json.dumps({"status": "Active", "confidence": 120,
                      "reasoning": "Website live.", "recommended_action": agent.ACTION_OPTIONS[0]})
    parsed = agent.parse_llm_response("```json\n" + raw + "\n```")
    assert parsed["confidence"] == 100
    assert parsed["mode"] == "llm"


@pytest.mark.parametrize("bad", [
    "not json",
    json.dumps({"status": "Maybe", "confidence": 5, "reasoning": "x",
                "recommended_action": agent.ACTION_OPTIONS[0]}),
    json.dumps({"status": "Active", "confidence": "high", "reasoning": "x",
                "recommended_action": agent.ACTION_OPTIONS[0]}),
    json.dumps({"status": "Active", "confidence": 5, "reasoning": "x",
                "recommended_action": "Do something else"}),
])
def test_parse_llm_response_rejects_bad_output(bad):
    with pytest.raises(ValueError):
        agent.parse_llm_response(bad)


def test_llm_failure_falls_back_to_rules(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")

    def boom(_):
        raise RuntimeError("no network")

    monkeypatch.setattr(agent, "_llm_assessment", boom)
    result = agent.assess_company("Acme Logistics LLC")
    assert result["mode"].startswith("rule-based (LLM call failed")


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


def test_live_website_check_success(monkeypatch):
    monkeypatch.setattr(signals.requests, "get", lambda *a, **k: FakeResponse(200))
    s = signals.get_signals("Acme", website="example.com", live_checks=True)
    assert s.website_active is True
    assert s.website_source == "live"


def test_live_website_check_error_status_and_exception(monkeypatch):
    monkeypatch.setattr(signals.requests, "get", lambda *a, **k: FakeResponse(404))
    assert signals.check_website("example.com") is False

    def raise_error(*a, **k):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(signals.requests, "get", raise_error)
    assert signals.check_website("example.com") is False


def test_live_check_is_skipped_without_website(monkeypatch):
    def fail(*a, **k):
        raise AssertionError("network should not be used")

    monkeypatch.setattr(signals.requests, "get", fail)
    s = signals.get_signals("Acme", website=None, live_checks=True)
    assert s.website_source == "simulated"
