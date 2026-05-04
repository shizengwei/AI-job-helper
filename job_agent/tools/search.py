"""Search tool used by the Agent."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx
from bs4 import BeautifulSoup

from job_agent.config import Settings
from job_agent.constants import (
    DEFAULT_USER_AGENT,
    GREENHOUSE_BOARD_TOKENS,
    LEVER_BOARD_COMPANIES,
    LEVER_BOARD_TOKENS,
    NEGATIVE_ROLE_KEYWORDS,
    POSITIVE_AI_KEYWORDS,
    POSITIVE_CAMPUS_KEYWORDS,
)
from job_agent.models import RawJobPosting, SearchPlanItem
from job_agent.services.normalize import clean_text, decode_search_result_url, extract_salary

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class BoardAPICandidate:
    job_url: str
    score: int
    raw_job: RawJobPosting


class SearchTool:
    def __init__(self, client: httpx.Client, settings: Settings) -> None:
        self.client = client
        self.settings = settings
        self._api_cache: dict[str, list[BoardAPICandidate]] = {}
        self._raw_job_cache: dict[str, RawJobPosting] = {}

    def search(self, plan: SearchPlanItem, visited_urls: set[str]) -> list[str]:
        results = self._search_board_api(plan, visited_urls)
        if results:
            return results
        results = self._search_duckduckgo(plan, visited_urls)
        if results:
            return results
        return self._search_bing(plan, visited_urls)

    def _search_board_api(
        self, plan: SearchPlanItem, visited_urls: set[str]
    ) -> list[str]:
        source_domain = self._canonical_source_domain(plan.source_domain)
        if source_domain not in self._api_cache:
            self._api_cache[source_domain] = self._load_board_candidates(source_domain)
        urls = [
            candidate.job_url
            for candidate in self._api_cache[source_domain]
            if candidate.job_url not in visited_urls
        ]
        urls = urls[: self.settings.search_results_per_query]
        if urls:
            LOGGER.info(
                "Board API returned %s URLs for source: %s",
                len(urls),
                source_domain,
            )
        return urls

    def get_cached_raw_job(self, job_url: str) -> RawJobPosting | None:
        return self._raw_job_cache.get(job_url)

    def _search_duckduckgo(
        self, plan: SearchPlanItem, visited_urls: set[str]
    ) -> list[str]:
        response = self.client.get(
            "https://html.duckduckgo.com/html/",
            params={"q": plan.query, "s": str(plan.page * 30)},
            headers={"User-Agent": DEFAULT_USER_AGENT},
            timeout=self.settings.request_timeout_seconds,
            follow_redirects=True,
        )
        response.raise_for_status()
        time.sleep(self.settings.inter_request_delay_seconds)
        soup = BeautifulSoup(response.text, "html.parser")
        urls: list[str] = []
        for node in soup.select("a.result__a, a.result-link, a[href]"):
            href = decode_search_result_url(node.get("href", ""))
            if self._accept_result_url(href, plan.source_domain, visited_urls, urls):
                urls.append(href)
            if len(urls) >= self.settings.search_results_per_query:
                break
        LOGGER.info("DuckDuckGo returned %s URLs for query: %s", len(urls), plan.query)
        return urls

    def _search_bing(self, plan: SearchPlanItem, visited_urls: set[str]) -> list[str]:
        response = self.client.get(
            "https://www.bing.com/search",
            params={"q": plan.query, "first": str(plan.page * 10 + 1)},
            headers={"User-Agent": DEFAULT_USER_AGENT},
            timeout=self.settings.request_timeout_seconds,
            follow_redirects=True,
        )
        response.raise_for_status()
        time.sleep(self.settings.inter_request_delay_seconds)
        soup = BeautifulSoup(response.text, "html.parser")
        urls: list[str] = []
        for node in soup.select("li.b_algo h2 a, a[href]"):
            href = node.get("href", "")
            if self._accept_result_url(href, plan.source_domain, visited_urls, urls):
                urls.append(href)
            if len(urls) >= self.settings.search_results_per_query:
                break
        LOGGER.info("Bing returned %s URLs for query: %s", len(urls), plan.query)
        return urls

    def _load_board_candidates(self, source_domain: str) -> list[BoardAPICandidate]:
        if source_domain == "jobs.lever.co":
            tokens = LEVER_BOARD_TOKENS
            candidates = self._load_lever_candidates(tokens)
        elif source_domain == "job-boards.greenhouse.io":
            tokens = GREENHOUSE_BOARD_TOKENS
            candidates = self._load_greenhouse_candidates(tokens)
        else:
            candidates = []
        LOGGER.info(
            "Loaded %s API candidates for source: %s",
            len(candidates),
            source_domain,
        )
        for candidate in candidates:
            self._raw_job_cache[candidate.job_url] = candidate.raw_job
        return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)

    def _load_lever_candidates(self, board_tokens: list[str]) -> list[BoardAPICandidate]:
        candidates: list[BoardAPICandidate] = []
        for token in board_tokens:
            url = f"https://api.lever.co/v0/postings/{token}?mode=json"
            response = self.client.get(
                url,
                headers={"User-Agent": DEFAULT_USER_AGENT},
                timeout=self.settings.request_timeout_seconds,
                follow_redirects=True,
            )
            if response.status_code != 200:
                continue
            for job in response.json():
                blob = clean_text(
                    " ".join(
                        [
                            str(job.get("text") or ""),
                            str(job.get("descriptionPlain") or ""),
                            str(job.get("additionalPlain") or ""),
                            str(job.get("openingPlain") or ""),
                            str(job.get("salaryDescriptionPlain") or ""),
                            clean_text(str((job.get("categories") or {}).get("location") or "")),
                        ]
                    )
                )
                score = self._score_candidate(str(job.get("text") or ""), blob)
                job_url = str(job.get("hostedUrl") or "")
                if score > 0 and job_url.startswith("http"):
                    salary_text = clean_text(
                        " ".join(
                            [
                                str(job.get("salaryDescriptionPlain") or ""),
                                str(job.get("salaryDescription") or ""),
                                str(job.get("salaryRange") or ""),
                            ]
                        )
                    )
                    raw_job = RawJobPosting(
                        title=clean_text(str(job.get("text") or "")),
                        company=LEVER_BOARD_COMPANIES.get(token, token.replace("-", " ").title()),
                        location=clean_text(str((job.get("categories") or {}).get("location") or "")),
                        salary=salary_text or extract_salary(blob),
                        description=blob,
                        source="jobs.lever.co",
                        job_url=job_url,
                    )
                    candidates.append(
                        BoardAPICandidate(job_url=job_url, score=score, raw_job=raw_job)
                    )
            time.sleep(self.settings.inter_request_delay_seconds)
        return candidates

    def _load_greenhouse_candidates(
        self, board_tokens: list[str]
    ) -> list[BoardAPICandidate]:
        candidates: list[BoardAPICandidate] = []
        for token in board_tokens:
            url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
            response = self.client.get(
                url,
                headers={"User-Agent": DEFAULT_USER_AGENT},
                timeout=self.settings.request_timeout_seconds,
                follow_redirects=True,
            )
            if response.status_code != 200:
                continue
            payload = response.json()
            for job in payload.get("jobs", []):
                blob = clean_text(
                    " ".join(
                        [
                            str(job.get("title") or ""),
                            str((job.get("location") or {}).get("name") or ""),
                            str(job.get("content") or ""),
                            self._flatten_metadata(job.get("metadata") or []),
                        ]
                    )
                )
                score = self._score_candidate(str(job.get("title") or ""), blob)
                job_url = str(job.get("absolute_url") or "")
                if score > 0 and job_url.startswith("http"):
                    raw_job = RawJobPosting(
                        title=clean_text(str(job.get("title") or "")),
                        company=clean_text(str(job.get("company_name") or "")),
                        location=clean_text(str((job.get("location") or {}).get("name") or "")),
                        salary=extract_salary(blob),
                        description=blob,
                        source="job-boards.greenhouse.io",
                        job_url=job_url,
                    )
                    candidates.append(
                        BoardAPICandidate(job_url=job_url, score=score, raw_job=raw_job)
                    )
            time.sleep(self.settings.inter_request_delay_seconds)
        return candidates

    def _flatten_metadata(self, metadata: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for item in metadata:
            if not isinstance(item, dict):
                continue
            parts.extend(str(value) for value in item.values())
        return clean_text(" ".join(parts))

    def _score_candidate(self, title: str, text: str) -> int:
        title_lower = clean_text(title).lower()
        lowered = text.lower()
        ai_score = sum(weight for keyword, weight in POSITIVE_AI_KEYWORDS.items() if keyword in lowered)
        campus_score = sum(
            weight for keyword, weight in POSITIVE_CAMPUS_KEYWORDS.items() if keyword in lowered
        )
        title_ai_bonus = (
            6 if any(keyword in title_lower for keyword in POSITIVE_AI_KEYWORDS) else 0
        )
        title_campus_bonus = (
            8 if any(keyword in title_lower for keyword in POSITIVE_CAMPUS_KEYWORDS) else 0
        )
        negative_penalty = sum(
            weight for keyword, weight in NEGATIVE_ROLE_KEYWORDS.items() if keyword in title_lower
        )
        if ai_score <= 0 or campus_score <= 0:
            return 0
        score = ai_score + campus_score + title_ai_bonus + title_campus_bonus - negative_penalty
        return max(score, 0)

    def _canonical_source_domain(self, source_domain: str) -> str:
        if source_domain.endswith("greenhouse.io"):
            return "job-boards.greenhouse.io"
        return source_domain

    def _accept_result_url(
        self,
        href: str,
        source_domain: str,
        visited_urls: set[str],
        seen_urls: list[str],
    ) -> bool:
        if not href or not href.startswith("http"):
            return False
        if source_domain not in href:
            return False
        if href in visited_urls or href in seen_urls:
            return False
        return True
