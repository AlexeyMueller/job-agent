from datetime import date

import httpx
import respx

from job_agent.config import Config
from job_agent.sources.dou import DouSource, html_to_text, parse_dou_feed

FEED_URL = "https://jobs.dou.ua/vacancies/feeds/?exp=3-5&category=QA"

FEED = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>QA</title>
<item>
<title>QA Automation Engineer в Creatio, Київ, Варшава (Польща), віддалено</title>
<link>https://jobs.dou.ua/companies/creatio/vacancies/367877/?utm_source=jobsrss</link>
<description>&lt;p&gt;We seek an engineer.&lt;/p&gt;&lt;h3&gt;Requirements:&lt;/h3&gt;&lt;ul&gt;&lt;li&gt;Playwright &amp;amp; TypeScript&lt;/li&gt;&lt;li&gt;API testing&lt;/li&gt;&lt;/ul&gt;&lt;div&gt;&lt;a href="x"&gt;Відгукнутись на вакансію&lt;/a&gt;&lt;/div&gt;</description>
<pubDate>Thu, 30 Jul 2026 15:03:50 +0300</pubDate>
<guid>https://jobs.dou.ua/companies/creatio/vacancies/367877/?1785413030</guid>
</item>
<item>
<title>QA Automation Engineer в CHI Software, $2 800–3500, віддалено</title>
<link>https://jobs.dou.ua/companies/chi-software/vacancies/367825/?utm_source=jobsrss</link>
<description>&lt;p&gt;Playwright role&lt;/p&gt;</description>
<pubDate>Thu, 30 Jul 2026 11:25:49 +0300</pubDate>
<guid>https://jobs.dou.ua/companies/chi-software/vacancies/367825/?1</guid>
</item>
<item>
<title>Middle &amp;amp; Senior Hardware QA Engineer в Infozahyst, Київ</title>
<link>https://jobs.dou.ua/companies/infozahyst/vacancies/357275/?utm_source=jobsrss</link>
<description>&lt;p&gt;Hardware&lt;/p&gt;</description>
<pubDate>Tue, 21 Jul 2026 11:41:44 +0300</pubDate>
<guid>https://jobs.dou.ua/companies/infozahyst/vacancies/357275/?2</guid>
</item>
</channel></rss>"""


def test_parse_feed_fields():
    jobs = parse_dou_feed(FEED)
    assert [j.ref for j in jobs] == ["367877", "367825", "357275"]

    creatio = jobs[0]
    assert creatio.source == "dou"
    assert creatio.title == "QA Automation Engineer"
    assert creatio.employer == "Creatio"
    assert creatio.location == "Київ, Варшава (Польща), віддалено"
    assert creatio.home_office is True
    assert creatio.url == "https://jobs.dou.ua/companies/creatio/vacancies/367877/"
    assert creatio.published == date(2026, 7, 30)
    assert creatio.salary_min is None


def test_parse_salary_and_html_entities_in_title():
    jobs = parse_dou_feed(FEED)
    chi = jobs[1]
    assert (chi.salary_min, chi.salary_max) == (2800.0, 3500.0)
    assert chi.location == "віддалено"  # the salary token is not part of the location
    assert jobs[2].title == "Middle & Senior Hardware QA Engineer"
    assert jobs[2].home_office is False


def test_html_to_text_strips_tags_keeps_structure_and_drops_reply_link():
    text = parse_dou_feed(FEED)[0].description
    assert "<" not in text
    assert "Playwright & TypeScript" in text
    assert "- API testing" in text
    assert "Відгукнутись" not in text
    assert text.startswith("We seek an engineer.")


def test_html_to_text_collapses_blank_lines():
    assert html_to_text("<p>a</p><p></p><p></p><p>b</p>") == "a\n\nb"


@respx.mock
def test_source_filters_old_vacancies_and_sends_user_agent():
    route = respx.get(FEED_URL).mock(return_value=httpx.Response(200, text=FEED))
    config = Config()  # 14 days window
    source = DouSource([FEED_URL], today=lambda: date(2026, 8, 10))  # cutoff: 27 Jul

    jobs = source.collect(config)

    assert {j.ref for j in jobs} == {"367877", "367825"}  # 21 Jul is before the cutoff
    assert route.calls.last.request.headers["User-Agent"].startswith("job-agent")


@respx.mock
def test_source_merges_duplicate_vacancies_across_feeds():
    other = "https://jobs.dou.ua/vacancies/feeds/?exp=5plus&category=QA"
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, text=FEED))
    respx.get(other).mock(return_value=httpx.Response(200, text=FEED))
    source = DouSource([FEED_URL, other], today=lambda: date(2026, 7, 31))
    assert len(source.collect(Config())) == 3


def test_details_are_the_job_itself():
    job = parse_dou_feed(FEED)[0]
    assert DouSource([]).get_details(job) is job
