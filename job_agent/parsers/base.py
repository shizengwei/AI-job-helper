"""Base parser utilities."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from job_agent.models import RawJobPosting
from job_agent.services.normalize import (
    clean_text,
    extract_salary,
    first_non_empty,
    load_json,
)


class SiteParser(ABC):
    source_domain: str = ""

    def match(self, url: str) -> bool:
        domain = urlparse(url).netloc.lower()
        return domain == self.source_domain or domain.endswith("." + self.source_domain)

    @abstractmethod
    def parse(self, html: str, url: str) -> RawJobPosting:
        raise NotImplementedError

    def _soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "html.parser")

    def _text(self, soup: BeautifulSoup, selectors: list[str]) -> str:
        for selector in selectors:
            node = soup.select_one(selector)
            if node:
                return clean_text(node.get_text(" ", strip=True))
        return ""

    def _description(self, soup: BeautifulSoup, selectors: list[str]) -> str:
        for selector in selectors:
            node = soup.select_one(selector)
            if node:
                return clean_text(node.get_text("\n", strip=True))
        return ""

    def _meta(self, soup: BeautifulSoup, name: str) -> str:
        node = soup.select_one(f'meta[property="{name}"], meta[name="{name}"]')
        return clean_text(node.get("content", "")) if node else ""

    def _extract_jobposting_jsonld(self, soup: BeautifulSoup) -> dict[str, Any]:
        for node in soup.select('script[type="application/ld+json"]'):
            payload = load_json(node.string or node.get_text() or "")
            candidate = self._find_jobposting_payload(payload)
            if candidate:
                return candidate
        return {}

    def _find_jobposting_payload(self, payload: object) -> dict[str, Any]:
        if isinstance(payload, dict):
            raw_type = payload.get("@type", "")
            if raw_type == "JobPosting" or (
                isinstance(raw_type, list) and "JobPosting" in raw_type
            ):
                return payload
            for value in payload.values():
                candidate = self._find_jobposting_payload(value)
                if candidate:
                    return candidate
        if isinstance(payload, list):
            for item in payload:
                candidate = self._find_jobposting_payload(item)
                if candidate:
                    return candidate
        return {}

    def _structured_title(self, payload: dict[str, Any]) -> str:
        return clean_text(str(payload.get("title") or payload.get("name") or ""))

    def _structured_company(self, payload: dict[str, Any], url: str) -> str:
        org = payload.get("hiringOrganization")
        if isinstance(org, dict):
            company = clean_text(str(org.get("name") or ""))
            if company:
                return company
        return self._company_hint_from_url(url)

    def _structured_location(self, payload: dict[str, Any]) -> str:
        value = payload.get("jobLocation") or payload.get("applicantLocationRequirements")
        return self._location_from_any(value)

    def _location_from_any(self, value: object) -> str:
        if isinstance(value, list):
            pieces = [self._location_from_any(item) for item in value]
            return clean_text(", ".join(piece for piece in pieces if piece))
        if isinstance(value, dict):
            address = value.get("address")
            if isinstance(address, dict):
                pieces = [
                    address.get("addressLocality", ""),
                    address.get("addressRegion", ""),
                    address.get("addressCountry", ""),
                ]
                return clean_text(", ".join(piece for piece in pieces if piece))
            return clean_text(str(value.get("name") or value.get("description") or ""))
        return clean_text(str(value or ""))

    def _structured_description(self, payload: dict[str, Any]) -> str:
        return clean_text(str(payload.get("description") or ""))

    def _structured_salary(self, payload: dict[str, Any], description: str) -> str:
        base_salary = payload.get("baseSalary")
        if isinstance(base_salary, dict):
            value = base_salary.get("value")
            if isinstance(value, dict):
                min_value = value.get("minValue")
                max_value = value.get("maxValue")
                unit = value.get("unitText") or ""
                if min_value and max_value:
                    return clean_text(f"${min_value} - ${max_value} / {unit}")
                if min_value:
                    return clean_text(f"${min_value} / {unit}")
        return extract_salary(description)

    def _company_hint_from_url(self, url: str) -> str:
        parts = [part for part in urlparse(url).path.split("/") if part]
        if parts:
            return clean_text(parts[0].replace("-", " ").replace("_", " ").title())
        return ""

    def _build_raw_job(
        self,
        *,
        url: str,
        title: str,
        company: str,
        location: str,
        salary: str,
        description: str,
    ) -> RawJobPosting:
        return RawJobPosting(
            title=clean_text(title),
            company=clean_text(company),
            location=clean_text(location),
            salary=clean_text(salary),
            description=clean_text(description),
            source=self.source_domain,
            job_url=url,
        )

    def _parse_with_fallbacks(
        self,
        html: str,
        url: str,
        *,
        title_selectors: list[str],
        company_selectors: list[str],
        location_selectors: list[str],
        description_selectors: list[str],
    ) -> RawJobPosting:
        soup = self._soup(html)
        payload = self._extract_jobposting_jsonld(soup)
        structured_description = self._structured_description(payload)
        description = first_non_empty(
            structured_description,
            self._description(soup, description_selectors),
        )
        return self._build_raw_job(
            url=url,
            title=first_non_empty(
                self._structured_title(payload),
                self._meta(soup, "og:title"),
                self._text(soup, title_selectors),
            ),
            company=first_non_empty(
                self._structured_company(payload, url),
                self._meta(soup, "og:site_name"),
                self._text(soup, company_selectors),
            ),
            location=first_non_empty(
                self._structured_location(payload),
                self._text(soup, location_selectors),
            ),
            salary=first_non_empty(
                self._structured_salary(payload, description),
                extract_salary(description),
            ),
            description=description,
        )

