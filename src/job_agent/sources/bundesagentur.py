"""Client for the Bundesagentur fuer Arbeit Jobsuche service.

Note: this is the public endpoint used by the agency's own apps and documented by the
community (https://github.com/bundesAPI/jobsuche-api). It is not an officially supported
API, so parameters and field names may change.
"""

import httpx

from job_agent.models import Job

BASE_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
API_KEY = "jobboerse-jobsuche"
SOURCE = "bundesagentur"


def parse_job(raw: dict) -> Job:
    """Convert one item of `stellenangebote` into a Job."""
    place = raw.get("arbeitsort") or {}
    location = ", ".join(p for p in (place.get("ort"), place.get("region")) if p) or None
    return Job(
        source=SOURCE,
        ref=raw.get("refnr") or raw["referenznummer"],
        title=raw.get("titel") or raw.get("beruf") or "",
        employer=raw.get("arbeitgeber"),
        location=location,
        published=raw.get("aktuelleVeroeffentlichungsdatum"),
        external_url=raw.get("externeUrl"),
    )


class BundesagenturClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=30)

    def search(
        self,
        was: str,
        wo: str | None = None,
        umkreis: int | None = None,
        veroeffentlichtseit: int | None = None,
        page: int = 1,
        size: int = 25,
    ) -> list[Job]:
        params: dict[str, str | int] = {
            "angebotsart": 1,  # 1 = regular employment
            "was": was,
            "page": page,
            "size": size,
            "pav": "false",
        }
        if wo:
            params["wo"] = wo
        if umkreis is not None:
            params["umkreis"] = umkreis
        if veroeffentlichtseit is not None:
            params["veroeffentlichtseit"] = veroeffentlichtseit

        response = self._client.get(
            f"{BASE_URL}/pc/v4/jobs",
            params=params,
            headers={"X-API-Key": API_KEY},
        )
        response.raise_for_status()
        items = response.json().get("stellenangebote") or []
        return [parse_job(item) for item in items]
