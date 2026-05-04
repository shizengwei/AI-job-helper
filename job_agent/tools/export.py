"""Export tool."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from job_agent.constants import CSV_FIELDS
from job_agent.models import JobPosting, RunReport


class ExportTool:
    def __init__(self, outputs_dir: Path) -> None:
        self.outputs_dir = outputs_dir
        self.outputs_dir.mkdir(parents=True, exist_ok=True)

    def export_jobs(self, jobs: list[JobPosting]) -> tuple[Path, Path]:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        csv_path = self.outputs_dir / f"jobs_{timestamp}.csv"
        json_path = self.outputs_dir / f"jobs_{timestamp}.json"

        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for job in jobs:
                writer.writerow(job.to_export_row())

        with json_path.open("w", encoding="utf-8") as handle:
            json.dump([job.to_json_dict() for job in jobs], handle, ensure_ascii=False, indent=2)

        return csv_path, json_path

    def export_report(self, report: RunReport) -> Path:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        report_path = self.outputs_dir / f"report_{timestamp}.json"
        with report_path.open("w", encoding="utf-8") as handle:
            json.dump(report.to_json_dict(), handle, ensure_ascii=False, indent=2)
        return report_path

