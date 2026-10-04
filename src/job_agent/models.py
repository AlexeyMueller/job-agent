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
    url: str | None = None  # vacancy page on the source portal
    external_url: str | None = None  # employer's own page, if any
    home_office: bool | None = None
    distance_km: int | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    description: str | None = None
