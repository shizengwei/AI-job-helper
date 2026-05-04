"""Lever parser."""

from __future__ import annotations

from job_agent.models import RawJobPosting
from job_agent.parsers.base import SiteParser


class LeverParser(SiteParser):
    source_domain = "jobs.lever.co"

    def parse(self, html: str, url: str) -> RawJobPosting:
        return self._parse_with_fallbacks(
            html,
            url,
            title_selectors=[".posting-headline h2", ".posting-headline", "h1"],
            company_selectors=[".main-header-text h3", ".posting-categories + div", ".company"],
            location_selectors=[
                ".posting-categories .sort-by-location",
                ".sort-by-location",
                ".location",
            ],
            description_selectors=[".content", ".posting", "main", "body"],
        )

