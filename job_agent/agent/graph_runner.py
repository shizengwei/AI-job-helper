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
from job_agent.models import IterationMetrics, RunReport, SearchPlanItem
from job_agent.parsers.registry import ParserRegistry
from job_agent.tools.classify import JobClassifier
from job_agent.tools.dedupe import DeduplicationTool
from job_agent.tools.export import ExportTool
from job_agent.tools.extract import SkillExtractionTool
from job_agent.tools.fetch import FetchTool
from job_agent.tools.search import SearchTool

LOGGER = logging.getLogger(__name__)

PLAN_NODE = "plan_queries"
EXECUTE_NODE = "execute_iteration"
REFLECT_NODE = "reflect"
EXPORT_NODE = "export_result"


class GraphState(TypedDict):
    state: AgentState
    plans: list[SearchPlanItem]
    metrics: IterationMetrics | None
    report: RunReport | None


class LangGraphAgentRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run(self) -> RunReport:
        state = AgentState(
            target_count=self.settings.target_count,
            max_iterations=self.settings.max_iterations,
            source_domains=self.settings.source_domains,
        )
        initial_state: GraphState = {
            "state": state,
            "plans": [],
            "metrics": None,
            "report": None,
        }

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
            state = graph_state["state"]
            state.iteration += 1
            plans = planner.plan(state)
            if not plans:
                LOGGER.info("Planner produced no more queries. Stopping.")
                return {"state": state, "plans": [], "metrics": None}

            LOGGER.info(
                "Starting iteration %s with %s planned queries.",
                state.iteration,
                len(plans),
            )
            return {"state": state, "plans": plans, "metrics": None}

        def execute_iteration(graph_state: GraphState) -> dict[str, object]:
            state = graph_state["state"]
            metrics = executor.execute_iteration(state, graph_state["plans"])
            return {"state": state, "metrics": metrics}

        def reflect(graph_state: GraphState) -> dict[str, object]:
            state = graph_state["state"]
            metrics = graph_state["metrics"]
            if metrics is not None:
                reflector.update(state, metrics)
            return {"state": state}

        def export_result(graph_state: GraphState) -> dict[str, object]:
            report = export_run_report(graph_state["state"], export_tool)
            return {"report": report}

        def route_entry(
            graph_state: GraphState,
        ) -> Literal["plan_queries", "export_result"]:
            if graph_state["state"].should_stop():
                return EXPORT_NODE
            return PLAN_NODE

        def route_after_planning(
            graph_state: GraphState,
        ) -> Literal["execute_iteration", "export_result"]:
            if graph_state["plans"]:
                return EXECUTE_NODE
            return EXPORT_NODE

        def route_after_reflection(
            graph_state: GraphState,
        ) -> Literal["plan_queries", "export_result"]:
            if graph_state["state"].should_stop():
                return EXPORT_NODE
            return PLAN_NODE

        graph = StateGraph(GraphState)
        graph.add_node(PLAN_NODE, plan_queries)
        graph.add_node(EXECUTE_NODE, execute_iteration)
        graph.add_node(REFLECT_NODE, reflect)
        graph.add_node(EXPORT_NODE, export_result)

        graph.add_conditional_edges(
            START,
            route_entry,
            {PLAN_NODE: PLAN_NODE, EXPORT_NODE: EXPORT_NODE},
        )
        graph.add_conditional_edges(
            PLAN_NODE,
            route_after_planning,
            {EXECUTE_NODE: EXECUTE_NODE, EXPORT_NODE: EXPORT_NODE},
        )
        graph.add_edge(EXECUTE_NODE, REFLECT_NODE)
        graph.add_conditional_edges(
            REFLECT_NODE,
            route_after_reflection,
            {PLAN_NODE: PLAN_NODE, EXPORT_NODE: EXPORT_NODE},
        )
        graph.add_edge(EXPORT_NODE, END)
        return graph.compile()

    def _recursion_limit(self) -> int:
        return max(25, self.settings.max_iterations * 5 + 10)
