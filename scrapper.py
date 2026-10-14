from __future__ import annotations

import argparse
from datetime import datetime, timezone
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from cleaning import PlantRecord, clean_text, split_values
from database_operator import AyurvedicAlmanac


DRAVYA_DIRECTORY = "https://dravya.ccras.org.in/all_plants"
PLANT_PATH = re.compile(r"/plant/(\d+)(?:/|$)")
DEFAULT_TIMEOUT = 15.0


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


def _table_attributes(soup: BeautifulSoup) -> tuple[dict[str, list[str]], dict[str, str]]:
    attributes: dict[str, list[str]] = {}
    source_values: dict[str, str] = {}
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
            cells = [cell for cell in cells if cell]
            if len(cells) < 2:
                continue
            field = cells[0].rstrip(":")
            values = split_values(" ".join(cells[1:]))
            if field and values:
                attributes.setdefault(field, []).extend(values)
                source_values[field] = " | ".join(cells[1:])
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
        ayurvedic_name=clean_text(title.split("|")[0]),
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
    try:
        plants = discover_plants(session, max_pages=max_pages)
        if max_plants is not None:
            plants = plants[:max_plants]
        database = AyurvedicAlmanac(database_path)
        database.create_database()
        inserted = 0
        for plant_id, url in plants:
            record = parse_plant(plant_id, url, fetch(session, url, timeout))
            record.validate()
            database.insert_record(record)
            inserted += 1
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
