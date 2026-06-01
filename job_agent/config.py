"""Configuration loading."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from job_agent.constants import SOURCE_DOMAINS


@dataclass(slots=True)
class Settings:
    target_count: int = 50
    max_iterations: int = 10
    batch_queries: int = 4
    search_results_per_query: int = 10
    max_pages_per_query: int = 1
    request_timeout_seconds: float = 20.0
    retry_attempts: int = 2
    inter_request_delay_seconds: float = 0.2
    llm_model: str = "gpt-4.1-mini"
    openai_api_key: str = ""
    outputs_dir: Path = Path("outputs")
    source_domains: tuple[str, ...] = tuple(SOURCE_DOMAINS)
    agent_runtime: str = "langgraph"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key)


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        target_count=int(os.getenv("TARGET_COUNT", "50")),
        max_iterations=int(os.getenv("MAX_ITERATIONS", "10")),
        batch_queries=int(os.getenv("BATCH_QUERIES", "4")),
        search_results_per_query=int(os.getenv("SEARCH_RESULTS_PER_QUERY", "10")),
        max_pages_per_query=int(os.getenv("MAX_PAGES_PER_QUERY", "1")),
        request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "20")),
        retry_attempts=int(os.getenv("RETRY_ATTEMPTS", "2")),
        inter_request_delay_seconds=float(
            os.getenv("INTER_REQUEST_DELAY_SECONDS", "0.2")
        ),
        llm_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        outputs_dir=Path(os.getenv("OUTPUTS_DIR", "outputs")),
        agent_runtime=os.getenv("AGENT_RUNTIME", "langgraph").strip().lower(),
    )
