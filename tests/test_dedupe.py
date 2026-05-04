from job_agent.models import JobPosting
from job_agent.tools.dedupe import DeduplicationTool


def test_dedupe_prefers_more_complete_job():
    deduper = DeduplicationTool()
    first = JobPosting(
        title="AI Engineer Intern",
        company="Example",
        location="New York, NY",
        salary="",
        tech_tags=["ML"],
        requirements="",
        source="jobs.lever.co",
        job_url="https://jobs.lever.co/example/1",
        match_score=5,
        match_reason="good",
        description="short",
    )
    second = JobPosting(
        title="AI Engineer Intern",
        company="Example",
        location="New York, NY",
        salary="$50 / hour",
        tech_tags=["ML", "LLM"],
        requirements="Python and machine learning experience",
        source="jobs.lever.co",
        job_url="https://jobs.lever.co/example/2",
        match_score=6,
        match_reason="better",
        description="longer description" * 50,
    )

    assert deduper.add(first) == "added"
    assert deduper.add(second) == "replaced"

    jobs = deduper.jobs()
    assert len(jobs) == 1
    assert jobs[0].job_url == second.job_url

