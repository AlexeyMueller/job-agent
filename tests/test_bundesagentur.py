import httpx
import respx

from job_agent.sources.bundesagentur import BASE_URL, BundesagenturClient, parse_job

SEARCH_URL = f"{BASE_URL}/pc/v6/jobs"

# Trimmed from a real v6 response.
SAMPLE = {
    "ergebnisliste": [
        {
            "stellenangebotsTitel": "QA Engineer (m/w/d), Frankfurt",
            "stellenlokationen": [
                {
                    "adresse": {
                        "strasse": "Untermainanlage 8",
                        "plz": "60329",
                        "ort": "Frankfurt am Main",
                        "region": "HESSEN",
                        "land": "DEUTSCHLAND",
                    },
                    "breite": 50.107842,
                    "laenge": 8.672706,
                }
            ],
            "homeofficemoeglich": False,
            "datumErsteVeroeffentlichung": "2026-09-24",
            "externeURL": "https://www.finest-jobs.com/stellenanzeige/Qa-Engineer-D-1318630?cp=BA",
            "hauptberuf": "Ingenieur/in - Sicherheitstechnik",
            "firma": "compeople",
            "referenznummer": "12811-2343588-S",
            "entfernung": 5,
        },
        {
            "stellenangebotsTitel": "Senior QA Engineer (m/w/d)",
            "gehaltsspanneVon": 60000.0,
            "gehaltsspanneBis": 70000.0,
            "stellenlokationen": [{"adresse": {"ort": "Seligenstadt, Hessen"}}],
            "homeofficemoeglich": True,
            "datumErsteVeroeffentlichung": "2026-08-19",
            "hauptberuf": "Qualitaetsingenieur/in",
            "firma": "camPoint AG",
            "referenznummer": "10001-1003569047-S",
            "entfernung": 26,
        },
    ],
    "maxErgebnisse": 12,
    "page": 1,
    "size": 2,
}


@respx.mock
def test_search_parses_jobs_and_sends_expected_request():
    route = respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=SAMPLE))

    jobs = BundesagenturClient().search("QA Engineer", wo="Frankfurt", umkreis=50)

    request = route.calls.last.request
    assert request.headers["X-API-Key"] == "jobboerse-jobsuche"
    assert request.url.params["was"] == "QA Engineer"
    assert request.url.params["wo"] == "Frankfurt"
    assert request.url.params["umkreis"] == "50"
    assert request.url.params["angebotsart"] == "1"

    assert len(jobs) == 2
    first = jobs[0]
    assert first.ref == "12811-2343588-S"
    assert first.title == "QA Engineer (m/w/d), Frankfurt"
    assert first.employer == "compeople"
    assert first.location == "Frankfurt am Main"
    assert str(first.published) == "2026-09-24"
    assert first.external_url.startswith("https://www.finest-jobs.com/")
    assert first.url == "https://www.arbeitsagentur.de/jobsuche/jobdetail/12811-2343588-S"
    assert first.home_office is False
    assert first.distance_km == 5

    second = jobs[1]
    assert second.home_office is True
    assert second.salary_min == 60000.0
    assert second.salary_max == 70000.0
    assert second.external_url is None


def test_parse_job_handles_missing_optional_fields():
    job = parse_job({"referenznummer": "1-2-S", "hauptberuf": "Tester/in"})
    assert job.title == "Tester/in"
    assert job.employer is None
    assert job.location is None
    assert job.published is None
    assert job.salary_min is None


@respx.mock
def test_search_returns_empty_list_when_no_results():
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json={"maxErgebnisse": 0}))
    assert BundesagenturClient().search("nonexistent") == []


@respx.mock
def test_search_raises_on_http_error():
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(500))
    try:
        BundesagenturClient().search("QA")
    except httpx.HTTPStatusError:
        return
    raise AssertionError("expected HTTPStatusError")


DETAILS = {
    "stellenangebotsTitel": "Senior QA Engineer (m/w/d)",
    "stellenangebotsBeschreibung": "Die campoint AG ist Technologiepartner ...",
    "firma": "camPoint AG",
    "gehaltsspanneVon": 60000.0,
    "gehaltsspanneBis": 70000.0,
    "homeofficemoeglich": True,
    "stellenlokationen": [{"adresse": {"ort": "Seligenstadt, Hessen"}}],
    "datumErsteVeroeffentlichung": "2026-08-19",
    "referenznummer": "10001-1003569047-S",
}


@respx.mock
def test_get_details_encodes_ref_and_parses_description():
    # base64("10001-1003569047-S")
    encoded = "MTAwMDEtMTAwMzU2OTA0Ny1T"
    route = respx.get(f"{BASE_URL}/pc/v4/jobdetails/{encoded}").mock(
        return_value=httpx.Response(200, json=DETAILS)
    )

    job = BundesagenturClient().get_details("10001-1003569047-S")

    assert route.called
    assert route.calls.last.request.headers["X-API-Key"] == "jobboerse-jobsuche"
    assert job.title == "Senior QA Engineer (m/w/d)"
    assert job.description.startswith("Die campoint AG")
    assert job.salary_min == 60000.0
    assert job.url.endswith("/jobdetail/10001-1003569047-S")
