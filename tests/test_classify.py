from job_agent.config import Settings
from job_agent.models import RawJobPosting
from job_agent.tools.classify import JobClassifier


def test_heuristic_classifier_accepts_ai_intern_role():
    classifier = JobClassifier(Settings(openai_api_key=""))
    job = RawJobPosting(
        title="Machine Learning Engineer Intern",
        company="Example AI",
        location="San Francisco, CA",
        salary="",
        description="Internship role working on machine learning, LLM, and PyTorch systems.",
        source="jobs.lever.co",
        job_url="https://jobs.lever.co/example/123",
    )

    result = classifier.classify(job)

    assert result.accepted is True
    assert result.score >= 4


def test_heuristic_classifier_rejects_backend_role():
    classifier = JobClassifier(Settings(openai_api_key=""))
    job = RawJobPosting(
        title="Backend Engineer Intern",
        company="Example",
        location="Remote",
        salary="",
        description="Internship role focused on backend microservices, APIs, and Java.",
        source="jobs.lever.co",
        job_url="https://jobs.lever.co/example/456",
    )

    result = classifier.classify(job)

    assert result.accepted is False


def test_heuristic_classifier_rejects_senior_manager_role():
    classifier = JobClassifier(Settings(openai_api_key=""))
    job = RawJobPosting(
        title="Engineering Manager, Machine Learning",
        company="Example AI",
        location="Remote",
        salary="",
        description="Lead the machine learning organization and hire senior engineers for production AI systems.",
        source="job-boards.greenhouse.io",
        job_url="https://job-boards.greenhouse.io/example/789",
    )

    result = classifier.classify(job)

    assert result.accepted is False
