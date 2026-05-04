"""Query planner."""

from __future__ import annotations

from job_agent.config import Settings
from job_agent.constants import CAMPUS_KEYWORDS, ROLE_KEYWORD_TIERS
from job_agent.models import SearchPlanItem
from job_agent.services.llm import OpenAILLMClient


_CAMPUS_ALIASES = {
    "new graduate": "new grad",
    "new graduates": "new grad",
    "interns": "intern",
    "internships": "internship",
    "students": "student",
    "universities": "university",
    "campus hire": "campus",
}


class QueryPlanner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.llm = (
            OpenAILLMClient(settings.openai_api_key, settings.llm_model)
            if settings.llm_enabled
            else None
        )
    # 如果LLM启用且返回了建议的查询计划，则使用LLM生成的计划。否则，使用基于规则的计划生成方法。
    def plan(self, state) -> list[SearchPlanItem]:  # type: ignore[no-untyped-def]
        llm_plans = self._plan_with_llm(state)
        if llm_plans:
            return llm_plans
        return self._plan_with_rules(state)

    def _plan_with_llm(self, state) -> list[SearchPlanItem]:  # type: ignore[no-untyped-def]
        if self.llm is None:
            return []
        # 为LLM提供每个来源域的统计信息，包括搜索命中、接受的职位数量、拒绝的职位数量和错误数量。这些统计信息可以帮助LLM更智能地建议查询计划，例如优先考虑那些之前表现较好的来源域。
        source_stats = {
            domain: {
                "search_hits": stats.search_hits,
                "accepted": stats.accepted,
                "rejected": stats.rejected,
                "errors": stats.errors,
            }
            for domain, stats in state.source_stats.items()
        }
        
        candidates = self.llm.suggest_query_candidates(
            source_domains=list(self.settings.source_domains),
            campus_keywords=list(CAMPUS_KEYWORDS),
            target_count=state.target_count,
            accepted_count=state.accepted_count,
            iteration=state.iteration,
            query_history=state.query_history[-20:],
            source_stats=source_stats,
            limit=max(self.settings.batch_queries * 2, self.settings.batch_queries),
        )
        if not candidates:
            return []

        plans: list[SearchPlanItem] = []
        for candidate in candidates:
            campus_keyword = self._normalize_campus_keyword(candidate.campus_keyword)
            if not campus_keyword:
                continue

            role_keyword = candidate.role_keyword.strip()
            source_domain = candidate.source_domain.strip().lower()
            if not role_keyword or source_domain not in self.settings.source_domains:
                continue

            query = self._build_query(source_domain, role_keyword, campus_keyword)
            plan = SearchPlanItem(
                source_domain=source_domain,
                role_keyword=role_keyword,
                campus_keyword=campus_keyword,
                query=query,
                page=0,
            )
            if plan.key in state.tried_queries:
                continue
            plans.append(plan)
            if len(plans) >= self.settings.batch_queries:
                break

        return plans

    def _plan_with_rules(self, state) -> list[SearchPlanItem]:  # type: ignore[no-untyped-def]
        plans: list[SearchPlanItem] = []
        phase = min(state.search_phase, len(ROLE_KEYWORD_TIERS) - 1)
        roles = [role for tier in ROLE_KEYWORD_TIERS[: phase + 1] for role in tier]
        domains = self._prioritized_domains(state)

        for role in roles:
            for campus in CAMPUS_KEYWORDS:
                for page in range(self.settings.max_pages_per_query):
                    for domain in domains:
                        query = self._build_query(domain, role, campus)
                        plan = SearchPlanItem(
                            source_domain=domain,
                            role_keyword=role,
                            campus_keyword=campus,
                            query=query,
                            page=page,
                        )
                        if plan.key in state.tried_queries:
                            continue
                        plans.append(plan)
                        if len(plans) >= self.settings.batch_queries:
                            return plans

        if not plans and state.search_phase < len(ROLE_KEYWORD_TIERS) - 1:
            state.search_phase += 1
            return self._plan_with_rules(state)
        return plans

    def _build_query(self, domain: str, role: str, campus: str) -> str:
        return f"site:{domain} {role} {campus}"

    def _normalize_campus_keyword(self, keyword: str) -> str:
        lowered = keyword.strip().lower()
        if lowered in CAMPUS_KEYWORDS:
            return lowered
        return _CAMPUS_ALIASES.get(lowered, "")

    def _prioritized_domains(self, state) -> list[str]:  # type: ignore[no-untyped-def]
        def sort_key(domain: str) -> tuple[int, int, int]:
            stats = state.source_stats[domain]
            return (stats.accepted, stats.search_hits, -stats.errors)

        return sorted(self.settings.source_domains, key=sort_key, reverse=True)
