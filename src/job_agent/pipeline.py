"""Daily run: search, drop known and excluded vacancies, score the new ones, store results."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from job_agent.config import Config, adjust_score
from job_agent.models import Job
from job_agent.scorer import ScoreResult
from job_agent.tracker import Tracker


@dataclass
class RunReport:
    found: int = 0
    excluded: int = 0
    already_known: int = 0
    to_score: int = 0
    scored: int = 0
    failed: int = 0
    results: list[tuple[Job, ScoreResult, int]] = field(default_factory=list)


def collect_candidates(
    sources, config: Config, log: Callable[[str], None] = print
) -> list[Job]:
    """Distinct vacancies from all sources. A failing source is logged and skipped."""
    found: dict[tuple[str, str], Job] = {}
    for source in sources:
        try:
            jobs = source.collect(config)
        except Exception as error:  # noqa: BLE001 - one broken source must not stop the run
            log(f"source {source.name} failed: {error}")
            continue
        for job in jobs:
            found.setdefault((job.source, job.ref), job)
    return list(found.values())


def run(
    sources,
    scorer,
    tracker: Tracker,
    profile: dict | None,
    config: Config,
    dry_run: bool = False,
    log: Callable[[str], None] = print,
) -> RunReport:
    report = RunReport()
    candidates = collect_candidates(sources, config, log)
    by_name = {source.name: source for source in sources}
    report.found = len(candidates)

    excluded_words = [w.lower() for w in config.search.exclude_keywords]
    fresh: list[Job] = []
    for job in candidates:
        if any(word in job.title.lower() for word in excluded_words):
            report.excluded += 1
        elif tracker.has(job.source, job.ref):
            report.already_known += 1
        else:
            fresh.append(job)

    fresh.sort(key=lambda j: j.published or date.min, reverse=True)
    fresh = fresh[: config.scoring.max_new_per_run]
    report.to_score = len(fresh)

    if dry_run:
        for job in fresh:
            log(
                f"would score [{job.source}]: {job.title} | {job.employer} | "
                f"{job.location} | {job.ref}"
            )
        return report

    for job in fresh:
        try:
            detail = by_name[job.source].get_details(job)
            result = scorer.score(detail, profile)
        except Exception as error:  # noqa: BLE001 - keep going; retried on the next run
            report.failed += 1
            log(f"failed: {job.ref}: {error}")
            continue
        final = adjust_score(
            result.score,
            result.work_mode,
            detail.distance_km,
            config,
            result.required_avoided_skills,
        )
        tracker.save(detail, result, final)
        report.scored += 1
        report.results.append((detail, result, final))
    return report
