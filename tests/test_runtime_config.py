from pathlib import Path

from job_agent.agent.graph_runner import LangGraphAgentRunner
from job_agent.agent.runner import AgentRunner
from job_agent.cli import _build_runner
from job_agent.config import Settings, load_settings


def test_load_settings_reads_agent_runtime(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME", "classic")

    settings = load_settings()

    assert settings.agent_runtime == "classic"


def test_build_runner_uses_classic_runtime_without_langgraph():
    settings = Settings(agent_runtime="classic")

    runner = _build_runner(settings)

    assert isinstance(runner, AgentRunner)


def test_langgraph_runner_exports_when_initial_state_should_stop(tmp_path):
    settings = Settings(target_count=0, outputs_dir=tmp_path)

    report = LangGraphAgentRunner(settings).run()

    assert report.collected_count == 0
    assert report.iterations == 0
    assert Path(report.output_csv).exists()
