from job_agent.agent.planner import QueryPlanner
from job_agent.agent.state import AgentState
from job_agent.config import Settings
from job_agent.services.llm import LLMQueryCandidate


class StubLLM:
    def __init__(self, candidates: list[LLMQueryCandidate]) -> None:
        self._candidates = candidates

    def suggest_query_candidates(self, **kwargs):  # type: ignore[no-untyped-def]
        return self._candidates


def test_planner_without_llm_uses_rule_fallback():
    settings = Settings(
        openai_api_key="",
        batch_queries=3,
        source_domains=("job-boards.greenhouse.io", "jobs.lever.co"),
    )
    state = AgentState(
        target_count=50,
        max_iterations=5,
        source_domains=settings.source_domains,
    )

    planner = QueryPlanner(settings)
    plans = planner.plan(state)

    assert len(plans) == 3
    assert all(plan.query.startswith("site:") for plan in plans)


def test_planner_with_llm_uses_llm_candidates_first():
    settings = Settings(
        openai_api_key="test-key",
        batch_queries=2,
        source_domains=("job-boards.greenhouse.io", "jobs.lever.co"),
    )
    state = AgentState(
        target_count=50,
        max_iterations=5,
        source_domains=settings.source_domains,
    )
    planner = QueryPlanner(settings)
    planner.llm = StubLLM(
        [
            LLMQueryCandidate(
                source_domain="jobs.lever.co",
                role_keyword="Machine Learning Engineer",
                campus_keyword="intern",
            ),
            LLMQueryCandidate(
                source_domain="job-boards.greenhouse.io",
                role_keyword="NLP Engineer",
                campus_keyword="new grad",
            ),
        ]
    )

    plans = planner.plan(state)

    assert len(plans) == 2
    assert plans[0].source_domain == "jobs.lever.co"
    assert plans[0].role_keyword == "Machine Learning Engineer"
    assert plans[0].campus_keyword == "intern"
