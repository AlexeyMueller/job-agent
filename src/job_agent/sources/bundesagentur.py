"""Client for the Bundesagentur fuer Arbeit Jobsuche service (pc/v6).

Note: this is the public endpoint used by the agency's own apps and documented by the
community (https://github.com/bundesAPI/jobsuche-api). It is not an officially supported
API, so parameters and field names may change.
"""

import base64

import httpx

from job_agent.config import Config
from job_agent.models import Job

BASE_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
API_KEY = "jobboerse-jobsuche"
SOURCE = "bundesagentur"
JOB_URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{ref}"


def parse_job(raw: dict) -> Job:
    """Convert a search result item or a job-details response into a Job."""
    locations = raw.get("stellenlokationen") or []
    address = (locations[0].get("adresse") or {}) if locations else {}
    published = raw.get("datumErsteVeroeffentlichung") or (
        raw.get("veroeffentlichungszeitraum") or {}
    ).get("von")
    ref = raw["referenznummer"]
    return Job(
        source=SOURCE,
        ref=ref,
        title=raw.get("stellenangebotsTitel") or raw.get("hauptberuf") or "",
        employer=raw.get("firma"),
        location=address.get("ort") or None,
        published=published,
        url=JOB_URL.format(ref=ref),
        external_url=raw.get("externeURL"),
        home_office=raw.get("homeofficemoeglich"),
        distance_km=raw.get("entfernung"),
        salary_min=raw.get("gehaltsspanneVon"),
        salary_max=raw.get("gehaltsspanneBis"),
        description=raw.get("stellenangebotsBeschreibung"),
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
        }
        if wo:
            params["wo"] = wo
        if umkreis is not None:
            params["umkreis"] = umkreis
        if veroeffentlichtseit is not None:
            params["veroeffentlichtseit"] = veroeffentlichtseit

        response = self._client.get(
            f"{BASE_URL}/pc/v6/jobs",
            params=params,
            headers={"X-API-Key": API_KEY},
        )
        response.raise_for_status()
        items = response.json().get("ergebnisliste") or []
        return [parse_job(item) for item in items]

    def get_details(self, ref: str) -> Job:
        """Fetch a single vacancy including its full description."""
        encoded = base64.b64encode(ref.encode()).decode()
        response = self._client.get(
            f"{BASE_URL}/pc/v4/jobdetails/{encoded}",
            headers={"X-API-Key": API_KEY},
        )
        response.raise_for_status()
        return parse_job(response.json())


class BundesagenturSource:
    """Adapter used by the pipeline: local search plus a nationwide search."""

    name = SOURCE

    def __init__(self, client: BundesagenturClient | None = None) -> None:
        self._client = client or BundesagenturClient()

    def collect(self, config: Config) -> list[Job]:
        s = config.search
        found: dict[str, Job] = {}
        for keyword in s.keywords:
            local = self._client.search(
                keyword,
                wo=s.location,
                umkreis=s.radius_km,
                veroeffentlichtseit=s.published_within_days,
                size=s.max_per_query,
            )
            for job in local:
                found.setdefault(job.ref, job)
            nationwide = self._client.search(
                keyword, veroeffentlichtseit=s.published_within_days, size=s.max_per_query
            )
            for job in nationwide:
                if s.nationwide_requires_home_office and not job.home_office:
                    continue
                found.setdefault(job.ref, job)
        return list(found.values())

    def get_details(self, job: Job) -> Job:
        detail = self._client.get_details(job.ref)
        return detail.model_copy(update={"distance_km": job.distance_km})
