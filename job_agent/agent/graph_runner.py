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
NEXT_CANDIDATE_NODE = "next_candidate"
FETCH_NODE = "fetch_or_load_candidate"
PARSE_NODE = "parse_job"
EVALUATE_NODE = "evaluate_job"
EXTRACT_NODE = "extract_job_details"
DEDUPE_NODE = "deduplicate_and_merge"
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
    current_url_source: str | None
    current_html: str | None
    current_raw_job: RawJobPosting | None
    classification_result: ClassificationResult | None
    current_tech_tags: list[str]
    current_requirements: str
    current_job: JobPosting | None
    last_error: str | None
    metrics: IterationMetrics | None
    progress_events: list[str]
    fallback_events: list[str]
    checkpoint_backend: str
    checkpoint_thread_id: str
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
        "current_url_source": None,
        "current_html": None,
        "current_raw_job": None,
        "classification_result": None,
        "current_tech_tags": [],
        "current_requirements": "",
        "current_job": None,
        "last_error": None,
        "metrics": None,
        "progress_events": [],
        "fallback_events": [],
        "checkpoint_backend": settings.checkpoint_backend,
        "checkpoint_thread_id": settings.checkpoint_thread_id,
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


def _append_event(graph_state: GraphState, field: str, event: str) -> list[str]:
    if not event:
        return list(graph_state[field])  # type: ignore[index]
    if field == "progress_events":
        LOGGER.info(event)
    elif field == "fallback_events":
        LOGGER.info("Fallback: %s", event)
    return [*graph_state[field], event]  # type: ignore[index]


def _append_events(graph_state: GraphState, field: str, events: list[str]) -> list[str]:
    if not events:
        return list(graph_state[field])  # type: ignore[index]
    for event in events:
        if field == "progress_events":
            LOGGER.info(event)
        elif field == "fallback_events":
            LOGGER.info("Fallback: %s", event)
    return [*graph_state[field], *events]  # type: ignore[index]


class LangGraphAgentRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._checkpoint_context = None

    def run(self) -> RunReport:
        initial_state = build_initial_graph_state(self.settings)

        with httpx.Client() as client:
            graph = self._build_graph(client)
            final_state = graph.invoke(
                initial_state,
                config=self._invoke_config(),
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
                fallback_events = graph_state["fallback_events"]
                if planner.last_fallback_reason:
                    fallback_events = _append_event(
                        graph_state,
                        "fallback_events",
                        "llm_plan_failed -> rule_based_plan: "
                        f"{planner.last_fallback_reason}",
                    )
                return {
                    **_agent_state_update(state),
                    "plans": [],
                    "current_plan": None,
                    "pending_urls": [],
                    "pending_url_sources": {},
                    "current_url": None,
                    "current_url_source": None,
                    "current_html": None,
                    "current_raw_job": None,
                    "classification_result": None,
                    "current_tech_tags": [],
                    "current_requirements": "",
                    "current_job": None,
                    "metrics": None,
                    "progress_events": _append_event(
                        graph_state,
                        "progress_events",
                        f"plan_queries: no queries produced at iteration {state.iteration}",
                    ),
                    "fallback_events": fallback_events,
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
                "progress_events": _append_event(
                    graph_state,
                    "progress_events",
                    f"plan_queries: planned {len(plans)} queries at iteration {state.iteration}",
                ),
                "fallback_events": (
                    _append_event(
                        graph_state,
                        "fallback_events",
                        "llm_plan_failed -> rule_based_plan: "
                        f"{planner.last_fallback_reason}",
                    )
                    if planner.last_fallback_reason
                    else graph_state["fallback_events"]
                ),
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
                "progress_events": _append_event(
                    graph_state,
                    "progress_events",
                    "search_sources: discovered "
                    f"{len(pending_urls)} pending URLs from {len(graph_state['plans'])} queries",
                ),
                "fallback_events": _append_events(
                    graph_state,
                    "fallback_events",
                    metrics.fallback_events,
                ),
                "route_decision": NEXT_CANDIDATE_NODE,
            }

        def next_candidate(graph_state: GraphState) -> dict[str, object]:
            state = to_agent_state(graph_state)
            metrics = graph_state["metrics"] or IterationMetrics(
                iteration=state.iteration
            )
            should_reflect = state.reached_target() or not graph_state["pending_urls"]
            if should_reflect:
                metrics = executor.finalize_iteration(state, metrics)
            return {
                **_agent_state_update(state),
                "pending_urls": [] if should_reflect else graph_state["pending_urls"],
                "pending_url_sources": (
                    {} if should_reflect else graph_state["pending_url_sources"]
                ),
                "current_url": None,
                "current_url_source": None,
                "current_html": None,
                "current_raw_job": None,
                "classification_result": None,
                "current_tech_tags": [],
                "current_requirements": "",
                "current_job": None,
                "metrics": metrics,
                "progress_events": _append_event(
                    graph_state,
                    "progress_events",
                    (
                        "next_candidate: reflecting after candidate batch "
                        f"(accepted_total={state.accepted_count})"
                        if should_reflect
                        else f"next_candidate: {len(graph_state['pending_urls'])} URLs pending"
                    ),
                ),
                "route_decision": REFLECT_NODE if should_reflect else FETCH_NODE,
            }

        def fetch_or_load_candidate(graph_state: GraphState) -> dict[str, object]:
            state = to_agent_state(graph_state)
            metrics = graph_state["metrics"] or IterationMetrics(
                iteration=state.iteration
            )
            pending_urls = list(graph_state["pending_urls"])
            pending_url_sources = dict(graph_state["pending_url_sources"])
            if not pending_urls:
                return {"route_decision": NEXT_CANDIDATE_NODE}

            current_url = pending_urls.pop(0)
            current_source = pending_url_sources.get(current_url, "")
            fallback_start = len(metrics.fallback_events)
            raw_job, html, error = executor.fetch_or_load_candidate(
                state,
                current_url,
                current_source,
                metrics,
            )
            if raw_job is not None:
                route_decision = EVALUATE_NODE
            elif html is not None:
                route_decision = PARSE_NODE
            else:
                route_decision = NEXT_CANDIDATE_NODE

            return {
                **_agent_state_update(state),
                "pending_urls": pending_urls,
                "current_url": current_url,
                "current_url_source": current_source,
                "current_html": html,
                "current_raw_job": raw_job,
                "classification_result": None,
                "current_tech_tags": [],
                "current_requirements": "",
                "current_job": None,
                "last_error": error,
                "metrics": metrics,
                "progress_events": _append_event(
                    graph_state,
                    "progress_events",
                    (
                        f"fetch_or_load_candidate: loaded cached raw job {current_url}"
                        if raw_job is not None
                        else (
                            f"fetch_or_load_candidate: fetched html {current_url}"
                            if html is not None
                            else f"fetch_or_load_candidate: skipped {current_url}"
                        )
                    ),
                ),
                "fallback_events": _append_events(
                    graph_state,
                    "fallback_events",
                    metrics.fallback_events[fallback_start:],
                ),
                "route_decision": route_decision,
            }

        def parse_job(graph_state: GraphState) -> dict[str, object]:
            state = to_agent_state(graph_state)
            metrics = graph_state["metrics"] or IterationMetrics(
                iteration=state.iteration
            )
            fallback_start = len(metrics.fallback_events)
            raw_job, error = executor.parse_job(
                state,
                graph_state["current_url"] or "",
                graph_state["current_html"],
                graph_state["current_url_source"] or "",
                metrics,
            )
            return {
                **_agent_state_update(state),
                "current_html": None,
                "current_raw_job": raw_job,
                "last_error": error,
                "metrics": metrics,
                "progress_events": _append_event(
                    graph_state,
                    "progress_events",
                    (
                        f"parse_job: parsed {graph_state['current_url']}"
                        if raw_job is not None
                        else f"parse_job: skipped {graph_state['current_url']}"
                    ),
                ),
                "fallback_events": _append_events(
                    graph_state,
                    "fallback_events",
                    metrics.fallback_events[fallback_start:],
                ),
                "route_decision": (
                    EVALUATE_NODE if raw_job is not None else NEXT_CANDIDATE_NODE
                ),
            }

        def evaluate_job(graph_state: GraphState) -> dict[str, object]:
            state = to_agent_state(graph_state)
            metrics = graph_state["metrics"] or IterationMetrics(
                iteration=state.iteration
            )
            raw_job = graph_state["current_raw_job"]
            if raw_job is None:
                return {"route_decision": NEXT_CANDIDATE_NODE}

            fallback_start = len(metrics.fallback_events)
            result = executor.evaluate_job(state, raw_job, metrics)
            return {
                **_agent_state_update(state),
                "classification_result": result,
                "metrics": metrics,
                "progress_events": _append_event(
                    graph_state,
                    "progress_events",
                    (
                        f"evaluate_job: accepted {raw_job.job_url} score={result.score}"
                        if result.accepted
                        else f"evaluate_job: rejected {raw_job.job_url} reason={result.reason}"
                    ),
                ),
                "fallback_events": _append_events(
                    graph_state,
                    "fallback_events",
                    metrics.fallback_events[fallback_start:],
                ),
                "route_decision": (
                    EXTRACT_NODE if result.accepted else NEXT_CANDIDATE_NODE
                ),
            }

        def extract_job_details(graph_state: GraphState) -> dict[str, object]:
            raw_job = graph_state["current_raw_job"]
            if raw_job is None:
                return {"route_decision": NEXT_CANDIDATE_NODE}

            metrics = graph_state["metrics"] or IterationMetrics(
                iteration=graph_state["iteration"]
            )
            fallback_start = len(metrics.fallback_events)
            tech_tags, requirements = executor.extract_job_details(raw_job, metrics)
            return {
                "current_tech_tags": tech_tags,
                "current_requirements": requirements,
                "metrics": metrics,
                "progress_events": _append_event(
                    graph_state,
                    "progress_events",
                    f"extract_job_details: extracted {len(tech_tags)} tags for {raw_job.job_url}",
                ),
                "fallback_events": _append_events(
                    graph_state,
                    "fallback_events",
                    metrics.fallback_events[fallback_start:],
                ),
                "route_decision": DEDUPE_NODE,
            }

        def deduplicate_and_merge(graph_state: GraphState) -> dict[str, object]:
            state = to_agent_state(graph_state)
            metrics = graph_state["metrics"] or IterationMetrics(
                iteration=state.iteration
            )
            raw_job = graph_state["current_raw_job"]
            result = graph_state["classification_result"]
            if raw_job is None or result is None:
                return {"route_decision": NEXT_CANDIDATE_NODE}

            job = executor.deduplicate_and_merge(
                state,
                raw_job,
                result,
                graph_state["current_tech_tags"],
                graph_state["current_requirements"],
                metrics,
            )
            return {
                **_agent_state_update(state),
                "current_job": job,
                "metrics": metrics,
                "progress_events": _append_event(
                    graph_state,
                    "progress_events",
                    f"deduplicate_and_merge: accepted_total={state.accepted_count}",
                ),
                "route_decision": NEXT_CANDIDATE_NODE,
            }

        def reflect_strategy(graph_state: GraphState) -> dict[str, object]:
            state = to_agent_state(graph_state)
            metrics = graph_state["metrics"]
            if metrics is not None:
                reflector.update(state, metrics)
            return {
                **_agent_state_update(state),
                "progress_events": _append_event(
                    graph_state,
                    "progress_events",
                    (
                        "reflect_strategy: stopping"
                        if state.should_stop()
                        else "reflect_strategy: continuing"
                    ),
                ),
                "route_decision": EXPORT_NODE if state.should_stop() else PLAN_NODE,
            }

        def export_result(graph_state: GraphState) -> dict[str, object]:
            report = export_run_report(
                to_agent_state(graph_state),
                export_tool,
                progress_events=graph_state["progress_events"],
                fallback_events=graph_state["fallback_events"],
                checkpoint_backend=graph_state["checkpoint_backend"],
                checkpoint_thread_id=graph_state["checkpoint_thread_id"],
            )
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

        def route_after_next_candidate(graph_state: GraphState) -> str:
            return graph_state["route_decision"]

        def route_after_fetch(graph_state: GraphState) -> str:
            return graph_state["route_decision"]

        def route_after_parse(graph_state: GraphState) -> str:
            return graph_state["route_decision"]

        def route_after_evaluation(graph_state: GraphState) -> str:
            return graph_state["route_decision"]

        def route_after_extraction(graph_state: GraphState) -> str:
            return graph_state["route_decision"]

        def route_after_deduplication(graph_state: GraphState) -> str:
            return graph_state["route_decision"]

        def route_after_reflection(
            graph_state: GraphState,
        ) -> Literal["plan_queries", "export_result"]:
            if to_agent_state(graph_state).should_stop():
                return EXPORT_NODE
            return PLAN_NODE

        graph = StateGraph(GraphState)
        graph.add_node(PLAN_NODE, plan_queries)
        graph.add_node(SEARCH_NODE, search_sources)
        graph.add_node(NEXT_CANDIDATE_NODE, next_candidate)
        graph.add_node(FETCH_NODE, fetch_or_load_candidate)
        graph.add_node(PARSE_NODE, parse_job)
        graph.add_node(EVALUATE_NODE, evaluate_job)
        graph.add_node(EXTRACT_NODE, extract_job_details)
        graph.add_node(DEDUPE_NODE, deduplicate_and_merge)
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
        graph.add_edge(SEARCH_NODE, NEXT_CANDIDATE_NODE)
        graph.add_conditional_edges(
            NEXT_CANDIDATE_NODE,
            route_after_next_candidate,
            {FETCH_NODE: FETCH_NODE, REFLECT_NODE: REFLECT_NODE},
        )
        graph.add_conditional_edges(
            FETCH_NODE,
            route_after_fetch,
            {
                PARSE_NODE: PARSE_NODE,
                EVALUATE_NODE: EVALUATE_NODE,
                NEXT_CANDIDATE_NODE: NEXT_CANDIDATE_NODE,
            },
        )
        graph.add_conditional_edges(
            PARSE_NODE,
            route_after_parse,
            {
                EVALUATE_NODE: EVALUATE_NODE,
                NEXT_CANDIDATE_NODE: NEXT_CANDIDATE_NODE,
            },
        )
        graph.add_conditional_edges(
            EVALUATE_NODE,
            route_after_evaluation,
            {
                EXTRACT_NODE: EXTRACT_NODE,
                NEXT_CANDIDATE_NODE: NEXT_CANDIDATE_NODE,
            },
        )
        graph.add_conditional_edges(
            EXTRACT_NODE,
            route_after_extraction,
            {DEDUPE_NODE: DEDUPE_NODE, NEXT_CANDIDATE_NODE: NEXT_CANDIDATE_NODE},
        )
        graph.add_conditional_edges(
            DEDUPE_NODE,
            route_after_deduplication,
            {NEXT_CANDIDATE_NODE: NEXT_CANDIDATE_NODE},
        )
        graph.add_conditional_edges(
            REFLECT_NODE,
            route_after_reflection,
            {PLAN_NODE: PLAN_NODE, EXPORT_NODE: EXPORT_NODE},
        )
        graph.add_edge(EXPORT_NODE, END)
        checkpointer = self._build_checkpointer()
        if checkpointer is None:
            return graph.compile()
        return graph.compile(checkpointer=checkpointer)

    def _invoke_config(self) -> dict[str, object]:
        return {
            "recursion_limit": self._recursion_limit(),
            "configurable": {"thread_id": self.settings.checkpoint_thread_id},
        }

    def _build_checkpointer(self):  # type: ignore[no-untyped-def]
        backend = self.settings.checkpoint_backend
        if backend in {"", "off", "none"}:
            return None
        if backend == "memory":
            from langgraph.checkpoint.memory import MemorySaver

            return MemorySaver()
        if backend == "sqlite":
            try:
                from langgraph.checkpoint.sqlite import SqliteSaver
            except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
                raise RuntimeError(
                    "SQLite checkpointing requires `langgraph-checkpoint-sqlite`. "
                    "Install the checkpoint extra or set AGENT_CHECKPOINT_BACKEND=memory."
                ) from exc

            self.settings.checkpoint_db_path.parent.mkdir(parents=True, exist_ok=True)
            saver = SqliteSaver.from_conn_string(str(self.settings.checkpoint_db_path))
            if hasattr(saver, "__enter__"):
                self._checkpoint_context = saver
                return saver.__enter__()
            return saver
        raise ValueError(
            "Unsupported AGENT_CHECKPOINT_BACKEND. Use 'memory', 'sqlite', or 'off'."
        )

    def _recursion_limit(self) -> int:
        per_iteration_steps = (
            4
            + self.settings.batch_queries
            * self.settings.search_results_per_query
            * 8
        )
        return max(100, self.settings.max_iterations * per_iteration_steps + 20)
