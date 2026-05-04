"""Agent execution loop for a batch of queries."""

from __future__ import annotations

import logging

from job_agent.models import IterationMetrics, JobPosting, RejectionRecord

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

    def execute_iteration(self, state, plans) -> IterationMetrics:  # type: ignore[no-untyped-def]
        metrics = IterationMetrics(iteration=state.iteration)
        for plan in plans:
            state.tried_queries.add(plan.key)
            state.query_history.append(plan.query)
            metrics.queries.append(plan.query)

            try:
                urls = self.search_tool.search(plan, state.visited_urls)
                state.source_stats[plan.source_domain].search_hits += len(urls)
                metrics.discovered_urls += len(urls)
            except Exception as exc:
                LOGGER.warning("Search failed for query %s: %s", plan.query, exc)
                state.source_stats[plan.source_domain].errors += 1
                continue

            for url in urls:
                if state.reached_target():
                    return self._finalize(state, metrics)
                state.visited_urls.add(url)
                try:
                    raw_job = self.search_tool.get_cached_raw_job(url)
                    if raw_job is None:
                        html = self.fetch_tool.fetch(url)
                        raw_job = self.parser_registry.parse(html, url)
                    state.source_stats[plan.source_domain].fetched += 1
                    metrics.parsed_jobs += 1
                except Exception as exc:
                    LOGGER.warning("Failed to fetch/parse %s: %s", url, exc)
                    metrics.fetch_errors += 1
                    state.source_stats[plan.source_domain].errors += 1
                    continue

                result = self.classifier.classify(raw_job)
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
                    continue

                tech_tags, requirements = self.extractor.extract(raw_job)
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

        return self._finalize(state, metrics)

    def _finalize(self, state, metrics: IterationMetrics) -> IterationMetrics:  # type: ignore[no-untyped-def]
        LOGGER.info(
            "Iteration %s finished. Accepted total: %s",
            state.iteration,
            state.accepted_count,
        )
        return metrics
