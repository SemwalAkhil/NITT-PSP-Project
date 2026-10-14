from __future__ import annotations

import argparse
from datetime import datetime, timezone
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeRemainingColumn
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from cleaning import PlantRecord, clean_text, split_values
from database_operator import AyurvedicAlmanac
from translation import GoogleNameTranslator, enrich_record


DRAVYA_DIRECTORY = "https://dravya.ccras.org.in/all_plants"
PLANT_PATH = re.compile(r"/plant/(\d+)(?:/|$)")
DEFAULT_TIMEOUT = 15.0
LANGUAGE_ALIASES = {
    "malyalam": "Malayalam",
    "oriya": "Odia",
}


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


def discover_plants(
    session: requests.Session,
    directory_url: str = DRAVYA_DIRECTORY,
    max_pages: int | None = None,
) -> list[tuple[int, str]]:
    """Discover unique plant IDs and absolute URLs until pagination is exhausted."""
    discovered: dict[int, str] = {}
    page = 1
    while max_pages is None or page <= max_pages:
        url = f"{directory_url}?page={page}"
        soup = BeautifulSoup(fetch(session, url), "html.parser")
        before = len(discovered)
        for link in soup.find_all("a", href=True):
            match = PLANT_PATH.search(link["href"])
            if match:
                discovered[int(match.group(1))] = urljoin(directory_url, link["href"])
        if len(discovered) == before and page > 1:
            break
        page += 1
    return sorted(discovered.items())


def _normalize_label(value: str) -> str:
    """Strip numbering and punctuation that appears in the DRAVYA table labels."""
    label = clean_text(value)
    label = re.sub(r"^(?:\d+[.)]?\s*)+", "", label)
    label = re.sub(r"^[\s\-:]+", "", label)
    label = re.sub(r"[:\s]+$", "", label)
    return label


def _section_name(table: BeautifulSoup) -> str:
    """Return the accordion section containing a table."""
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
    botanical_name = next(
        (value for field, values in attributes.items()
         if re.search(r"scientific|botanical", field, re.I)
         for value in values),
        None,
    )
    family = next(
        (value for field, values in attributes.items() if re.search(r"family", field, re.I) for value in values),
        None,
    )
    return PlantRecord(
        source="CCRAS DRAVYA",
        source_record_id=plant_id,
        source_url=url,
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        ayurvedic_name=english_names[0] if english_names else clean_text(title.split("|")[0]),
        botanical_name=botanical_name,
        family=family,
        attributes=attributes,
        source_values=source_values,
    ).clean()


def scrape(
    database_path: str = "AyurvedicDB.db",
    max_pages: int | None = None,
    max_plants: int | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = 2,
) -> int:
    session = create_session(retries)
    translator = GoogleNameTranslator()
    try:
        plants = discover_plants(session, max_pages=max_pages)
        if max_plants is not None:
            plants = plants[:max_plants]
        database = AyurvedicAlmanac(database_path)
        database.create_database()
        inserted = 0
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task("Scraping plants", total=len(plants))
            for plant_id, url in plants:
                progress.update(task, description=f"Scraping plant {plant_id}")
                record = parse_plant(plant_id, url, fetch(session, url, timeout))
                record = enrich_record(record, translator)
                record.validate()
                database.insert_record(record)
                inserted += 1
                progress.advance(task)
        return inserted
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape CCRAS DRAVYA into SQLite.")
    parser.add_argument("--database", default="AyurvedicDB.db")
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
    args = parser.parse_args()
    try:
        print(scrape(
            args.database,
            args.max_pages,
            args.max_plants,
            args.timeout,
            args.retries,
        ))
    except KeyboardInterrupt:
        parser.exit(130, "Scrape interrupted by user.\n")


if __name__ == "__main__":
    main()
