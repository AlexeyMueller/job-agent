import typer

from job_agent import __version__
from job_agent.sources.bundesagentur import BundesagenturClient

app = typer.Typer(help="AI-assisted job search agent.")


@app.callback()
def main() -> None:
    """job-agent command line interface."""


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
