"""Normalization helpers."""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Iterable
from urllib.parse import parse_qs, unquote, urlparse


WHITESPACE_RE = re.compile(r"\s+")
TAG_RE = re.compile(r"<[^>]+>")
SALARY_RE = re.compile(
    r"(\$[\d,.]+(?:\s*-\s*\$[\d,.]+)?(?:\s*/\s*(?:year|yr|hour|month))?)",
    re.IGNORECASE,
)


def clean_text(value: str) -> str:
    text = unescape(value or "")
    text = TAG_RE.sub(" ", text)
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip()


def clean_lines(value: str) -> list[str]:
    lines = []
    for raw_line in (value or "").splitlines():
        line = clean_text(raw_line)
        if line:
            lines.append(line)
    return lines


def compact_texts(parts: Iterable[str]) -> str:
    return clean_text(" ".join(part for part in parts if part))


def normalize_company(value: str) -> str:
    text = clean_text(value).lower()
    text = re.sub(r"\b(inc|llc|ltd|corp|corporation|co)\b\.?", "", text)
    return WHITESPACE_RE.sub(" ", text).strip(" -_,")


def normalize_location(value: str) -> str:
    text = clean_text(value).lower()
    text = text.replace("remote - ", "remote ")
    text = text.replace("remote,", "remote ")
    return WHITESPACE_RE.sub(" ", text).strip(" -_,")


def extract_domain(url: str) -> str:
    return urlparse(url).netloc.lower()


def dedupe_key(title: str, company: str, location: str) -> str:
    normalized_title = clean_text(title).lower()
    normalized_company = normalize_company(company)
    normalized_location = normalize_location(location)
    return "|".join([normalized_title, normalized_company, normalized_location])


def extract_salary(text: str) -> str:
    match = SALARY_RE.search(text or "")
    return clean_text(match.group(1)) if match else ""


def decode_search_result_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        query = parse_qs(parsed.query)
        if "uddg" in query and query["uddg"]:
            return unquote(query["uddg"][0])
    return url


def load_json(text: str) -> object | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def first_non_empty(*values: str) -> str:
    for value in values:
        cleaned = clean_text(value)
        if cleaned:
            return cleaned
    return ""

