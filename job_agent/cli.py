"""CLI entrypoint."""

from __future__ import annotations

import logging

from job_agent.agent.runner import AgentRunner
from job_agent.config import load_settings
from job_agent.logging_utils import configure_logging


def main() -> None:
    configure_logging()
    settings = load_settings()
    report = AgentRunner(settings).run()
    logging.getLogger(__name__).info(
        "Completed collection with %s jobs. CSV: %s",
        report.collected_count,
        report.output_csv,
    )


if __name__ == "__main__":
    main()

