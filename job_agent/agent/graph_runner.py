"""LangGraph-based agent runtime."""

from __future__ import annotations

import logging
from typing import Literal, TypedDict, cast

import httpx

try:
    from langgraph.graph import END, START, StateGraph
except ImportError as exc:  # pragma: no cover - depends on optional environment setup
    raise RuntimeError(
        "LangGraph runtime requires the 'langgraph' package. "
        "Run `python3 -m pip install -e .`, or set AGENT_RUNTIME=classic."
    ) from exc

from job_agent.agent.executor import AgentExecutor
from job_agent.agent.planner import QueryPlanner
from job_agent.agent.reflector import Reflector
from job_agent.agent.reporting import export_run_report
from job_agent.agent.state import AgentState
from job_agent.config import Settings
from job_agent.models import (
    ClassificationResult,
    IterationMetrics,
    JobPosting,
    RawJobPosting,
    RejectionRecord,
    RunReport,
    SearchPlanItem,
    SourceStats,
)
from job_agent.parsers.registry import ParserRegistry
from job_agent.tools.classify import JobClassifier
from job_agent.tools.dedupe import DeduplicationTool
from job_agent.tools.export import ExportTool
from job_agent.tools.extract import SkillExtractionTool
from job_agent.tools.fetch import FetchTool
from job_agent.tools.search import SearchTool

LOGGER = logging.getLogger(__name__)

PLAN_NODE = "plan_queries"
SEARCH_NODE = "search_sources"
PROCESS_NODE = "process_candidates"
REFLECT_NODE = "reflect_strategy"
EXPORT_NODE = "export_result"


class GraphState(TypedDict):
    target_count: int
    max_iterations: int
    source_domains: tuple[str, ...]
    iteration: int
    search_phase: int
    iterations_without_progress: int
    accepted_jobs: list[JobPosting]
    rejected_jobs: list[RejectionRecord]
    visited_urls: set[str]
    tried_queries: set[str]
    query_history: list[str]
    source_stats: dict[str, SourceStats]
    plans: list[SearchPlanItem]
    current_plan: SearchPlanItem | None
    pending_urls: list[str]
    pending_url_sources: dict[str, str]
    current_url: str | None
    current_raw_job: RawJobPosting | None
    classification_result: ClassificationResult | None
    current_job: JobPosting | None
    last_error: str | None
    metrics: IterationMetrics | None
    route_decision: str
    report: RunReport | None


def build_initial_graph_state(settings: Settings) -> GraphState:
    state = AgentState(
        target_count=settings.target_count,
        max_iterations=settings.max_iterations,
        source_domains=settings.source_domains,
    )
    return {
        **_agent_state_update(state),
        "plans": [],
        "current_plan": None,
        "pending_urls": [],
        "pending_url_sources": {},
        "current_url": None,
        "current_raw_job": None,
        "classification_result": None,
        "current_job": None,
        "last_error": None,
        "metrics": None,
        "route_decision": START,
        "report": None,
    }


def to_agent_state(graph_state: GraphState) -> AgentState:
    return AgentState(
        target_count=graph_state["target_count"],
        max_iterations=graph_state["max_iterations"],
        source_domains=graph_state["source_domains"],
        iteration=graph_state["iteration"],
        search_phase=graph_state["search_phase"],
        iterations_without_progress=graph_state["iterations_without_progress"],
        accepted_jobs=graph_state["accepted_jobs"],
        rejected_jobs=graph_state["rejected_jobs"],
        visited_urls=graph_state["visited_urls"],
        tried_queries=graph_state["tried_queries"],
        query_history=graph_state["query_history"],
        source_stats=graph_state["source_stats"],
    )


def _agent_state_update(state: AgentState) -> dict[str, object]:
    return {
        "target_count": state.target_count,
        "max_iterations": state.max_iterations,
        "source_domains": state.source_domains,
        "iteration": state.iteration,
        "search_phase": state.search_phase,
        "iterations_without_progress": state.iterations_without_progress,
        "accepted_jobs": state.accepted_jobs,
        "rejected_jobs": state.rejected_jobs,
        "visited_urls": state.visited_urls,
        "tried_queries": state.tried_queries,
        "query_history": state.query_history,
        "source_stats": state.source_stats,
    }


def _next_plan(plans: list[SearchPlanItem]) -> SearchPlanItem | None:
    return plans[0] if plans else None


class LangGraphAgentRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run(self) -> RunReport:
        initial_state = build_initial_graph_state(self.settings)

        with httpx.Client() as client:
            graph = self._build_graph(client)
            final_state = graph.invoke(
                initial_state,
                config={"recursion_limit": self._recursion_limit()},
            )

        report = cast(RunReport | None, final_state.get("report"))
        if report is None:
            raise RuntimeError("LangGraph run finished without producing a report.")
        return report

    def _build_graph(self, client: httpx.Client):  # type: ignore[no-untyped-def]
        export_tool = ExportTool(self.settings.outputs_dir)
        executor = AgentExecutor(
            search_tool=SearchTool(client, self.settings),
            fetch_tool=FetchTool(client, self.settings),
            parser_registry=ParserRegistry(),
            classifier=JobClassifier(self.settings),
            extractor=SkillExtractionTool(self.settings),
            deduper=DeduplicationTool(),
        )
        planner = QueryPlanner(self.settings)
        reflector = Reflector()

        def plan_queries(graph_state: GraphState) -> dict[str, object]:
            state = to_agent_state(graph_state)
            state.iteration += 1
            plans = planner.plan(state)
            if not plans:
                LOGGER.info("Planner produced no more queries. Stopping.")
                return {
                    **_agent_state_update(state),
                    "plans": [],
                    "current_plan": None,
                    "pending_urls": [],
                    "pending_url_sources": {},
                    "current_url": None,
                    "metrics": None,
                    "route_decision": EXPORT_NODE,
                }

            LOGGER.info(
                "Starting iteration %s with %s planned queries.",
                state.iteration,
                len(plans),
            )
            return {
                **_agent_state_update(state),
                "plans": plans,
                "current_plan": _next_plan(plans),
                "metrics": None,
                "route_decision": SEARCH_NODE,
            }

        def search_sources(graph_state: GraphState) -> dict[str, object]:
            state = to_agent_state(graph_state)
            pending_urls, pending_url_sources, metrics = executor.search_sources(
                state,
                graph_state["plans"],
            )
            return {
                **_agent_state_update(state),
                "pending_urls": pending_urls,
                "pending_url_sources": pending_url_sources,
                "current_url": pending_urls[0] if pending_urls else None,
                "metrics": metrics,
                "route_decision": PROCESS_NODE,
            }

        def process_candidates(graph_state: GraphState) -> dict[str, object]:
            state = to_agent_state(graph_state)
            metrics = graph_state["metrics"] or IterationMetrics(
                iteration=state.iteration
            )
            metrics = executor.process_candidates(
                state,
                graph_state["pending_urls"],
                graph_state["pending_url_sources"],
                metrics,
            )
            return {
                **_agent_state_update(state),
                "pending_urls": [],
                "pending_url_sources": {},
                "current_url": None,
                "metrics": metrics,
                "route_decision": REFLECT_NODE,
            }

        def reflect_strategy(graph_state: GraphState) -> dict[str, object]:
            state = to_agent_state(graph_state)
            metrics = graph_state["metrics"]
            if metrics is not None:
                reflector.update(state, metrics)
            return {
                **_agent_state_update(state),
                "route_decision": EXPORT_NODE if state.should_stop() else PLAN_NODE,
            }

        def export_result(graph_state: GraphState) -> dict[str, object]:
            report = export_run_report(to_agent_state(graph_state), export_tool)
            return {"report": report, "route_decision": END}

        def route_entry(
            graph_state: GraphState,
        ) -> Literal["plan_queries", "export_result"]:
            if to_agent_state(graph_state).should_stop():
                return EXPORT_NODE
            return PLAN_NODE

        def route_after_planning(
            graph_state: GraphState,
        ) -> Literal["search_sources", "export_result"]:
            if graph_state["plans"]:
                return SEARCH_NODE
            return EXPORT_NODE

        def route_after_reflection(
            graph_state: GraphState,
        ) -> Literal["plan_queries", "export_result"]:
            if to_agent_state(graph_state).should_stop():
                return EXPORT_NODE
            return PLAN_NODE

        graph = StateGraph(GraphState)
        graph.add_node(PLAN_NODE, plan_queries)
        graph.add_node(SEARCH_NODE, search_sources)
        graph.add_node(PROCESS_NODE, process_candidates)
        graph.add_node(REFLECT_NODE, reflect_strategy)
        graph.add_node(EXPORT_NODE, export_result)

        graph.add_conditional_edges(
            START,
            route_entry,
            {PLAN_NODE: PLAN_NODE, EXPORT_NODE: EXPORT_NODE},
        )
        graph.add_conditional_edges(
            PLAN_NODE,
            route_after_planning,
            {SEARCH_NODE: SEARCH_NODE, EXPORT_NODE: EXPORT_NODE},
        )
        graph.add_edge(SEARCH_NODE, PROCESS_NODE)
        graph.add_edge(PROCESS_NODE, REFLECT_NODE)
        graph.add_conditional_edges(
            REFLECT_NODE,
            route_after_reflection,
            {PLAN_NODE: PLAN_NODE, EXPORT_NODE: EXPORT_NODE},
        )
        graph.add_edge(EXPORT_NODE, END)
        return graph.compile()

    def _recursion_limit(self) -> int:
        return max(25, self.settings.max_iterations * 5 + 10)
