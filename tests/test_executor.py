from job_agent.agent.executor import AgentExecutor
from job_agent.agent.state import AgentState
from job_agent.models import (
    ClassificationResult,
    IterationMetrics,
    RawJobPosting,
    SearchPlanItem,
)
from job_agent.tools.dedupe import DeduplicationTool


class StubSearchTool:
    def __init__(self, urls: list[str], raw_jobs: dict[str, RawJobPosting]) -> None:
        self.urls = urls
        self.raw_jobs = raw_jobs
        self.visited_snapshots: list[set[str]] = []

    def search(self, plan, visited_urls):  # type: ignore[no-untyped-def]
        self.visited_snapshots.append(set(visited_urls))
        return [url for url in self.urls if url not in visited_urls]

    def get_cached_raw_job(self, job_url: str) -> RawJobPosting | None:
        return self.raw_jobs.get(job_url)


class UnusedFetchTool:
    def fetch(self, url: str) -> str:
        raise AssertionError("cached raw jobs should not require fetching")


class UnusedParserRegistry:
    def parse(self, html: str, url: str) -> RawJobPosting:
        raise AssertionError("cached raw jobs should not require parsing")


class AcceptingClassifier:
    def classify(self, job: RawJobPosting) -> ClassificationResult:
        return ClassificationResult(
            accepted=True,
            score=8,
            reason="campus AI role",
        )


class StubExtractor:
    def extract(self, job: RawJobPosting) -> tuple[list[str], str]:
        return ["Machine Learning"], "Internship role."


def _raw_job(url: str) -> RawJobPosting:
    return RawJobPosting(
        title="Machine Learning Engineer Intern",
        company="Example AI",
        location="Remote",
        salary="",
        description="Internship role working on machine learning systems.",
        source="jobs.lever.co",
        job_url=url,
    )


def _executor(urls: list[str], raw_jobs: dict[str, RawJobPosting]) -> AgentExecutor:
    return AgentExecutor(
        search_tool=StubSearchTool(urls, raw_jobs),
        fetch_tool=UnusedFetchTool(),
        parser_registry=UnusedParserRegistry(),
        classifier=AcceptingClassifier(),
        extractor=StubExtractor(),
        deduper=DeduplicationTool(),
    )


def test_search_sources_collects_pending_urls_and_metrics():
    url = "https://jobs.lever.co/example/123"
    executor = _executor([url], {url: _raw_job(url)})
    state = AgentState(
        target_count=10,
        max_iterations=2,
        source_domains=("jobs.lever.co",),
        iteration=1,
    )
    plan = SearchPlanItem(
        source_domain="jobs.lever.co",
        role_keyword="Machine Learning Engineer",
        campus_keyword="intern",
        query="site:jobs.lever.co Machine Learning Engineer intern",
    )

    pending_urls, pending_url_sources, metrics = executor.search_sources(
        state,
        [plan],
    )

    assert pending_urls == [url]
    assert pending_url_sources == {url: "jobs.lever.co"}
    assert metrics.queries == [plan.query]
    assert metrics.discovered_urls == 1
    assert state.query_history == [plan.query]
    assert plan.key in state.tried_queries
    assert state.source_stats["jobs.lever.co"].search_hits == 1
    assert state.visited_urls == set()


def test_search_sources_dedupes_pending_urls_across_plans():
    url = "https://jobs.lever.co/example/123"
    executor = _executor([url], {url: _raw_job(url)})
    state = AgentState(
        target_count=10,
        max_iterations=2,
        source_domains=("jobs.lever.co",),
        iteration=1,
    )
    plans = [
        SearchPlanItem(
            source_domain="jobs.lever.co",
            role_keyword="Machine Learning Engineer",
            campus_keyword="intern",
            query="site:jobs.lever.co Machine Learning Engineer intern",
        ),
        SearchPlanItem(
            source_domain="jobs.lever.co",
            role_keyword="AI Engineer",
            campus_keyword="new grad",
            query="site:jobs.lever.co AI Engineer new grad",
        ),
    ]

    pending_urls, pending_url_sources, metrics = executor.search_sources(state, plans)

    assert pending_urls == [url]
    assert pending_url_sources == {url: "jobs.lever.co"}
    assert metrics.discovered_urls == 1
    assert executor.search_tool.visited_snapshots[0] == set()
    assert executor.search_tool.visited_snapshots[1] == {url}


def test_process_candidates_accepts_cached_raw_job():
    url = "https://jobs.lever.co/example/123"
    executor = _executor([url], {url: _raw_job(url)})
    state = AgentState(
        target_count=10,
        max_iterations=2,
        source_domains=("jobs.lever.co",),
        iteration=1,
    )
    metrics = IterationMetrics(iteration=1, discovered_urls=1)

    metrics = executor.process_candidates(
        state,
        [url],
        {url: "jobs.lever.co"},
        metrics,
    )

    assert metrics.parsed_jobs == 1
    assert metrics.accepted_jobs == 1
    assert state.accepted_count == 1
    assert state.accepted_jobs[0].job_url == url
    assert state.source_stats["jobs.lever.co"].fetched == 1
    assert state.source_stats["jobs.lever.co"].accepted == 1
    assert state.visited_urls == {url}
