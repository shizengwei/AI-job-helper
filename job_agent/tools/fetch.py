"""Web page fetching tool."""

from __future__ import annotations

import logging
import time

import httpx

from job_agent.config import Settings
from job_agent.constants import DEFAULT_USER_AGENT

LOGGER = logging.getLogger(__name__)


class FetchTool:
    def __init__(self, client: httpx.Client, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    def fetch(self, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(self.settings.retry_attempts + 1):
            try:
                response = self.client.get(
                    url,
                    headers={"User-Agent": DEFAULT_USER_AGENT},
                    timeout=self.settings.request_timeout_seconds,
                    follow_redirects=True,
                )
                response.raise_for_status()
                time.sleep(self.settings.inter_request_delay_seconds)
                return response.text
            except Exception as exc:
                last_error = exc
                LOGGER.debug("Fetch failed for %s on attempt %s: %s", url, attempt + 1, exc)
                time.sleep(self.settings.inter_request_delay_seconds * (attempt + 1))
        raise RuntimeError(f"Failed to fetch {url}: {last_error}") from last_error

