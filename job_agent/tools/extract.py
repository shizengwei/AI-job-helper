"""Skill and requirements extraction."""

from __future__ import annotations

import re

from job_agent.config import Settings
from job_agent.constants import MAX_SUMMARY_CHARS, REQUIREMENT_HINTS, TECH_TAG_CATALOG
from job_agent.models import RawJobPosting
from job_agent.services.llm import OpenAILLMClient
from job_agent.services.normalize import clean_lines, clean_text


class SkillExtractionTool:
    def __init__(self, settings: Settings) -> None:
        self.llm = (
            OpenAILLMClient(settings.openai_api_key, settings.llm_model)
            if settings.llm_enabled
            else None
        )

    def extract(self, job: RawJobPosting) -> tuple[list[str], str]:
        if self.llm is not None:
            llm_result = self.llm.extract_job_details(job)
            if llm_result is not None:
                tags = llm_result.tech_tags or self._heuristic_tags(job.description)
                summary = llm_result.requirements or self._heuristic_requirements(job.description)
                return tags, summary
        return self._heuristic_tags(job.description), self._heuristic_requirements(job.description)

    def _heuristic_tags(self, description: str) -> list[str]:
        text = description.lower()
        tags = [
            label
            for label, keywords in TECH_TAG_CATALOG.items()
            if any(keyword in text for keyword in keywords)
        ]
        return sorted(tags)

    def _heuristic_requirements(self, description: str) -> str:
        lines = clean_lines(description)
        candidates = [
            line
            for line in lines
            if any(hint in line.lower() for hint in REQUIREMENT_HINTS)
        ]
        if not candidates:
            sentence_candidates = [
                clean_text(part)
                for part in re.split(r"(?<=[.!?])\s+", description)
                if any(hint in part.lower() for hint in REQUIREMENT_HINTS)
            ]
            candidates = [part for part in sentence_candidates if part]
        summary = " ".join(candidates[:3]) if candidates else clean_text(description)[:MAX_SUMMARY_CHARS]
        return summary[:MAX_SUMMARY_CHARS]

