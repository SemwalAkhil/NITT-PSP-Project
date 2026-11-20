# Web Scraper & HTML Parser (`scrapper.py`)

## 1. Purpose
The `scrapper.py` module discovers, fetches, and parses Ayurvedic plant monographs from the CCRAS DRAVYA portal. It transforms raw HTML tables and vernacular cards into clean, validated `PlantRecord` instances.

## 2. Where it fits
- **Upstream callers:** Called by the `herbal-almanac scrape` CLI command and integration test suites.
- **Downstream dependencies:** Uses `requests` and `urllib3` for HTTP retrieval with retries, `BeautifulSoup` (bs4) for DOM parsing, and `cleaning.py` for text normalization.

## 3. Key functions and classes
- `discover_plant_urls(session, base_url, max_pages=None)`: Discovers plant detail page URLs across paginated directory pages; yields URL strings.
- `fetch_plant_page(session, url)`: Downloads HTML content for a plant monograph with retry logic and bounded timeouts; returns raw HTML string.
- `parse_plant(html, url)`: Extracts botanical identity, section attributes, vernacular names, and Doshakarma text from HTML; returns a validated `PlantRecord`.
- `scrape(start_url, max_pages=None, max_plants=None, database_path=None, translate=False)`: Orchestrates the discovery, fetch, parse, and SQLite persistence workflow with terminal progress reporting.

## 4. Worked example
```python
from pathlib import Path
from herbal_almanac.scrapper import parse_plant

html_content = Path("sample.html").read_text(encoding="utf-8")
record = parse_plant(html_content, "https://example.org/plant/101")
print(record.ayurvedic_name)   # Scraped name
print(record.botanical_name)   # Botanical Latin binomial
```
