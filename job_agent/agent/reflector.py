"""Reflection policy."""

from __future__ import annotations

from job_agent.constants import ROLE_KEYWORD_TIERS
from job_agent.models import IterationMetrics


class Reflector:
    def update(self, state, metrics: IterationMetrics) -> None:  # type: ignore[no-untyped-def]
        if metrics.accepted_jobs == 0:
            state.iterations_without_progress += 1
        else:
            state.iterations_without_progress = 0

        if (
            metrics.accepted_jobs < 2
            and state.search_phase < len(ROLE_KEYWORD_TIERS) - 1
            and metrics.discovered_urls < 8
        ):
            state.search_phase += 1

