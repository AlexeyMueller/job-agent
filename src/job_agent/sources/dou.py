"""jobs.dou.ua RSS source (Ukrainian IT job board). Feeds carry full descriptions."""

import html
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import date, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit

import httpx

from job_agent.config import Config
from job_agent.models import Job

SOURCE = "dou"
USER_AGENT = "job-agent/0.1 (personal job search tool)"
_SALARY = re.compile(r"^\$\s*([\d\s]+?)\s*[–-]\s*([\d\s]+)$")
_REPLY_LINE = "Відгукнутись на вакансію"
_BLOCK_TAGS = {"p", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "div", "tr"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("- ")

    def handle_endtag(self, tag):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def html_to_text(markup: str) -> str:
    parser = _TextExtractor()
    parser.feed(markup)
    text = "".join(parser.parts).replace(_REPLY_LINE, "")
    lines = [line.strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _parse_title(raw_title: str) -> tuple[str, str | None, str | None, float | None, float | None]:
    """'Job title в Company, $1000–2000, Київ, віддалено' -> title, company, location, salary."""
    text = html.unescape(raw_title).strip()
    if " в " not in text:
        return text, None, None, None, None
    title, rest = text.rsplit(" в ", 1)
    parts = [part.strip() for part in rest.split(",")]
    company, tokens = parts[0], parts[1:]
    salary_min = salary_max = None
    places = []
    for token in tokens:
        match = _SALARY.match(token)
        if match:
            salary_min = float(re.sub(r"\s", "", match.group(1)))
            salary_max = float(re.sub(r"\s", "", match.group(2)))
        elif token:
            places.append(token)
    return title.strip(), company, ", ".join(places) or None, salary_min, salary_max


def parse_dou_feed(xml_text: str) -> list[Job]:
    root = ET.fromstring(xml_text)
    jobs = []
    for item in root.iter("item"):
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or "").strip()
        id_match = re.search(r"/vacancies/(\d+)", link or guid)
        if not id_match:
            continue
        title, company, location, salary_min, salary_max = _parse_title(
            item.findtext("title") or ""
        )
        published = None
        if item.findtext("pubDate"):
            published = parsedate_to_datetime(item.findtext("pubDate")).date()
        parts = urlsplit(link)
        clean_url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        jobs.append(
            Job(
                source=SOURCE,
                ref=id_match.group(1),
                title=title,
                employer=company,
                location=location,
                published=published,
                url=clean_url,
                home_office="віддалено" in (location or "").lower(),
                salary_min=salary_min,
                salary_max=salary_max,
                description=html_to_text(item.findtext("description") or ""),
            )
        )
    return jobs


class DouSource:
    name = SOURCE

    def __init__(
        self,
        feeds: list[str],
        client: httpx.Client | None = None,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._feeds = feeds
        self._client = client or httpx.Client(timeout=30, follow_redirects=True)
        self._today = today

    def collect(self, config: Config) -> list[Job]:
        cutoff = self._today() - timedelta(days=config.search.published_within_days)
        found: dict[str, Job] = {}
        for url in self._feeds:
            response = self._client.get(url, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            for job in parse_dou_feed(response.text):
                if job.published and job.published < cutoff:
                    continue
                found.setdefault(job.ref, job)
        return list(found.values())

    def get_details(self, job: Job) -> Job:
        return job  # the feed already contains the full description
