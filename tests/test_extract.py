from job_agent.config import Settings
from job_agent.models import RawJobPosting
from job_agent.tools.extract import SkillExtractionTool


def test_extractor_records_heuristic_fallback_without_llm():
    extractor = SkillExtractionTool(Settings(openai_api_key=""))
    job = RawJobPosting(
        title="Machine Learning Engineer Intern",
        company="Example AI",
        location="Remote",
        salary="",
        description="Requirements include Python, machine learning, and PyTorch.",
        source="jobs.lever.co",
        job_url="https://jobs.lever.co/example/123",
    )

    tags, requirements = extractor.extract(job)

    assert tags
    assert "Python" in requirements or "machine learning" in requirements
    assert extractor.last_strategy == "heuristic"
    assert extractor.last_fallback_reason == "llm_disabled"
