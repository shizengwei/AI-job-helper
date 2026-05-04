"""Agent state."""

from __future__ import annotations

from dataclasses import dataclass, field

from job_agent.models import JobPosting, RejectionRecord, SourceStats


@dataclass(slots=True)
class AgentState:
    target_count: int
    max_iterations: int
    source_domains: tuple[str, ...]
    iteration: int = 0
    search_phase: int = 0
    iterations_without_progress: int = 0
    accepted_jobs: list[JobPosting] = field(default_factory=list)
    rejected_jobs: list[RejectionRecord] = field(default_factory=list)
    visited_urls: set[str] = field(default_factory=set)
    tried_queries: set[str] = field(default_factory=set)
    query_history: list[str] = field(default_factory=list)
    source_stats: dict[str, SourceStats] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source_stats:
            self.source_stats = {
                domain: SourceStats(source_domain=domain) for domain in self.source_domains
            }

    @property
    def accepted_count(self) -> int:
        return len(self.accepted_jobs)

    def reached_target(self) -> bool:
        return self.accepted_count >= self.target_count

    def should_stop(self) -> bool:
        return (
            self.reached_target()
            or self.iteration >= self.max_iterations
            or self.iterations_without_progress >= 3
        )

