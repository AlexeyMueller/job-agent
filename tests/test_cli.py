from typer.testing import CliRunner

from job_agent import __version__
from job_agent.cli import app

runner = CliRunner()


def test_version_command_prints_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_explain_prints_stored_evaluation_and_handles_unknown_ref(tmp_path):
    from job_agent.models import Job
    from job_agent.scorer import ScoreResult
    from job_agent.tracker import Tracker

    db = str(tmp_path / "jobs.db")
    tracker = Tracker(db)
    job = Job(source="dou", ref="123", title="QA Engineer", employer="Acme", location="Berlin",
              url="https://jobs.dou.ua/x/123/")
    result = ScoreResult(
        score=70, apply=True, summary="Good fit overall.", match_reasons=["Playwright"],
        gaps=["German C1"], red_flags=["Ukraine only"], work_mode="remote",
        language_requirement="German C1",
    )
    tracker.save(job, result, 60)
    tracker.close()

    found = runner.invoke(app, ["explain", "123", "--db", db])
    assert found.exit_code == 0
    for text in ("QA Engineer", "Score: 60/100 (model 70)", "Good fit overall.",
                 "Playwright", "German C1", "Ukraine only", "Work mode: remote"):
        assert text in found.stdout

    missing = runner.invoke(app, ["explain", "999", "--db", db])
    assert missing.exit_code == 1
    assert "No stored vacancy" in missing.stdout
