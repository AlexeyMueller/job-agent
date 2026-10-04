from datetime import date

import pytest

from job_agent.config import Config, adjust_score, load_config
from job_agent.models import Job
from job_agent.pipeline import run
from job_agent.scorer import ScoreResult
from job_agent.tracker import Tracker


def make_job(ref, title="QA Engineer", home_office=False, distance=None, published="2026-09-30"):
    return Job(
        source="bundesagentur",
        ref=ref,
        title=title,
        employer="Example GmbH",
        location="Frankfurt",
        published=date.fromisoformat(published),
        home_office=home_office,
        distance_km=distance,
        description=f"description of {ref}",
    )


class FakeSource:
    def __init__(self, local, nationwide):
        self.local, self.nationwide = local, nationwide
        self.details = {j.ref: j for j in local + nationwide}

    def search(self, was, wo=None, umkreis=None, veroeffentlichtseit=None, page=1, size=25):
        return list(self.local if wo else self.nationwide)

    def get_details(self, ref):
        job = self.details[ref]
        return job.model_copy(update={"distance_km": None})  # details lack the distance


class FakeScorer:
    def __init__(self, score=80, work_mode="onsite", fail_on=None, avoided=()):
        self.score_value, self.work_mode, self.fail_on = score, work_mode, fail_on
        self.avoided = list(avoided)
        self.calls = []

    def score(self, job, profile):
        self.calls.append(job.ref)
        if job.ref == self.fail_on:
            raise RuntimeError("boom")
        return ScoreResult(
            score=self.score_value, apply=True, summary="s", match_reasons=[], gaps=[],
            red_flags=[], work_mode=self.work_mode, required_avoided_skills=self.avoided,
        )


@pytest.fixture
def config():
    cfg = Config()
    cfg.search.keywords = ["QA Engineer"]
    return cfg


@pytest.fixture
def tracker():
    t = Tracker(":memory:")
    yield t
    t.close()


def sample_source():
    local = [
        make_job("A", distance=5),
        make_job("B", title="Werkstudent QA", distance=7),
    ]
    nationwide = [
        make_job("A", distance=None),  # duplicate of A
        make_job("C", home_office=True),
        make_job("D", home_office=False),  # onsite far away: filtered out
    ]
    return FakeSource(local, nationwide)


def test_dedupes_excludes_and_filters_nationwide(config, tracker):
    scorer = FakeScorer()
    report = run(sample_source(), scorer, tracker, {}, config)
    assert sorted(scorer.calls) == ["A", "C"]
    assert report.found == 3  # A, B, C (D is filtered out before counting)
    assert report.excluded == 1
    assert report.scored == 2


def test_second_run_scores_nothing_new(config, tracker):
    scorer = FakeScorer()
    run(sample_source(), scorer, tracker, {}, config)
    scorer.calls.clear()
    report = run(sample_source(), scorer, tracker, {}, config)
    assert scorer.calls == []
    assert report.already_known == 2


def test_cap_limits_paid_calls_and_prefers_newest(config, tracker):
    config.scoring.max_new_per_run = 1
    local = [make_job("OLD", published="2026-09-01"), make_job("NEW", published="2026-09-30")]
    scorer = FakeScorer()
    run(FakeSource(local, []), scorer, tracker, {}, config)
    assert scorer.calls == ["NEW"]


def test_dry_run_does_not_score_or_save(config, tracker):
    scorer = FakeScorer()
    lines = []
    report = run(sample_source(), scorer, tracker, {}, config, dry_run=True, log=lines.append)
    assert scorer.calls == []
    assert report.to_score == 2 and report.scored == 0
    assert tracker.top(0) == []
    assert len(lines) == 2


def test_failure_is_skipped_and_retried_next_time(config, tracker):
    scorer = FakeScorer(fail_on="C")
    report = run(sample_source(), scorer, tracker, {}, config, log=lambda _: None)
    assert report.failed == 1 and report.scored == 1
    assert not tracker.has("bundesagentur", "C")


def test_distance_from_search_is_kept_for_adjustment(config, tracker):
    # A is local (5 km): onsite_local -15. C is nationwide, home office, hybrid: relocation -20.
    scorer = FakeScorer(score=80, work_mode="hybrid")
    run(sample_source(), scorer, tracker, {}, config)
    rows = {r["ref"]: r for r in tracker.top(0)}
    assert rows["A"]["final_score"] == 70  # hybrid_local -10
    assert rows["C"]["final_score"] == 60  # hybrid_relocation -20


@pytest.mark.parametrize(
    "mode,distance,expected",
    [
        ("remote", None, 80),
        ("remote", 500, 80),
        ("mostly_remote", 10, 77),
        ("mostly_remote", 200, 70),
        ("hybrid", 10, 70),
        ("onsite", 10, 65),
        ("hybrid", 200, 60),
        ("onsite", 200, 50),
        ("onsite", None, 50),
    ],
)
def test_adjust_score(mode, distance, expected):
    assert adjust_score(80, mode, distance, Config()) == expected


def test_adjust_score_is_clamped():
    assert adjust_score(10, "onsite", None, Config()) == 0


def test_load_config_defaults_and_partial_file(tmp_path):
    assert load_config(tmp_path / "missing.yaml").scoring.min_score == 60
    path = tmp_path / "config.yaml"
    path.write_text("search:\n  radius_km: 80\n", encoding="utf-8")
    cfg = load_config(path)
    assert cfg.search.radius_km == 80
    assert cfg.search.keywords == ["QA Engineer", "Software Tester", "QA Analyst"]


def test_tracker_top_filters_and_orders(tracker):
    result = ScoreResult(
        score=50, apply=False, summary="s", match_reasons=[], gaps=[], red_flags=[]
    )
    tracker.save(make_job("LOW"), result, 40)
    tracker.save(make_job("HIGH"), result, 90)
    tracker.save(make_job("MID"), result, 65)
    assert [r["ref"] for r in tracker.top(60)] == ["HIGH", "MID"]


def test_default_avoid_list_has_german_and_english_names():
    names = {s.name for s in Config().scoring.avoid_skills}
    aliases = {a for s in Config().scoring.avoid_skills for a in s.aliases}
    assert {"Penetration testing", "Load and performance testing"} <= names
    assert {"Penetrationstest", "Lasttest", "Pentest", "Load testing"} <= aliases


def test_adjust_score_applies_skill_penalty_even_for_remote():
    skills = ["Penetration testing"]
    assert adjust_score(80, "remote", None, Config(), skills) == 70


def test_adjust_score_skill_penalty_is_capped_and_ignores_unknown_names():
    cfg = Config()
    cfg.scoring.skill_penalty = -20
    two = ["Penetration testing", "Load and performance testing"]
    assert adjust_score(90, "remote", None, cfg, two) == 60  # -40 capped to -30
    assert adjust_score(90, "remote", None, cfg, ["Made up skill"]) == 90
    assert adjust_score(90, "remote", None, cfg, ["penetration testing"] * 3) == 70  # counted once


def test_pipeline_subtracts_skill_penalty(config, tracker):
    scorer = FakeScorer(score=80, work_mode="remote", avoided=["Penetration testing"])
    run(sample_source(), scorer, tracker, {}, config)
    assert {r["final_score"] for r in tracker.top(0)} == {70}


def test_default_avoid_list_has_selenium_with_playwright_exception():
    skills = {s.name: s for s in Config().scoring.avoid_skills}
    selenium = skills["Selenium, Cypress, Appium"]
    assert {"Selenium", "Cypress", "Appium"} <= set(selenium.aliases)
    assert "Playwright" in selenium.exception
