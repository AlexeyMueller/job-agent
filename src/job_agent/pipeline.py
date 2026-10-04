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


def collect_candidates(source, config: Config) -> list[Job]:
    """All distinct vacancies found by the configured searches (local first, then nationwide)."""
    s = config.search
    found: dict[str, Job] = {}
    for keyword in s.keywords:
        local = source.search(
            keyword,
            wo=s.location,
            umkreis=s.radius_km,
            veroeffentlichtseit=s.published_within_days,
            size=s.max_per_query,
        )
        for job in local:
            found.setdefault(job.ref, job)
        nationwide = source.search(
            keyword, veroeffentlichtseit=s.published_within_days, size=s.max_per_query
        )
        for job in nationwide:
            if s.nationwide_requires_home_office and not job.home_office:
                continue
            found.setdefault(job.ref, job)
    return list(found.values())


def run(
    source,
    scorer,
    tracker: Tracker,
    profile: dict | None,
    config: Config,
    dry_run: bool = False,
    log: Callable[[str], None] = print,
) -> RunReport:
    report = RunReport()
    candidates = collect_candidates(source, config)
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
            log(f"would score: {job.title} | {job.employer} | {job.location} | {job.ref}")
        return report

    for job in fresh:
        try:
            detail = source.get_details(job.ref).model_copy(
                update={"distance_km": job.distance_km}
            )
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
