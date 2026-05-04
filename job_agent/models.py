"""Dataclasses used across the system."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass(slots=True)
class SearchPlanItem:
    source_domain: str
    role_keyword: str
    campus_keyword: str
    query: str
    page: int = 0

    @property
    def key(self) -> str:
        return "|".join(
            [
                self.source_domain,
                self.role_keyword.lower(),
                self.campus_keyword.lower(),
                str(self.page),
            ]
        )


@dataclass(slots=True)
class RawJobPosting:
    title: str
    company: str
    location: str
    salary: str
    description: str
    source: str
    job_url: str


@dataclass(slots=True)
class ClassificationResult:
    accepted: bool
    score: int
    reason: str


@dataclass(slots=True)
class JobPosting:
    title: str
    company: str
    location: str
    salary: str
    tech_tags: list[str]
    requirements: str
    source: str
    job_url: str
    match_score: int
    match_reason: str
    description: str = ""

    def to_export_row(self) -> dict[str, str]:
        return {
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "salary": self.salary,
            "tech_tags": ", ".join(self.tech_tags),
            "requirements": self.requirements,
            "source": self.source,
            "job_url": self.job_url,
        }

    def to_json_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["tech_tags"] = list(self.tech_tags)
        return payload


@dataclass(slots=True)
class RejectionRecord:
    job_url: str
    title: str
    company: str
    reason: str


@dataclass(slots=True)
class SourceStats:
    source_domain: str
    search_hits: int = 0
    fetched: int = 0
    accepted: int = 0
    rejected: int = 0
    errors: int = 0


@dataclass(slots=True)
class IterationMetrics:
    iteration: int
    queries: list[str] = field(default_factory=list)
    discovered_urls: int = 0
    parsed_jobs: int = 0
    accepted_jobs: int = 0
    rejected_jobs: int = 0
    fetch_errors: int = 0


@dataclass(slots=True)
class RunReport:
    target_count: int
    collected_count: int
    iterations: int
    queries_used: list[str]
    sources_used: list[str]
    rejection_breakdown: dict[str, int]
    output_csv: str
    output_json: str
    generated_at: str = field(
        default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds") + "Z"
    )

    def to_json_dict(self) -> dict[str, object]:
        return asdict(self)

