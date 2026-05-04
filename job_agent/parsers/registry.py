"""Parser registry."""

from __future__ import annotations

from job_agent.models import RawJobPosting
from job_agent.parsers.ashby import AshbyParser
from job_agent.parsers.base import SiteParser
from job_agent.parsers.greenhouse import GreenhouseParser
from job_agent.parsers.lever import LeverParser


class ParserRegistry:
    def __init__(self) -> None:
        self.parsers: list[SiteParser] = [
            GreenhouseParser(),
            LeverParser(),
            AshbyParser(),
        ]

    def parse(self, html: str, url: str) -> RawJobPosting:
        for parser in self.parsers:
            if parser.match(url):
                return parser.parse(html, url)
        raise ValueError(f"No parser registered for URL: {url}")

