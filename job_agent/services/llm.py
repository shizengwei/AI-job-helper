"""Optional LLM integration with safe fallbacks."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from job_agent.models import ClassificationResult, RawJobPosting

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class LLMExtraction:
    tech_tags: list[str]
    requirements: str


@dataclass(slots=True)
class LLMQueryCandidate:
    source_domain: str
    role_keyword: str
    campus_keyword: str


class OpenAILLMClient:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model
        self._client = None

    def _ensure_client(self):  # type: ignore[no-untyped-def]
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except ModuleNotFoundError:
            LOGGER.warning("openai package is not installed. Falling back to heuristic mode.")
            return None
        self._client = OpenAI(api_key=self.api_key)
        return self._client
    # 把一条职位信息交给 GPT，让 GPT 帮你判断它是不是目标岗位”。
    def classify_job(self, job: RawJobPosting) -> ClassificationResult | None:
        client = self._ensure_client()
        if client is None:
            return None
        prompt = (
            "You are screening jobs for an AI Engineer campus job search assistant. "
            "Decide if the role is an AI/ML/LLM-related internship or campus/new-grad role. "
            "Return strict JSON with keys accepted(boolean), score(integer 0-10), reason(string).\n\n"
            f"Title: {job.title}\n"
            f"Company: {job.company}\n"
            f"Location: {job.location}\n"
            f"Description: {job.description[:5000]}"
        )
        try:
            response = client.responses.create(
                model=self.model,
                input=prompt,
            )
            text = response.output_text
            payload = json.loads(text)
            return ClassificationResult(
                accepted=bool(payload.get("accepted")),
                score=int(payload.get("score", 0)),
                reason=str(payload.get("reason", "")),
            )
        except Exception as exc:  # pragma: no cover - network/runtime path
            LOGGER.warning("LLM classification failed: %s", exc)
            return None

    def extract_job_details(self, job: RawJobPosting) -> LLMExtraction | None:
        client = self._ensure_client()
        if client is None:
            return None
        prompt = (
            "Extract AI/ML technology tags and summarize the core requirements from the job description. "
            "Return strict JSON with keys tech_tags(array of strings) and requirements(string, <= 300 chars).\n\n"
            f"Title: {job.title}\n"
            f"Description: {job.description[:5000]}"
        )
        try:
            response = client.responses.create(
                model=self.model,
                input=prompt,
            )
            payload = json.loads(response.output_text)
            tags = [str(tag).strip() for tag in payload.get("tech_tags", []) if str(tag).strip()]
            requirements = str(payload.get("requirements", "")).strip()
            return LLMExtraction(tech_tags=tags, requirements=requirements)
        except Exception as exc:  # pragma: no cover - network/runtime path
            LOGGER.warning("LLM extraction failed: %s", exc)
            return None
    # 根据历史效果，让 LLM 帮 Agent 优化下一轮搜索策略。
    # LLM 可以分析之前的查询计划和结果，识别哪些来源域表现较好，哪些关键词更有效，以及是否需要调整查询的多样性。基于这些分析，LLM 可以建议新的查询组合，例如优先使用之前表现较好的来源域，或者引入新的关键词来覆盖未被充分挖掘的职位类型。
    def suggest_query_candidates(
        self,
        *,
        source_domains: list[str],
        campus_keywords: list[str],
        target_count: int,
        accepted_count: int,
        iteration: int,
        query_history: list[str],
        source_stats: dict[str, dict[str, int]],
        limit: int,
    ) -> list[LLMQueryCandidate] | None:
        client = self._ensure_client()
        if client is None:
            return None

        prompt = (
            "You are helping an autonomous job-search agent optimize search queries for AI Engineer campus jobs. "
            "Generate query candidates that improve recall while keeping relevance high. "
            "Return STRICT JSON only with this schema:\n"
            "{\"queries\": [{\"source_domain\": str, \"role_keyword\": str, \"campus_keyword\": str}]}\n"
            "Rules:\n"
            f"1) source_domain must be one of: {source_domains}\n"
            f"2) campus_keyword must be one of: {campus_keywords}\n"
            "3) role_keyword must target AI/ML/LLM/NLP/CV roles, not pure backend/frontend/devops/sales roles\n"
            f"4) Provide at most {max(1, min(limit, 20))} queries\n\n"
            f"Current progress: accepted={accepted_count}/{target_count}, iteration={iteration}\n"
            f"Recent queries: {query_history}\n"
            f"Source stats: {source_stats}"
        )

        try:
            response = client.responses.create(
                model=self.model,
                input=prompt,
            )
            payload = self._extract_json_payload(response.output_text)
            if payload is None:
                return None
            raw_queries = payload.get("queries", [])
            if not isinstance(raw_queries, list):
                return None

            allowed_sources = set(source_domains)
            allowed_campus = set(keyword.lower() for keyword in campus_keywords)
            candidates: list[LLMQueryCandidate] = []
            for item in raw_queries:
                if not isinstance(item, dict):
                    continue
                source_domain = str(item.get("source_domain", "")).strip().lower()
                role_keyword = str(item.get("role_keyword", "")).strip()
                campus_keyword = str(item.get("campus_keyword", "")).strip().lower()
                if source_domain not in allowed_sources:
                    continue
                if campus_keyword not in allowed_campus:
                    continue
                if not role_keyword:
                    continue
                candidates.append(
                    LLMQueryCandidate(
                        source_domain=source_domain,
                        role_keyword=role_keyword,
                        campus_keyword=campus_keyword,
                    )
                )
                if len(candidates) >= limit:
                    break
            return candidates
        except Exception as exc:  # pragma: no cover - network/runtime path
            LOGGER.warning("LLM query suggestion failed: %s", exc)
            return None

    def _extract_json_payload(self, text: str) -> dict[str, Any] | None:
        payload = self._loads_json(text)
        if isinstance(payload, dict):
            return payload

        match = re.search(r"```(?:json)?\\s*(\{.*?\})\\s*```", text, re.DOTALL)
        if match:
            payload = self._loads_json(match.group(1))
            if isinstance(payload, dict):
                return payload

        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            payload = self._loads_json(text[start : end + 1])
            if isinstance(payload, dict):
                return payload

        return None

    def _loads_json(self, text: str) -> Any | None:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
