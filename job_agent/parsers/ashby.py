"""Ashby parser."""

from __future__ import annotations

from job_agent.models import RawJobPosting
from job_agent.parsers.base import SiteParser


class AshbyParser(SiteParser):
    source_domain = "jobs.ashbyhq.com"

    def parse(self, html: str, url: str) -> RawJobPosting:
        return self._parse_with_fallbacks(
            html,
            url,
            title_selectors=["h1", "[data-testid='job-title']"],
            company_selectors=["[data-testid='company-name']", ".ashby-job-posting-company"],
            location_selectors=["[data-testid='job-location']", ".ashby-job-posting-location"],
            description_selectors=["main", "[data-testid='job-description']", "body"],
        )

