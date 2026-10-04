from datetime import date

from pydantic import BaseModel


class Job(BaseModel):
    """A vacancy, normalised across sources."""

    source: str
    ref: str
    title: str
    employer: str | None = None
    location: str | None = None
    published: date | None = None
    external_url: str | None = None
