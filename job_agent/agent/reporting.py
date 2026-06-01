"""Run-report generation shared by agent runtimes."""

from __future__ import annotations

from collections import Counter

from job_agent.models import RunReport


def export_run_report(state, export_tool) -> RunReport:  # type: ignore[no-untyped-def]
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
