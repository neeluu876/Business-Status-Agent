"""
signals.py
----------
Collects the signals an analyst would use to decide whether a company is
still operating: website status, filing status, news, social activity, and
headcount trend.

Only one signal can be real in this public demo: website reachability. If a
website URL is provided and live checks are enabled, `website_active` comes
from an actual HTTP request. Every other signal is simulated, deterministically
seeded on the company name, so the project runs with no API keys.

The `website_source` field records where the website signal came from, so a
reader can always tell real data from simulated data.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, asdict

import requests


@dataclass
class CompanySignals:
    company_name: str
    website_active: bool
    last_website_update_days_ago: int
    news_mentions_last_90_days: int
    state_filing_status: str  # active | delinquent | dissolved | unknown
    social_media_last_post_days_ago: int
    employee_count_trend: str  # growing | stable | declining | unknown
    website_source: str = "simulated"  # simulated | live

    def to_dict(self):
        return asdict(self)


def _seeded_rng(company_name: str) -> random.Random:
    """Deterministic RNG per company so results are reproducible across runs."""
    seed = int(hashlib.sha256(company_name.strip().lower().encode()).hexdigest(), 16) % (2**32)
    return random.Random(seed)


def check_website(url: str, timeout: float = 5.0) -> bool:
    """Return True if the URL answers with a non-error status code.

    Any network error, timeout, or HTTP status of 400 or higher counts as
    inactive. This is a reachability check only. It does not prove the
    business is operating.
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        response = requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": "business-status-agent-demo/1.0"},
        )
        return response.status_code < 400
    except requests.RequestException:
        return False


def get_signals(company_name: str, website: str | None = None,
                live_checks: bool = False) -> CompanySignals:
    rng = _seeded_rng(company_name)

    website_active = rng.random() > 0.25
    last_update = rng.randint(0, 5) if website_active else rng.randint(180, 900)

    news_mentions = rng.choices(
        [0, rng.randint(1, 3), rng.randint(4, 15)],
        weights=[0.35, 0.4, 0.25],
    )[0]

    filing_status = rng.choices(
        ["active", "delinquent", "dissolved", "unknown"],
        weights=[0.55, 0.15, 0.15, 0.15],
    )[0]

    social_last_post = rng.randint(0, 900)

    employee_trend = rng.choices(
        ["growing", "stable", "declining", "unknown"],
        weights=[0.25, 0.35, 0.25, 0.15],
    )[0]

    source = "simulated"
    if live_checks and website:
        website_active = check_website(website)
        source = "live"
        if not website_active:
            last_update = max(last_update, 180)

    return CompanySignals(
        company_name=company_name,
        website_active=website_active,
        last_website_update_days_ago=last_update,
        news_mentions_last_90_days=news_mentions,
        state_filing_status=filing_status,
        social_media_last_post_days_ago=social_last_post,
        employee_count_trend=employee_trend,
        website_source=source,
    )
