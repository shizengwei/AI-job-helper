"""Agent execution loop for a batch of queries."""

from __future__ import annotations

import logging

from job_agent.agent.state import AgentState
from job_agent.models import (
    ClassificationResult,
    IterationMetrics,
    JobPosting,
    RawJobPosting,
    RejectionRecord,
    SearchPlanItem,
)

LOGGER = logging.getLogger(__name__)


class AgentExecutor:
    def __init__(
        self,
        *,
        search_tool,
        fetch_tool,
        parser_registry,
        classifier,
        extractor,
        deduper,
    ) -> None:
        self.search_tool = search_tool
        self.fetch_tool = fetch_tool
        self.parser_registry = parser_registry
        self.classifier = classifier
        self.extractor = extractor
        self.deduper = deduper

    def execute_iteration(
        self,
        state: AgentState,
        plans: list[SearchPlanItem],
    ) -> IterationMetrics:
        pending_urls, pending_url_sources, metrics = self.search_sources(state, plans)
        return self.process_candidates(
            state,
            pending_urls,
            pending_url_sources,
            metrics,
        )

    def search_sources(
        self,
        state: AgentState,
        plans: list[SearchPlanItem],
    ) -> tuple[list[str], dict[str, str], IterationMetrics]:
        metrics = IterationMetrics(iteration=state.iteration)
        pending_urls: list[str] = []
        pending_url_sources: dict[str, str] = {}
        seen_urls = set(state.visited_urls)

        for plan in plans:
            state.tried_queries.add(plan.key)
            state.query_history.append(plan.query)
            metrics.queries.append(plan.query)

            try:
                urls = self.search_tool.search(plan, seen_urls)
                metrics.fallback_events.extend(
                    getattr(self.search_tool, "last_fallback_events", [])
                )
                state.source_stats[plan.source_domain].search_hits += len(urls)
                metrics.discovered_urls += len(urls)
                for url in urls:
                    if url in seen_urls:
                        continue
                    pending_urls.append(url)
                    pending_url_sources[url] = plan.source_domain
                    seen_urls.add(url)
            except Exception as exc:
                LOGGER.warning("Search failed for query %s: %s", plan.query, exc)
                metrics.fallback_events.append(
                    f"search_failed -> skip_query: {plan.query} ({exc})"
                )
                state.source_stats[plan.source_domain].errors += 1
                continue

        return pending_urls, pending_url_sources, metrics

    def process_candidates(
        self,
        state: AgentState,
        pending_urls: list[str],
        pending_url_sources: dict[str, str],
        metrics: IterationMetrics,
    ) -> IterationMetrics:
        for url in pending_urls:
            if state.reached_target():
                return self.finalize_iteration(state, metrics)
            source_domain = pending_url_sources.get(url, "")

            raw_job, html, error = self.fetch_or_load_candidate(
                state,
                url,
                source_domain,
                metrics,
            )
            if error:
                continue

            if raw_job is None:
                raw_job, error = self.parse_job(
                    state,
                    url,
                    html,
                    source_domain,
                    metrics,
                )
            if raw_job is None or error:
                continue

            result = self.evaluate_job(state, raw_job, metrics)
            if not result.accepted:
                continue

            tech_tags, requirements = self.extract_job_details(raw_job, metrics)
            self.deduplicate_and_merge(
                state,
                raw_job,
                result,
                tech_tags,
                requirements,
                metrics,
            )

        return self.finalize_iteration(state, metrics)

    def fetch_or_load_candidate(
        self,
        state: AgentState,
        url: str,
        source_domain: str,
        metrics: IterationMetrics,
    ) -> tuple[RawJobPosting | None, str | None, str | None]:
        state.visited_urls.add(url)
        try:
            raw_job = self.search_tool.get_cached_raw_job(url)
            if raw_job is not None:
                if source_domain:
                    state.source_stats[source_domain].fetched += 1
                metrics.parsed_jobs += 1
                return raw_job, None, None
            return None, self.fetch_tool.fetch(url), None
        except Exception as exc:
            LOGGER.warning("Failed to fetch %s: %s", url, exc)
            metrics.fetch_errors += 1
            metrics.fallback_events.append(f"fetch_failed -> retry_or_skip: {url} ({exc})")
            if source_domain:
                state.source_stats[source_domain].errors += 1
            return None, None, str(exc)

    def parse_job(
        self,
        state: AgentState,
        url: str,
        html: str | None,
        source_domain: str,
        metrics: IterationMetrics,
    ) -> tuple[RawJobPosting | None, str | None]:
        if html is None:
            metrics.fallback_events.append(f"parse_failed -> skip_candidate: {url} (missing html)")
            return None, "missing html"
        try:
            raw_job = self.parser_registry.parse(html, url)
            if source_domain:
                state.source_stats[source_domain].fetched += 1
            metrics.parsed_jobs += 1
            return raw_job, None
        except Exception as exc:
            LOGGER.warning("Failed to parse %s: %s", url, exc)
            metrics.fetch_errors += 1
            metrics.fallback_events.append(f"parse_failed -> skip_candidate: {url} ({exc})")
            if source_domain:
                state.source_stats[source_domain].errors += 1
            return None, str(exc)

    def evaluate_job(
        self,
        state: AgentState,
        raw_job: RawJobPosting,
        metrics: IterationMetrics,
    ) -> ClassificationResult:
        result = self.classifier.classify(raw_job)
        fallback_reason = getattr(self.classifier, "last_fallback_reason", "")
        if fallback_reason:
            metrics.fallback_events.append(
                "llm_evaluate_failed -> heuristic_evaluate: "
                f"{raw_job.job_url} ({fallback_reason})"
            )
        if not result.accepted:
            metrics.rejected_jobs += 1
            state.source_stats[raw_job.source].rejected += 1
            state.rejected_jobs.append(
                RejectionRecord(
                    job_url=raw_job.job_url,
                    title=raw_job.title,
                    company=raw_job.company,
                    reason=result.reason,
                )
            )
        return result

    def extract_job_details(
        self,
        raw_job: RawJobPosting,
        metrics: IterationMetrics | None = None,
    ) -> tuple[list[str], str]:
        details = self.extractor.extract(raw_job)
        fallback_reason = getattr(self.extractor, "last_fallback_reason", "")
        if metrics is not None and fallback_reason:
            metrics.fallback_events.append(
                "llm_extract_failed -> heuristic_extract: "
                f"{raw_job.job_url} ({fallback_reason})"
            )
        return details

    def deduplicate_and_merge(
        self,
        state: AgentState,
        raw_job: RawJobPosting,
        result: ClassificationResult,
        tech_tags: list[str],
        requirements: str,
        metrics: IterationMetrics,
    ) -> JobPosting:
        job = JobPosting(
            title=raw_job.title,
            company=raw_job.company,
            location=raw_job.location,
            salary=raw_job.salary,
            tech_tags=tech_tags,
            requirements=requirements,
            source=raw_job.source,
            job_url=raw_job.job_url,
            match_score=result.score,
            match_reason=result.reason,
            description=raw_job.description,
        )
        dedupe_status = self.deduper.add(job)
        if dedupe_status in {"added", "replaced"}:
            state.accepted_jobs = self.deduper.jobs()
            metrics.accepted_jobs += 1
            state.source_stats[raw_job.source].accepted += 1
        else:
            metrics.rejected_jobs += 1
        return job

    def finalize_iteration(
        self,
        state: AgentState,
        metrics: IterationMetrics,
    ) -> IterationMetrics:
        LOGGER.info(
            "Iteration %s finished. Accepted total: %s",
            state.iteration,
            state.accepted_count,
        )
        return metrics
