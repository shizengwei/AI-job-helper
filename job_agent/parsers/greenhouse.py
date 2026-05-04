"""Greenhouse parser."""

from __future__ import annotations

from job_agent.models import RawJobPosting
from job_agent.parsers.base import SiteParser


class GreenhouseParser(SiteParser):
    source_domain = "job-boards.greenhouse.io"

    def match(self, url: str) -> bool:
        return "greenhouse.io" in url

    def parse(self, html: str, url: str) -> RawJobPosting:
        return self._parse_with_fallbacks(
            html,
            url,
            title_selectors=["h1.app-title", "h1", ".header h1"],
            company_selectors=[".company-name", ".app-title + div", ".company"],
            location_selectors=[".location", ".app-location", '[data-qa="job-location"]'],
            description_selectors=["#content", "#app-body", "main", "body"],
        )
