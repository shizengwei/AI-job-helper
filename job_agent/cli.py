"""CLI entrypoint."""

from __future__ import annotations

import logging

from job_agent.agent.runner import AgentRunner
from job_agent.config import load_settings
from job_agent.logging_utils import configure_logging


def _build_runner(settings):  # type: ignore[no-untyped-def]
    if settings.agent_runtime == "classic":
        return AgentRunner(settings)
    if settings.agent_runtime == "langgraph":
        from job_agent.agent.graph_runner import LangGraphAgentRunner

        return LangGraphAgentRunner(settings)
    raise ValueError(
        "Unsupported AGENT_RUNTIME. Use 'langgraph' or 'classic'."
    )


def main() -> None:
    configure_logging()
    settings = load_settings()
    report = _build_runner(settings).run()
    logging.getLogger(__name__).info(
        "Completed collection with %s jobs. CSV: %s",
        report.collected_count,
        report.output_csv,
    )


if __name__ == "__main__":
    main()
