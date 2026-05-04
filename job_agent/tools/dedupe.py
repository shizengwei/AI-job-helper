"""Deduplication tool."""

from __future__ import annotations

from job_agent.models import JobPosting
from job_agent.services.normalize import dedupe_key


class DeduplicationTool:
    def __init__(self) -> None:
        self._jobs_by_url: dict[str, JobPosting] = {}
        self._jobs_by_key: dict[str, JobPosting] = {}

    def add(self, job: JobPosting) -> str:
        if job.job_url in self._jobs_by_url:
            existing = self._jobs_by_url[job.job_url]
            if self._score(job) > self._score(existing):
                self._replace(existing, job)
                return "replaced"
            return "duplicate"

        key = dedupe_key(job.title, job.company, job.location)
        existing = self._jobs_by_key.get(key)
        if existing is not None:
            if self._score(job) > self._score(existing):
                self._replace(existing, job)
                return "replaced"
            return "duplicate"

        self._jobs_by_url[job.job_url] = job
        self._jobs_by_key[key] = job
        return "added"

    def jobs(self) -> list[JobPosting]:
        return list(self._jobs_by_key.values())

    def _replace(self, old_job: JobPosting, new_job: JobPosting) -> None:
        old_key = dedupe_key(old_job.title, old_job.company, old_job.location)
        new_key = dedupe_key(new_job.title, new_job.company, new_job.location)
        self._jobs_by_url.pop(old_job.job_url, None)
        self._jobs_by_url[new_job.job_url] = new_job
        self._jobs_by_key.pop(old_key, None)
        self._jobs_by_key[new_key] = new_job

    def _score(self, job: JobPosting) -> int:
        return sum(
            [
                3 if job.salary else 0,
                2 if job.location else 0,
                2 if job.requirements else 0,
                len(job.tech_tags),
                min(len(job.description) // 300, 3),
            ]
        )

