# Multilingual Herb Glossary (`herb_glossary.py`)

## 1. Purpose

`src/herbal_almanac/herb_glossary.py` loads the packaged `herb_names.csv` dataset and provides multilingual botanical lookup, phonetic normalization, CCRAS plant ID resolution, and vernacular search across 15 Indian and international languages.

Its main responsibilities are:

- Load and index 347 botanical and Ayurvedic herb records packaged in `src/herbal_almanac/data/herb_names.csv`.
- Provide phonetic and transliteration tolerance (`tolerant_herb_key`) to match Sanskrit and regional spelling variations.
- Resolve canonical CCRAS plant IDs (`get_plant_id`) for image hotlinking and external record linking.
- Resolve individual herbs (`resolve_herb`) by integer ID, botanical name, original Sanskrit name, English name, or vernacular names.
- Provide multilingual search (`search_herb_glossary`) to query herbs in specific Indic scripts or across all supported languages.
- Connect with `database_operator.py` so that searches in the CLI and web explorer seamlessly find database herbs when queried by vernacular names (e.g., searching "Adusa" or "Adathodai" resolves to *Adhatoda vasica* / Vasa).

## 2. Where It Fits in the Architecture

```text
                     herb_names.csv (347 herbs)
                                |
                                v
                         herb_glossary.py
                                |
           +--------------------+--------------------+
           |                    |                    |
           v                    v                    v
   database_operator.py     herb_view.py          cli.py
     (search_herbs)      (herb_image_url,     (herbs -l <lang>)
           |             vernacular_table)           |
           v                    |                    v
    FastAPI Web App             v                Terminal
  (Multilingual search)   Jinja2 Templates         Output
```

- **Database search integration:** In `database_operator.py`, `search_herbs()` queries `search_herb_glossary()` to match vernacular queries against canonical plant IDs and botanical names stored in SQLite.
- **Image URL resolution:** In `herb_view.py`, `herb_image_url()` uses `get_plant_id()` to resolve the plant's official CCRAS upload ID.
- **Vernacular table generation:** In `herb_view.py`, `herb_vernacular_table()` extracts localized regional names for presentation on the herb detail page.
- **Command-line search:** In `cli.py`, `herbal-almanac herbs --language <lang>` displays regional names for all matching herbs.
- **Audit script:** `scripts/herb_name_coverage.py` evaluates resolution percentage and regional language availability against any SQLite database.

## 3. Supported Languages

The glossary maps 15 languages across their ISO 639-1 language codes and CSV column headers:

| Code | Language | CSV Column Header |
|---|---|---|
| `en` | English | `English` |
| `hi` | Hindi | `Hindi` |
| `sa` | Sanskrit | `Sanskrit` |
| `as` | Assamese | `Assamese` |
| `bn` | Bengali | `Bengali` |
| `gu` | Gujarati | `Gujarati` |
| `kn` | Kannada | `Kannada` |
| `ml` | Malayalam | `Malayalam` |
| `mr` | Marathi | `Marathi` |
| `ne` | Nepali | `Nepali` |
| `or` | Odia | `Odia` |
| `pa` | Punjabi | `Punjabi` |
| `ta` | Tamil | `Tamil` |
| `te` | Telugu | `Telugu` |
| `ur` | Urdu | `Urdu` |

## 4. Key Functions and Classes

### `tolerant_herb_key(term: str | None) -> str`
Normalizes a botanical, classical, or vernacular herb name for tolerant matching:
1. Decomposes Unicode characters (NFKD) and strips combining diacritical marks.
2. Converts to lowercase and normalizes whitespace.
3. Collapses Sanskrit and phonetic variations:
   - `w` -> `v`
   - `sh`, `z` -> `s`
   - `cch`, `chh`, `ch` -> `c`
4. Collapses repeated doubled consonants (e.g., `tt` -> `t`, `dd` -> `d`).
5. Strips punctuation while preserving Indic Unicode script code points.

### `class ResolvedHerb`
Subclasses `dict` to encapsulate a resolved herb record with properties:
- `id`: CCRAS plant integer ID.
- `original_name`: Scraped or classical Sanskrit title.
- `botanical_name`: Binomial Latin botanical nomenclature.
- `english_name`: Common English name.
- `vernacular_names`: Dictionary mapping language column names to regional names.
- `get_name(lang: str) -> str | None`: Retrieves the localized name by language code or column name, ignoring `"N/A"` markers.
- `all_names() -> list[str]`: Returns all distinct non-empty names across all languages.

### `class HerbGlossaryStore`
In-memory indexing engine:
- `by_id`: Indexed by integer plant ID.
- `by_botanical`: Indexed by tolerant botanical name key.
- `by_original`: Indexed by tolerant classical name key.
- `by_english`: Indexed by tolerant English name key.
- `by_name_key`: Inverted index mapping every normalized vernacular name to matching `ResolvedHerb` instances.
- `get_plant_id(herb: dict[str, Any]) -> int | None`: Resolves CCRAS ID via `source_record_id`, botanical name, or transliterated names.
- `resolve_herb(query: str | int | None) -> ResolvedHerb | None`: Multi-tier resolver matching ID, exact keys, and substring tokens.
- `search_herb_glossary(query: str, language: str | None, limit: int) -> list[ResolvedHerb]`: Filters herbs by text query across all or specified languages.

### `get_herb_glossary_store() -> HerbGlossaryStore`
Cached singleton factory (`@lru_cache(maxsize=1)`) that loads `herb_names.csv` via `importlib.resources` or local filesystem fallback.

## 5. Coverage Auditor (`scripts/herb_name_coverage.py`)

The companion audit script verifies glossary coverage against any SQLite database:

```bash
python scripts/herb_name_coverage.py [database_path]
```

It reports:
1. Total database herbs and matched percentage.
2. Distinct vernacular language coverage statistics.
3. List of any unmapped herb records.
