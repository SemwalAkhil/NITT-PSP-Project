from __future__ import annotations

import argparse
from datetime import datetime, timezone
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
from urllib.parse import urljoin

import requests
import sqlite3
from bs4 import BeautifulSoup
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeRemainingColumn
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .cleaning import PlantRecord, clean_text, split_values
from .database_operator import AyurvedicAlmanac, default_database_path
from .translation import GoogleNameTranslator, enrich_record


DRAVYA_DIRECTORY = "https://dravya.ccras.org.in/all_plants"
PLANT_PATH = re.compile(r"/plant/(\d+)(?:/|$)")
DEFAULT_TIMEOUT = 15.0
LANGUAGE_ALIASES = {
    "malyalam": "Malayalam",
    "oriya": "Odia",
}
@dataclass(frozen=True, slots=True)
class ScrapeFailure:
    plant_id: int
    url: str
    attempts: int
    error_type: str
    reason: str


class ScraperError(RuntimeError):
    """Expected scraper failure with actionable context."""


class DiscoveryError(ScraperError):
    pass


@dataclass(frozen=True, slots=True)
class DiscoveryReport:
    plants: list[tuple[int, str]]
    pages: int
    total_discovered: int
    termination: str


@dataclass(slots=True)
class ScrapeReport:
    processed: int = 0
    discovered: int = 0
    discovery_pages: int = 0
    discovery_termination: str = ""
    failures: list[ScrapeFailure] = field(default_factory=list)

    def write_json(self, path: str | Path) -> None:
        destination = Path(path)
        destination.write_text(
            json.dumps(
                {
                    "processed": self.processed,
                    "discovered": self.discovered,
                    "discovery_pages": self.discovery_pages,
                    "discovery_termination": self.discovery_termination,
                    "failed": len(self.failures),
                    "failures": [asdict(failure) for failure in self.failures],
                },
                indent=2,
                ensure_ascii=False,
            ) + "\n",
            encoding="utf-8",
        )


def create_session(retries: int = 2) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=retries,
        connect=retries,
        read=0,
        status=retries,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = "HerbalAlmanac/0.1 (research data collection)"
    return session


def fetch(session: requests.Session, url: str, timeout: float = DEFAULT_TIMEOUT) -> str:
    response = session.get(url, timeout=(5.0, timeout))
    response.raise_for_status()
    return response.text


def _discover_plants(
    session: requests.Session,
    directory_url: str = DRAVYA_DIRECTORY,
    max_pages: int | None = None,
) -> DiscoveryReport:
    """Discover plants, rejecting transient empty pages instead of truncating."""
    discovered: dict[int, str] = {}
    page = 1
    empty_page_attempts = 0
    while max_pages is None or page <= max_pages:
        url = f"{directory_url}?page={page}"
        soup = BeautifulSoup(fetch(session, url), "html.parser")
        before = len(discovered)
        for link in soup.find_all("a", href=True):
            match = PLANT_PATH.search(link["href"])
            if match:
                discovered[int(match.group(1))] = urljoin(directory_url, link["href"])
        if len(discovered) == before:
            empty_page_attempts += 1
            if page > 1 and empty_page_attempts >= 2:
                return DiscoveryReport(
                    sorted(discovered.items()), page, len(discovered), "two consecutive pages added no IDs"
                )
        else:
            empty_page_attempts = 0
        page += 1
    termination = "max_pages reached" if max_pages is not None else "pagination did not terminate"
    if max_pages is None:
        raise DiscoveryError(
            f"pagination did not terminate after {page - 1} pages; discovered {len(discovered)} plants"
        )
    return DiscoveryReport(sorted(discovered.items()), page - 1, len(discovered), termination)


def discover_plants(
    session: requests.Session,
    directory_url: str = DRAVYA_DIRECTORY,
    max_pages: int | None = None,
) -> DiscoveryReport:
    """Return discovered plants and pagination metadata."""
    return _discover_plants(session, directory_url, max_pages)


def _normalize_label(value: str) -> str:
    """Strip numbering and punctuation that appears in the DRAVYA table labels."""
    label = clean_text(value)
    label = re.sub(r"^(?:\d+[.)]?\s*)+", "", label)
    label = re.sub(r"^[\s\-:]+", "", label)
    label = re.sub(r"[:\s]+$", "", label)
    return label


def _section_name(table: BeautifulSoup) -> str:
    """Return the accordion section containing a table."""
    explicit = table.get("data-section") or table.get("data-section-name")
    if explicit:
        return _normalize_label(explicit)
    caption = table.find("caption")
    if caption:
        return _normalize_label(caption.get_text(" ", strip=True))
    heading = table.find_previous(class_="accordion-button")
    if heading is None:
        heading = table.find_previous("h3")
    if heading is None:
        return ""
    return _normalize_label(heading.get_text(" ", strip=True))


def _table_attributes(soup: BeautifulSoup) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Parse each table as a header row followed by records.

    DRAVYA tables are relational tables: the first row contains column names
    and every later row contains values for those columns. The accordion
    button supplies the parent section, which prevents fields such as
    ``Name`` from colliding across sections.
    """
    attributes: dict[str, list[str]] = {}
    source_values: dict[str, str] = {}
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        header_row = next((row for row in rows if row.find("th")), None)
        if header_row is None:
            continue

        headers = [
            _normalize_label(cell.get_text(" ", strip=True))
            for cell in header_row.find_all(["th", "td"])
        ]
        headers = [header for header in headers if header]
        if not headers:
            continue

        section = _section_name(table)
        if not section:
            section = "Unsectioned"
        for row in rows:
            if row is header_row:
                continue
            cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all("td")]
            if not cells:
                continue
            for index, value in enumerate(cells[:len(headers)]):
                if not value:
                    continue
                field = ".".join(part for part in (section, headers[index]) if part)
                values = split_values(value)
                attributes.setdefault(field, []).extend(values)
                existing = source_values.get(field, "")
                combined = [piece for piece in existing.split(" | ") if piece] if existing else []
                for item in values:
                    if item and item not in combined:
                        combined.append(item)
                source_values[field] = " | ".join(combined)

    return attributes, source_values


def _vernacular_attributes(soup: BeautifulSoup) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Extract language names from the DRAVYA vernacular-name card."""
    attributes: dict[str, list[str]] = {}
    source_values: dict[str, str] = {}
    header = next(
        (
            element
            for element in soup.select(".card-header")
            if "vernacular names" in element.get_text(" ", strip=True).casefold()
        ),
        None,
    )
    if header is None:
        return attributes, source_values

    card = header.find_parent(class_="card")
    if card is None:
        return attributes, source_values

    for badge in card.select(".badge"):
        language = clean_text(badge.get_text(" ", strip=True))
        language = LANGUAGE_ALIASES.get(language.casefold(), language)
        value_element = badge.parent.find("p") if badge.parent else None
        if not language or value_element is None:
            continue
        values = split_values(value_element.get_text(" ", strip=True))
        if not values:
            continue
        field = f"Vernacular Names.{language}"
        attributes.setdefault(field, []).extend(values)
        existing = source_values.get(field, "")
        combined = [piece for piece in existing.split(" | ") if piece] if existing else []
        for value in values:
            if value not in combined:
                combined.append(value)
        source_values[field] = " | ".join(combined)

    return attributes, source_values


def _scientific_profile(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    """Extract taxonomy from the live scientific-profile card."""
    scientific_name: str | None = None
    family: str | None = None
    for label in soup.select("small"):
        label_text = clean_text(label.get_text(" ", strip=True)).casefold()
        if label_text not in {"scientific name", "family name"}:
            continue
        value_container = label.find_parent("div")
        if value_container is None:
            continue
        value_element = label.find_next_sibling("span")
        if value_element is None:
            value_element = value_container.find_next("span")
        if value_element is None:
            continue
        value = clean_text(value_element.get_text(" ", strip=True))
        if label_text == "scientific name":
            italic = value_element.find("i")
            scientific_name = clean_text(italic.get_text(" ", strip=True)) if italic else value
        else:
            family = value
    return scientific_name, family


def _title_ayurvedic_name(title: str) -> str | None:
    """Return the source title's Ayurvedic/Sanskrit name when present."""
    if " - " not in title:
        return None
    value = clean_text(title.rsplit(" - ", 1)[1])
    return value or None


def parse_plant(plant_id: int, url: str, html: str) -> PlantRecord:
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.find(["h1", "h2"])
    title_element = soup.title
    title = (
        heading.get_text(" ", strip=True)
        if heading
        else title_element.get_text(" ", strip=True)
        if title_element
        else f"Plant {plant_id}"
    )
    attributes, source_values = _table_attributes(soup)
    vernacular_attributes, vernacular_source_values = _vernacular_attributes(soup)
    attributes.update(vernacular_attributes)
    source_values.update(vernacular_source_values)
    english_names = attributes.get("Vernacular Names.English", [])
    profile_botanical_name, profile_family = _scientific_profile(soup)
    botanical_name = profile_botanical_name or next(
        (value for field, values in attributes.items()
         if re.search(r"scientific|botanical", field, re.I)
         for value in values),
        None,
    )
    family = profile_family or next(
        (value for field, values in attributes.items() if re.search(r"family", field, re.I) for value in values),
        None,
    )
    ayurvedic_name = _title_ayurvedic_name(title) or (
        english_names[0] if english_names else clean_text(title.split("|")[0])
    )
    return PlantRecord(
        source="CCRAS DRAVYA",
        source_record_id=plant_id,
        source_url=url,
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        ayurvedic_name=ayurvedic_name,
        botanical_name=botanical_name,
        family=family,
        attributes=attributes,
        source_values=source_values,
    ).clean()


def scrape(
    database_path: str | Path | None = None,
    max_pages: int | None = None,
    max_plants: int | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = 2,
    record_retries: int = 1,
    failure_report_path: str | Path | None = None,
    translate: bool = False,
) -> ScrapeReport:
    if record_retries < 0:
        raise ValueError("record_retries must be non-negative")
    database_path = database_path or default_database_path()
    session = create_session(retries)
    translator = GoogleNameTranslator(cache_path=database_path) if translate else None
    try:
        discovery = discover_plants(session, max_pages=max_pages)
        plants = discovery.plants
        report = ScrapeReport(
            discovered=discovery.total_discovered,
            discovery_pages=discovery.pages,
            discovery_termination=discovery.termination,
        )
        if max_plants is not None:
            plants = plants[:max_plants]
        database = AyurvedicAlmanac(database_path)
        database.create_database()
        pending = list(plants)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task("Scraping plants", total=len(plants))
            for attempt in range(record_retries + 1):
                failed: list[tuple[int, str, Exception, int]] = []
                for plant_id, url in pending:
                    completed = False
                    progress.update(
                        task,
                        description=f"Scraping plant {plant_id}"
                        + (f" (retry {attempt})" if attempt else ""),
                    )
                    try:
                        record = parse_plant(plant_id, url, fetch(session, url, timeout))
                        if translator is not None:
                            record = enrich_record(record, translator)
                        record.validate()
                        database.insert_record(record)
                    except (requests.RequestException, ValueError, sqlite3.Error) as error:
                        failed.append((plant_id, url, error, attempt + 1))
                    else:
                        report.processed += 1
                        completed = True
                    if attempt == record_retries and not completed:
                        completed = True
                    if completed:
                        progress.advance(task)
                if not failed:
                    break
                pending = [(plant_id, url) for plant_id, url, _, _ in failed]
                if attempt == record_retries:
                    report.failures = [
                        ScrapeFailure(
                            plant_id=plant_id,
                            url=url,
                            attempts=attempts,
                            error_type=type(error).__name__,
                            reason=str(error) or "no error message",
                        )
                        for plant_id, url, error, attempts in failed
                    ]
        if failure_report_path is not None:
            report.write_json(failure_report_path)
        return report
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape CCRAS DRAVYA into SQLite.")
    parser.add_argument("--database", default=str(default_database_path()))
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--max-plants", type=int)
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="Read timeout in seconds for each HTTP request.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Number of retries for connection and temporary HTTP failures.",
    )
    parser.add_argument(
        "--record-retries",
        type=int,
        default=1,
        help="Number of separate retries for plants that fail processing.",
    )
    parser.add_argument(
        "--failure-report",
        type=Path,
        help="Write failed plant details as JSON to this path.",
    )
    parser.add_argument(
        "--translate",
        action="store_true",
        help="Enable machine translation enrichment (disabled by default).",
    )
    args = parser.parse_args()
    try:
        print(scrape(
            args.database,
            args.max_pages,
            args.max_plants,
            args.timeout,
            args.retries,
            args.record_retries,
            args.failure_report,
            args.translate,
        ))
    except KeyboardInterrupt:
        parser.exit(130, "Scrape interrupted by user.\n")


if __name__ == "__main__":
    main()
