from job_agent.config import Settings
from job_agent.models import SearchPlanItem
from job_agent.tools.search import SearchTool


class FallbackSearchTool(SearchTool):
    def __init__(self) -> None:
        self.settings = Settings()
        self._api_cache = {}
        self._raw_job_cache = {}
        self.last_strategy = ""
        self.last_fallback_events = []

    def _search_board_api(self, plan, visited_urls):  # type: ignore[no-untyped-def]
        return []

    def _search_duckduckgo(self, plan, visited_urls):  # type: ignore[no-untyped-def]
        return ["https://jobs.lever.co/example/123"]

    def _search_bing(self, plan, visited_urls):  # type: ignore[no-untyped-def]
        raise AssertionError("DuckDuckGo fallback should stop before Bing")


def test_search_records_api_empty_fallback_to_search_engine():
    tool = FallbackSearchTool()
    plan = SearchPlanItem(
        source_domain="jobs.lever.co",
        role_keyword="Machine Learning Engineer",
        campus_keyword="intern",
        query="site:jobs.lever.co Machine Learning Engineer intern",
    )

    urls = tool.search(plan, set())

    assert urls == ["https://jobs.lever.co/example/123"]
    assert tool.last_strategy == "duckduckgo"
    assert tool.last_fallback_events == [
        "api_search_empty -> search_engine_search: "
        "site:jobs.lever.co Machine Learning Engineer intern"
    ]
