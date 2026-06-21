from job_agent.agent.graph_runner import build_initial_graph_state, to_agent_state
from job_agent.config import Settings
from job_agent.models import JobPosting


def test_initial_graph_state_exposes_workflow_fields():
    settings = Settings(
        target_count=3,
        max_iterations=2,
        source_domains=("jobs.lever.co",),
    )

    graph_state = build_initial_graph_state(settings)

    assert graph_state["target_count"] == 3
    assert graph_state["max_iterations"] == 2
    assert graph_state["source_domains"] == ("jobs.lever.co",)
    assert graph_state["plans"] == []
    assert graph_state["current_plan"] is None
    assert graph_state["pending_urls"] == []
    assert graph_state["pending_url_sources"] == {}
    assert graph_state["current_url"] is None
    assert graph_state["current_url_source"] is None
    assert graph_state["current_html"] is None
    assert graph_state["current_raw_job"] is None
    assert graph_state["classification_result"] is None
    assert graph_state["current_tech_tags"] == []
    assert graph_state["current_requirements"] == ""
    assert graph_state["current_job"] is None
    assert graph_state["last_error"] is None
    assert graph_state["metrics"] is None
    assert graph_state["progress_events"] == []
    assert graph_state["fallback_events"] == []
    assert graph_state["checkpoint_backend"] == "memory"
    assert graph_state["checkpoint_thread_id"] == "job-agent-default"
    assert graph_state["report"] is None
    assert "jobs.lever.co" in graph_state["source_stats"]


def test_graph_state_adapter_preserves_target_stop_condition():
    settings = Settings(target_count=1)
    graph_state = build_initial_graph_state(settings)
    graph_state["accepted_jobs"] = [
        JobPosting(
            title="Machine Learning Engineer Intern",
            company="Example AI",
            location="Remote",
            salary="",
            tech_tags=["Machine Learning"],
            requirements="Internship role.",
            source="jobs.lever.co",
            job_url="https://jobs.lever.co/example/123",
            match_score=8,
            match_reason="campus AI role",
        )
    ]

    state = to_agent_state(graph_state)

    assert state.should_stop() is True


def test_graph_state_adapter_preserves_iteration_stop_condition():
    settings = Settings(target_count=10, max_iterations=2)
    graph_state = build_initial_graph_state(settings)
    graph_state["iteration"] = 2

    state = to_agent_state(graph_state)

    assert state.should_stop() is True
