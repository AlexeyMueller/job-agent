import typer

from job_agent import __version__

app = typer.Typer(help="AI-assisted job search agent.")


@app.callback()
def main() -> None:
    """job-agent command line interface."""


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo(__version__)
