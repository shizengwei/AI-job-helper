"""Run-report generation shared by agent runtimes."""

from __future__ import annotations

from collections import Counter

from job_agent.models import RunReport


def export_run_report(  # type: ignore[no-untyped-def]
    state,
    export_tool,
    *,
    progress_events: list[str] | None = None,
    fallback_events: list[str] | None = None,
    checkpoint_backend: str = "",
    checkpoint_thread_id: str = "",
) -> RunReport:
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
        progress_events=progress_events or [],
        fallback_events=fallback_events or [],
        checkpoint_backend=checkpoint_backend,
        checkpoint_thread_id=checkpoint_thread_id,
    )
    export_tool.export_report(report)
    return report
