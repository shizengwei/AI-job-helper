"""Top-level runner."""

from __future__ import annotations

import logging
from collections import Counter

import httpx

from job_agent.agent.executor import AgentExecutor
from job_agent.agent.planner import QueryPlanner
from job_agent.agent.reflector import Reflector
from job_agent.agent.state import AgentState
from job_agent.config import Settings
from job_agent.models import RunReport
from job_agent.parsers.registry import ParserRegistry
from job_agent.tools.classify import JobClassifier
from job_agent.tools.dedupe import DeduplicationTool
from job_agent.tools.export import ExportTool
from job_agent.tools.extract import SkillExtractionTool
from job_agent.tools.fetch import FetchTool
from job_agent.tools.search import SearchTool

LOGGER = logging.getLogger(__name__)


class AgentRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run(self) -> RunReport:
        state = AgentState(
            target_count=self.settings.target_count,
            max_iterations=self.settings.max_iterations,
            source_domains=self.settings.source_domains,
        )
        export_tool = ExportTool(self.settings.outputs_dir)

        with httpx.Client() as client:
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

            while not state.should_stop():
                state.iteration += 1
                plans = planner.plan(state)
                if not plans:
                    LOGGER.info("Planner produced no more queries. Stopping.")
                    break

                LOGGER.info(
                    "Starting iteration %s with %s planned queries.",
                    state.iteration,
                    len(plans),
                )
                metrics = executor.execute_iteration(state, plans)
                reflector.update(state, metrics)

                if state.reached_target():
                    break

        jobs = sorted(
            state.accepted_jobs,
            key=lambda job: (job.source, job.company.lower(), job.title.lower()),
        )
        csv_path, json_path = export_tool.export_jobs(jobs)
        rejection_breakdown = Counter(record.reason for record in state.rejected_jobs)
        report = RunReport(
            target_count=state.target_count,
            collected_count=len(jobs),
            iterations=state.iteration,
            queries_used=state.query_history,
            sources_used=sorted({job.source for job in jobs}),
            rejection_breakdown=dict(rejection_breakdown),
            output_csv=str(csv_path),
            output_json=str(json_path),
        )
        export_tool.export_report(report)
        return report

