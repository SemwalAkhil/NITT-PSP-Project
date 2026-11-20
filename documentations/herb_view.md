# Herb Detail View-Model Layer (`herb_view.py`)

## 1. Purpose
The `herb_view.py` module contains pure view-model functions that prepare herb records for web presentation. It deduplicates multi-variant source claims and groups 200+ raw attributes into structured sections without modifying database records.

## 2. Where it fits
- **Upstream callers:** Called by `web_app.py` in the `/herbs/{id}` detail route and registered as Jinja template filters (`clean_family`, `format_retrieved`).
- **Downstream dependencies:** Pure standard-library module using `re`, `datetime`, and `typing`.

## 3. Key functions and classes
- `clean_family(value)`: Accepts a comma-separated family string, returns deduplicated family text (e.g. "Acanthaceae, Acanthaceae" &rarr; "Acanthaceae").
- `format_retrieved(iso_ts)`: Accepts an ISO-8601 timestamp string, returns human-readable date formatting (e.g. "19 Nov 2026").
- `dedupe_properties(properties)`: Accepts raw property claim dictionaries, returns deduplicated property records with combined `claim_count` badges (`×N`) and unique source expressions.
- `group_properties_by_domain(properties)`: Accepts property records, returns dictionary partitioned into fixed classical order (`rasa`, `guna`, `virya`, `vipaka`, `prabhava`, `karma`).
- `virya_consensus(properties)`: Accepts properties list, returns consensus summary dictionary indicating whether all sources agree or diverge.
- `dedupe_dosha_effects(effects)`: Accepts dosha effects, returns a complete 3-dosha matrix (`Vata`, `Pitta`, `Kapha`) with explicit "Not recorded" fallback.
- `group_attributes(attributes)`: Accepts raw `herb_attributes` rows, returns 8 structured sections (Vernacular Names, Parts Used, Preparations, Dose, Doshakarma, Usages, Etymology, Raw Triples) with consolidated source attribution.

## 4. Worked example
```python
from herbal_almanac.herb_view import clean_family, dedupe_properties

clean_fam = clean_family("Lamiaceae, Lamiaceae")  # "Lamiaceae"
raw_props = [
    {"domain": "rasa", "concept_code": "RASA_TIKTA", "display_label": "Bitter", "source_expression": "Tikta"},
    {"domain": "rasa", "concept_code": "RASA_TIKTA", "display_label": "Bitter", "source_expression": "तिक्त"},
]
deduped = dedupe_properties(raw_props)
print(deduped[0]["claim_count"])  # 2
```
