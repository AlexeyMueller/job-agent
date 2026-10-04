import httpx
import respx

from job_agent.sources.bundesagentur import BASE_URL, BundesagenturClient, parse_job

SEARCH_URL = f"{BASE_URL}/pc/v4/jobs"

SAMPLE = {
    "stellenangebote": [
        {
            "refnr": "10001-1002716922-S",
            "titel": "QA Engineer (m/w/d)",
            "beruf": "Softwaretester/in",
            "arbeitgeber": "Example GmbH",
            "aktuelleVeroeffentlichungsdatum": "2026-09-30",
            "arbeitsort": {"ort": "Frankfurt am Main", "region": "Hessen"},
            "externeUrl": "https://example.com/job/1",
        },
        {"refnr": "10001-2-S", "beruf": "Softwaretester/in"},
    ],
    "maxErgebnisse": "2",
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
    assert first.ref == "10001-1002716922-S"
    assert first.title == "QA Engineer (m/w/d)"
    assert first.employer == "Example GmbH"
    assert first.location == "Frankfurt am Main, Hessen"
    assert str(first.published) == "2026-09-30"
    assert first.external_url == "https://example.com/job/1"


def test_parse_job_handles_missing_optional_fields():
    job = parse_job({"refnr": "10001-2-S", "beruf": "Softwaretester/in"})
    assert job.title == "Softwaretester/in"
    assert job.employer is None
    assert job.location is None
    assert job.published is None


@respx.mock
def test_search_returns_empty_list_when_no_results():
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json={"maxErgebnisse": "0"}))
    assert BundesagenturClient().search("nonexistent") == []


@respx.mock
def test_search_raises_on_http_error():
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(500))
    try:
        BundesagenturClient().search("QA")
    except httpx.HTTPStatusError:
        return
    raise AssertionError("expected HTTPStatusError")
