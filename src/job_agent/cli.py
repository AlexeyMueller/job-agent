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
