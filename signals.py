"""
signals.py
-----------
Generates the raw "signals" an analyst would normally pull from disparate
systems (website checks, state filing records, news mentions, social activity,
D&B-style firmographic feeds) before deciding whether a company is truly
active or out-of-business (OOB).

For this public demo, signals are deterministically simulated (seeded on the
company name) so the project runs with zero external API keys or network
access. In a production setting, each `get_*` function below would be swapped
for a real connector (e.g. a website uptime check, Secretary of State filing
API, a news API, or a D&B/Snowflake query) without changing anything else in
the pipeline.
"""

import hashlib
import random
from dataclasses import dataclass, asdict


@dataclass
class CompanySignals:
    company_name: str
    website_active: bool
    last_website_update_days_ago: int
    news_mentions_last_90_days: int
    state_filing_status: str  # active | delinquent | dissolved | unknown
    social_media_last_post_days_ago: int
    employee_count_trend: str  # growing | stable | declining | unknown

    def to_dict(self):
        return asdict(self)


def _seeded_rng(company_name: str) -> random.Random:
    """Deterministic RNG per company so results are reproducible across runs."""
    seed = int(hashlib.sha256(company_name.strip().lower().encode()).hexdigest(), 16) % (2**32)
    return random.Random(seed)


def get_signals(company_name: str) -> CompanySignals:
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

    return CompanySignals(
        company_name=company_name,
        website_active=website_active,
        last_website_update_days_ago=last_update,
        news_mentions_last_90_days=news_mentions,
        state_filing_status=filing_status,
        social_media_last_post_days_ago=social_last_post,
        employee_count_trend=employee_trend,
    )
