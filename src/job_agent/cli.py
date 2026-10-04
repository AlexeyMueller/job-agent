import json
import os

import typer
from dotenv import load_dotenv

from job_agent import __version__
from job_agent.config import Config, load_config
from job_agent.pipeline import run as run_pipeline
from job_agent.profile import load_profile
from job_agent.scorer import DEFAULT_MODEL, Scorer
from job_agent.sources.bundesagentur import BundesagenturClient
from job_agent.tracker import Tracker

app = typer.Typer(help="AI-assisted job search agent.")


@app.callback()
def main() -> None:
    """job-agent command line interface."""
    load_dotenv()


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo(__version__)


@app.command()
def search(
    was: str = typer.Argument(..., help="Job title or keywords, e.g. 'QA Engineer'"),
    wo: str = typer.Option(None, help="Location, e.g. 'Frankfurt am Main'"),
    umkreis: int = typer.Option(None, help="Radius in km"),
    days: int = typer.Option(None, help="Only vacancies published in the last N days"),
    size: int = typer.Option(10, help="Number of results"),
) -> None:
    """Search Bundesagentur vacancies and print them."""
    jobs = BundesagenturClient().search(
        was, wo=wo, umkreis=umkreis, veroeffentlichtseit=days, size=size
    )
    for job in jobs:
        typer.echo(f"{job.title} | {job.employer} | {job.location} | {job.published} | {job.ref}")
    typer.echo(f"{len(jobs)} result(s)")


@app.command()
def show(
    ref: str = typer.Argument(..., help="Reference number, e.g. 10001-1003569047-S"),
    chars: int = typer.Option(1500, help="How many characters of the description to print"),
) -> None:
    """Show one vacancy with its description."""
    job = BundesagenturClient().get_details(ref)
    typer.echo(f"{job.title} | {job.employer} | {job.location}")
    typer.echo(f"Link: {job.url}")
    if job.external_url:
        typer.echo(f"Employer page: {job.external_url}")
    description = job.description or ""
    typer.echo(f"Description ({len(description)} chars):")
    typer.echo(description[:chars])


def _require_api_key() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        typer.echo("ANTHROPIC_API_KEY is not set. Put it in a .env file (see .env.example).")
        raise typer.Exit(code=1)


@app.command()
def score(
    ref: str = typer.Argument(..., help="Reference number of the vacancy"),
    model: str = typer.Option(DEFAULT_MODEL, help="Claude model used for scoring"),
    profile_path: str = typer.Option("profile.yaml", "--profile", help="Path to profile.yaml"),
    config_path: str = typer.Option("config.yaml", "--config", help="Path to config.yaml"),
) -> None:
    """Score one vacancy against your profile."""
    _require_api_key()
    profile = load_profile(profile_path)
    config = load_config(config_path)
    job = BundesagenturClient().get_details(ref)
    result = Scorer(model=model, avoid_skills=config.scoring.avoid_skills).score(job, profile)
    typer.echo(f"{job.title} | {job.employer} | {job.location}")
    typer.echo(f"Link: {job.url}")
    typer.echo(f"Score: {result.score}/100 | Apply: {'yes' if result.apply else 'no'}")
    typer.echo(f"Work mode: {result.work_mode}")
    if result.required_avoided_skills:
        typer.echo(f"Requires skills you lack: {', '.join(result.required_avoided_skills)}")
    typer.echo(result.summary)
    for title, items in (
        ("Matches", result.match_reasons),
        ("Gaps", result.gaps),
        ("Red flags", result.red_flags),
    ):
        if items:
            typer.echo(f"{title}:")
            for item in items:
                typer.echo(f"  - {item}")
    if result.language_requirement:
        typer.echo(f"Language: {result.language_requirement}")


def _print_row(
    config: Config, title, employer, location, mode, final, model_score, url, avoided=()
) -> None:
    flag = "*" if final >= config.scoring.min_score else " "
    typer.echo(
        f"{flag} {final:>3} (model {model_score}) | {mode:<13} | "
        f"{title} | {employer} | {location}\n      {url}"
    )
    if avoided:
        typer.echo(f"      requires skills you lack: {', '.join(avoided)}")


@app.command()
def run(
    config_path: str = typer.Option("config.yaml", "--config", help="Path to config.yaml"),
    profile_path: str = typer.Option("profile.yaml", "--profile", help="Path to profile.yaml"),
    db: str = typer.Option("jobs.db", help="SQLite file with already processed vacancies"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Search only: show what would be scored, no API cost"
    ),
) -> None:
    """Search, skip known vacancies, score new ones and store the results."""
    config = load_config(config_path)
    if not dry_run:
        _require_api_key()
        profile = load_profile(profile_path)
        scorer = Scorer(model=config.scoring.model, avoid_skills=config.scoring.avoid_skills)
    else:
        profile, scorer = None, None
    tracker = Tracker(db)
    try:
        report = run_pipeline(
            BundesagenturClient(), scorer, tracker, profile, config,
            dry_run=dry_run, log=typer.echo,
        )
    finally:
        tracker.close()

    typer.echo(
        f"Found {report.found}: {report.excluded} excluded, {report.already_known} already known, "
        f"{report.to_score} to score, {report.scored} scored, {report.failed} failed."
    )
    for job, result, final in sorted(report.results, key=lambda r: r[2], reverse=True):
        _print_row(
            config, job.title, job.employer, job.location,
            result.work_mode, final, result.score, job.url, result.required_avoided_skills,
        )


@app.command(name="list")
def list_jobs(
    config_path: str = typer.Option("config.yaml", "--config", help="Path to config.yaml"),
    db: str = typer.Option("jobs.db", help="SQLite file with processed vacancies"),
    min_score: int = typer.Option(None, help="Minimum final score (default: from config)"),
    limit: int = typer.Option(30, help="Maximum rows"),
) -> None:
    """Show the best stored vacancies."""
    config = load_config(config_path)
    threshold = config.scoring.min_score if min_score is None else min_score
    tracker = Tracker(db)
    try:
        rows = tracker.top(threshold, limit)
    finally:
        tracker.close()
    for row in rows:
        _print_row(
            config, row["title"], row["employer"], row["location"],
            row["work_mode"], row["final_score"], row["model_score"], row["url"],
            json.loads(row["result_json"]).get("required_avoided_skills", []),
        )
    typer.echo(f"{len(rows)} vacancy(ies) with final score >= {threshold}")
