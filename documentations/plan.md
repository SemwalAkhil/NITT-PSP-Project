# Dravyaguna Data Mapping Project — SDLC Plan

## 1. Project Overview

### Goal

Build an open-source Python library and SQL database that maps Ayurvedic pharmacology (**Dravyaguna**) to:

- Ayurvedic/Sanskrit drug names
- Accepted botanical identities
- Sanskrit synonyms and vernacular/trade names
- Parts used
- Rasa, Guna, Virya, Vipaka
- Karma
- Doshakarma / Dosha effects
- Ayurvedic therapeutic indications
- Standardized disease terminology and clinical mappings
- Source provenance and evidence

### Core Principle

The project must preserve a strict separation between:

```text
SOURCE DATA
    ↓
RAW DATA
    ↓
PARSED DATA
    ↓
NORMALIZED DATA
    ↓
VALIDATED DATA
    ↓
SQL DATABASE
    ↓
PYTHON LIBRARY API
```

Never overwrite the original source terminology during normalization.

Example:

```text
Source:
    KaphaVātahara

Normalized:
    Kapha → decrease
    Vata  → decrease
    Pitta → unspecified
```

The original `KaphaVātahara` must remain stored alongside the normalized values.

---

# 2. Scope

## 2.1 MVP Scope

The first release should focus on the CCRAS DRAVYA dataset.

### MVP data

- Ayurvedic name
- Scientific/botanical name
- Botanical family
- Vernacular names
- Sanskrit synonyms
- Parts used
- Rasa
- Guna
- Virya
- Vipaka
- Karma
- Doshakarma
- Therapeutic Usage
- Source URL
- Source record ID
- Retrieval timestamp

### MVP output

```text
DRAVYA
  ↓
Scraper
  ↓
Raw JSON
  ↓
Validation
  ↓
SQLite
  ↓
Python API
```

---

## 2.2 Post-MVP Scope

### Phase 2

- Ayurvedic Pharmacopoeia of India (API) PDF extraction
- Pharmacopoeial identity/metadata validation

### Phase 3

- NAMASTE terminology import
- Ayurvedic condition normalization
- English clinical terminology mapping

### Phase 4

- POWO/IPNI botanical taxonomy resolution
- Botanical synonym/deduplication

### Phase 5

- e-Charak/NMPB trade-name enrichment

### Phase 6

- IMPPAT research/phytochemical enrichment, subject to licensing

### Phase 7

- Public Python package
- CLI
- Automated testing
- CI/CD
- Versioned database releases

---

# 3. Authoritative Source Strategy

| Data | Primary Source | Secondary Source |
|---|---|---|
| Ayurvedic identity | DRAVYA | Classical texts/e-Nighantu |
| Botanical identity | API/PCIM&H | POWO/IPNI |
| Sanskrit synonyms | DRAVYA | e-Nighantu/classical texts |
| Rasa/Guna/Virya/Vipaka | DRAVYA | Classical texts |
| Karma | DRAVYA | Classical texts |
| Doshakarma | DRAVYA | Classical texts |
| Therapeutic Usage | DRAVYA | NAMASTE/classical texts |
| Disease terminology | NAMASTE | WHO |
| Trade/common names | e-Charak/NMPB | FRLHT database |
| Taxonomic accepted status | POWO/IPNI | API |
| Research/phytochemicals | IMPPAT | Primary research |

### Licensing rule

Public accessibility does **not** automatically mean unrestricted redistribution.

Every source must be reviewed for:

- access conditions
- scraping restrictions
- redistribution rights
- license
- attribution requirements
- commercial-use restrictions

Store source-license metadata in the project.

---

# 4. SDLC Phases

# Phase 1 — Requirements Analysis

## Objectives

Define exactly what the system must do before scraping.

## Tasks

- [ ] Define project goals
- [ ] Define MVP
- [ ] Define users
- [ ] Define supported sources
- [ ] Define output database
- [ ] Define Python API expectations
- [ ] Define provenance requirements
- [ ] Define normalization rules
- [ ] Define licensing constraints

## Deliverables

```text
docs/
├── requirements.md
└── source-policy.md
```

## Definition of Done

Requirements are written and every target data field has a proposed source.

---

# Phase 2 — Feasibility Study

## Objectives

Verify that each source can technically and legally support the planned extraction.

## Tasks

### DRAVYA

- [ ] Test plant directory
- [ ] Test plant detail page
- [ ] Inspect HTML
- [ ] Inspect page IDs/URLs
- [ ] Inspect publicly exposed JSON/IIIF-related resources
- [ ] Determine stable extraction selectors
- [ ] Check robots.txt/terms

### API

- [ ] Identify available volumes
- [ ] Collect legal/public PDF sources
- [ ] Test text extraction
- [ ] Test monograph boundaries
- [ ] Test scientific-name extraction

### NAMASTE

- [ ] Locate official Excel resources
- [ ] Inspect workbook structure
- [ ] Test import with pandas/openpyxl

### e-Charak

- [ ] Inspect medicinal-plant list
- [ ] Determine trade-name extraction method
- [ ] Check reuse restrictions

### POWO/IPNI

- [ ] Determine taxonomy lookup strategy
- [ ] Determine accepted-name/synonym resolution method

### IMPPAT

- [ ] Confirm available public interfaces
- [ ] Review database license
- [ ] Determine whether data can be redistributed

## Deliverable

```text
docs/source-feasibility.md
```

---

# Phase 3 — System Architecture

## Objectives

Design the whole ETL system before implementing individual sources.

## Architecture

```text
                ┌───────────────┐
                │    DRAVYA     │
                └───────┬───────┘
                        │
                ┌───────▼───────┐
                │ DRAVYA CRAWLER│
                └───────┬───────┘
                        │
                        ▼
                    RAW DATA
                        │
       ┌────────────────┼─────────────────┐
       │                │                 │
       ▼                ▼                 ▼
    API PDF         NAMASTE XLSX      e-Charak
    Parser            Importer         Parser
       │                │                 │
       └────────────────┼─────────────────┘
                        ▼
                  NORMALIZATION
              ┌────────┼─────────┐
              ▼        ▼         ▼
           Taxonomy  Dosha    Conditions
              │        │         │
              └────────┼─────────┘
                       ▼
                   VALIDATION
                       │
                       ▼
                  SQL DATABASE
                       │
                       ▼
                 PYTHON LIBRARY
```

## Deliverables

```text
docs/architecture.md
docs/data-flow.md
```

---

# Phase 4 — Database Design

## Objectives

Create the relational model before the full scraping pipeline.

## Initial tables

```text
herbs
herb_names
herb_synonyms
herb_parts
herb_properties
herb_karma
herb_doshas
conditions
herb_conditions
taxonomy
sources
source_records
scrape_runs
scrape_errors
```

## Core `herbs` concept

Suggested fields:

```text
herb_id
ayurvedic_name
sanskrit_name_devanagari
botanical_name_source
accepted_botanical_name
botanical_author
family
taxon_id
```

## Core `herb_doshas` concept

```text
herb_id
dosha
effect
classical_expression
source_id
confidence
```

Allowed normalized effect values:

```text
increase
decrease
neutral
unspecified
```

Do not force `balance` when the source only expresses pacification or aggravation.

## Core `herb_conditions`

```text
herb_id
condition_id
source_term
mapping_type
confidence
```

## `sources`

```text
source_id
publisher
title
volume
page
url
retrieved_at
license
```

## Deliverables

```text
database/
├── models.py
├── connection.py
└── repository.py
```

---

# Phase 5 — DRAVYA Crawler

## Objective

Discover all plant records and their URLs.

## Strategy

Use the public plant directory:

```text
/all_plants?page=1
/all_plants?page=2
...
```

Do not hard-code the final page count.

Stop when a page produces no new plant records.

## Tasks

- [ ] Implement HTTP client
- [ ] Implement pagination
- [ ] Extract plant IDs
- [ ] Extract plant names
- [ ] Extract plant URLs
- [ ] Save discovery index
- [ ] Deduplicate URLs
- [ ] Log failures

## Output

```text
data/
└── dravya/
    └── index.json
```

Example:

```json
{
  "source_id": 374,
  "name": "Withania somnifera",
  "url": "https://dravya.ccras.org.in/plant/374/withania-somnifera"
}
```

## Definition of Done

The crawler can discover all currently available plant records without manually entering URLs.

---

# Phase 6 — DRAVYA Downloader + Cache

## Objective

Download source pages once and reuse local copies during development.

## Tasks

- [ ] HTTP timeout handling
- [ ] Retry handling
- [ ] User-Agent
- [ ] Rate limiting
- [ ] Response status validation
- [ ] Local HTML caching
- [ ] Retrieval timestamps
- [ ] Error logging

## Directory

```text
data/raw/dravya/
├── 374.html
├── 375.html
└── ...
```

## Important

Do not repeatedly download unchanged pages while developing the parser.

---

# Phase 7 — DRAVYA Parser

## Objective

Convert individual plant pages into structured source records.

## Extract

```text
Identity
Scientific Profile
Vernacular Names
Sanskrit Synonyms
Parts Used
Mahakashaya
Varga
Skandha
Rasa
Guna
Virya
Vipaka
Karma
Doshakarma
Therapeutic Usage
Pharmacopoeial Status
```

## Parsing rule

Do not rely on:

```python
tables[7]
```

Use semantic section detection:

```text
Heading
   ↓
Associated content/table
```

## Raw output

```text
data/raw/dravya/
├── 374.json
├── 375.json
└── ...
```

## Definition of Done

A selected test set of plants can be parsed successfully with section-level output.

---

# Phase 8 — Raw Data Schema

## Objective

Create a stable source representation independent of SQL.

Example:

```json
{
  "source": "DRAVYA",
  "source_record_id": 374,
  "source_url": "...",
  "retrieved_at": "...",

  "identity": {
    "ayurvedic_name": "...",
    "scientific_name": "...",
    "family": "..."
  },

  "vernacular_names": [],
  "synonyms": [],
  "parts_used": [],

  "classifications": {
    "gana": [],
    "mahakashaya": [],
    "varga": [],
    "skandha": []
  },

  "properties": {
    "rasa": [],
    "guna": [],
    "virya": [],
    "vipaka": []
  },

  "karma": [],
  "doshakarma": [],
  "therapeutic_usage": []
}
```

---

# Phase 9 — Validation Framework

## Objective

Detect extraction problems before inserting records into the database.

## Checks

### Required

- [ ] Source record ID
- [ ] Source URL
- [ ] Retrieval timestamp
- [ ] Ayurvedic name
- [ ] Scientific name, where source provides it

### Structural

- [ ] Correct field types
- [ ] Expected lists/tables present
- [ ] No duplicate source records
- [ ] No malformed URLs

### Quality

- [ ] Unexpected empty fields
- [ ] Broken Unicode/diacritics
- [ ] Duplicate botanical names
- [ ] Duplicate plant IDs

## Output

```text
reports/
├── validation.json
└── validation.csv
```

---

# Phase 10 — SQLite Database Import

## Objective

Load validated source records into SQL.

## Pipeline

```text
Raw JSON
   ↓
Pydantic validation
   ↓
Normalization
   ↓
SQLAlchemy
   ↓
SQLite
```

## Initial database

```text
data/ayurveda.db
```

## Definition of Done

A clean local SQLite database can be rebuilt entirely from raw source records.

---

# Phase 11 — Dosha Normalization

## Objective

Convert classical Doshakarma expressions to structured values while preserving the source expression.

## Example

```text
Source:
    KaphaVātahara

Normalized:
    Kapha → decrease
    Vata  → decrease
    Pitta → unspecified
```

## Rule categories

### Pacification/decrease

```text
Vātahara
Vātaghna
Vātaśamana
Pittahara
Pittaghna
Pittaśamana
Kaphahara
Kaphaghna
Kaphashamana
```

### Increase

```text
Vātavardhaka
Vātavṛddhi
Pittavardhaka
Pittavṛddhi
Kaphavardhaka
Kaphavṛddhi
```

### Multi-Dosha expressions

Support expressions such as:

```text
KaphaVātahara
Tridoṣahara
Tridoṣaśamana
```

## Important rule

Never infer a missing Dosha.

If only Vata/Kapha pacification is documented:

```text
Vata      = decrease
Kapha     = decrease
Pitta     = unspecified
```

## Tests

Create unit tests for all supported keyword families.

---

# Phase 12 — API PDF Pipeline

## Objective

Use the Ayurvedic Pharmacopoeia of India to validate pharmacopoeial identity.

## Steps

```text
API PDF
  ↓
pdfplumber
  ↓
Raw text
  ↓
Monograph detection
  ↓
Field extraction
  ↓
Validation
  ↓
Raw JSON
```

## Initial fields

Start with:

- Monograph name
- Botanical name
- Family
- Part used
- API volume
- Page
- Pharmacopoeial metadata

## Do not start with OCR

Prefer machine-readable/searchable PDFs.

Use OCR only when necessary and only after confirming that normal text extraction is insufficient.

---

# Phase 13 — Botanical Taxonomy Resolution

## Objective

Prevent duplicate herbs caused by botanical synonyms.

## Strategy

```text
DRAVYA botanical name
        +
API botanical name
        ↓
IPNI / POWO
        ↓
Accepted taxon
        ↓
Internal taxon_id
```

## Preserve

```text
source botanical name
accepted botanical name
historical synonym
author citation
taxon ID
taxonomy source
```

## Example

```text
Physalis somnifera L.
        ↓
Withania somnifera (L.) Dunal
```

Both may resolve to the same accepted taxon.

## Important

Do not make the raw botanical string the primary key.

---

# Phase 14 — NAMASTE Import

## Objective

Use official standardized Ayurvedic terminology for condition normalization.

## Steps

```text
NAMASTE XLSX
    ↓
pandas/openpyxl
    ↓
condition table
```

## Store

- Term ID
- Parent ID
- Code
- Word
- Short definition
- Long definition
- Reference
- NAMASTE group

## Useful groups

```text
SAT-C → disorders/diagnosis
SAT-D → signs/symptoms
SAT-E → morbidity codes
```

---

# Phase 15 — Clinical Condition Crosswalk

## Objective

Map Ayurvedic disease terminology to modern clinical labels without overwriting the Ayurvedic term.

## Architecture

```text
Ayurvedic term
      ↓
NAMASTE standardized term
      ↓
English clinical concept
      ↓
Optional ICD terminology
```

## Example

```text
Kāsa
  ↓
NAMASTE
  ↓
Cough
```

Do not automatically equate:

```text
Kāsa = COPD
```

unless a source explicitly establishes that mapping.

## Mapping metadata

Store:

```text
mapping_type
source
confidence
clinical_domain
ICD code
```

---

# Phase 16 — e-Charak/NMPB Enrichment

## Objective

Cross-reference:

- Trade names
- Common names
- Plant parts
- Market/raw-drug terminology

## Strategy

Join against canonical herb/taxon records.

Do not create duplicate herbs when only the trade name differs.

---

# Phase 17 — IMPPAT Enrichment

## Objective

Optionally add research-oriented data such as:

- phytochemicals
- therapeutic-use associations
- plant-part/phytochemical relationships

## Constraints

Before redistribution:

- [ ] Review license
- [ ] Review permitted use
- [ ] Review commercial restrictions
- [ ] Separate restricted source data from open project code where required

Do not assume a public database interface means the whole database may be copied into the repository.

---

# Phase 18 — Deduplication

## Duplicate dimensions

Check duplicates using:

```text
source ID
botanical name
accepted taxon ID
normalized Ayurvedic name
synonym relationships
```

## Candidate workflow

```text
Potential duplicate
      ↓
Compare botanical taxon
      ↓
Compare Ayurvedic identity
      ↓
Compare source references
      ↓
Automatic merge OR manual review
```

---

# Phase 19 — Provenance System

Every source-derived relationship should retain:

```text
source
source_record_id
source_url
source_term
volume
page
retrieved_at
license
confidence
```

Example:

```json
{
  "herb": "Withania somnifera",
  "dosha": "Vata",
  "effect": "decrease",
  "classical_expression": "KaphaVātahara",
  "source": "CCRAS DRAVYA",
  "source_url": "...",
  "confidence": "high"
}
```

This makes the dataset auditable.

---

# Phase 20 — Python Library API

## Goal

Provide an easy developer-facing interface.

Example:

```python
from dravyaguna import Dravyaguna

db = Dravyaguna("ayurveda.db")

herb = db.herb("Ashwagandha")

print(herb.botanical_name)
print(herb.rasa)
print(herb.guna)
print(herb.virya)
print(herb.vipaka)
print(herb.karma)
print(herb.dosha_effects)
print(herb.therapeutic_usage)
```

## Query API

```python
db.search("Ashwagandha")
db.by_botanical_name("Withania somnifera")
db.by_dosha("Vata", effect="decrease")
db.by_condition("Kasa")
```

---

# Phase 21 — CLI

Provide commands such as:

```bash
dravyaguna scrape dravya
dravyaguna scrape api
dravyaguna import namaste
dravyaguna normalize
dravyaguna validate
dravyaguna build-db
dravyaguna update
```

The `update` command should eventually run the complete pipeline safely.

---

# Phase 22 — Testing

## Unit tests

Test:

- [ ] URL discovery
- [ ] HTML parsing
- [ ] Table parsing
- [ ] PDF extraction
- [ ] Dosha normalization
- [ ] Taxonomy normalization
- [ ] Condition mapping

## Integration tests

Test:

```text
DRAVYA → parser → raw JSON → database
API → parser → raw JSON → database
NAMASTE → importer → database
```

## Data tests

Check:

- [ ] Duplicate IDs
- [ ] Duplicate canonical taxa
- [ ] Invalid Dosha values
- [ ] Missing sources
- [ ] Broken mappings
- [ ] Empty required values

## Regression tests

Maintain a fixed set of test pages/records so parser changes can be compared against expected output.

---

# Phase 23 — Data Quality Reporting

Generate a report similar to:

```text
Total source records:       338
Botanical names:            334
Missing botanical names:      4

Rasa available:             320
Guna available:             319
Virya available:            330
Vipaka available:           328

Doshakarma available:       301
Therapeutic Usage:          315

Potential duplicates:         7
Manual review required:       9
```

This should become a release artifact.

---

# Phase 24 — Documentation

Create:

```text
docs/
├── requirements.md
├── architecture.md
├── data-model.md
├── sources.md
├── extraction.md
├── normalization.md
├── taxonomy.md
├── conditions.md
├── licensing.md
└── contributing.md
```

Document each database field:

```text
Field
Source
Extraction method
Normalization method
Allowed values
Example
License/provenance
```

---

# Phase 25 — Project Packaging

Recommended layout:

```text
project/
├── src/
│   └── dravyaguna/
│       ├── __init__.py
│       ├── client.py
│       ├── models.py
│       ├── queries.py
│       └── database.py
│
├── scrapers/
│   ├── dravya/
│   ├── api/
│   ├── namaste/
│   └── echarak/
│
├── normalization/
├── database/
├── data/
├── tests/
├── docs/
├── reports/
├── pyproject.toml
├── README.md
└── LICENSE
```

---

# Phase 26 — CI/CD

Use GitHub Actions.

Pipeline:

```text
push / pull request
       ↓
lint
       ↓
unit tests
       ↓
integration tests
       ↓
build package
       ↓
release artifact
```

Recommended tools:

```text
pytest
ruff
mypy (optional)
build
twine / trusted publishing
```

---

# Phase 27 — Versioning

Recommended release roadmap:

```text
v0.1.0
DRAVYA MVP

v0.2.0
API integration

v0.3.0
NAMASTE integration

v0.4.0
Botanical taxonomy normalization

v0.5.0
e-Charak enrichment

v0.6.0
Clinical crosswalk

v1.0.0
Stable integrated release
```

Database releases should also carry a version.

---

# Phase 28 — Maintenance

The project is a continuously maintained data pipeline.

Update flow:

```text
Source changes
      ↓
New scrape
      ↓
Compare to previous version
      ↓
Validation
      ↓
Review changed records
      ↓
Database rebuild
      ↓
Version bump
      ↓
Release
```

Every record/release should preserve:

```text
data_version
parser_version
retrieved_at
source_version
```

---

# 5. Recommended Repository Structure

```text
dravyaguna/
│
├── src/
│   └── dravyaguna/
│       ├── __init__.py
│       ├── client.py
│       ├── models.py
│       ├── queries.py
│       └── database.py
│
├── scrapers/
│   ├── common/
│   │   ├── http.py
│   │   ├── cache.py
│   │   └── logging.py
│   │
│   ├── dravya/
│   │   ├── crawler.py
│   │   ├── parser.py
│   │   └── models.py
│   │
│   ├── api/
│   │   ├── pdf_loader.py
│   │   ├── monograph_detector.py
│   │   ├── parser.py
│   │   └── validator.py
│   │
│   ├── namaste/
│   │   ├── downloader.py
│   │   ├── loader.py
│   │   └── parser.py
│   │
│   └── echarak/
│       ├── crawler.py
│       └── parser.py
│
├── normalization/
│   ├── botanical.py
│   ├── dosha.py
│   ├── conditions.py
│   └── names.py
│
├── database/
│   ├── models.py
│   ├── connection.py
│   └── repository.py
│
├── data/
│   ├── raw/
│   │   ├── dravya/
│   │   ├── api/
│   │   └── namaste/
│   ├── normalized/
│   └── ayurveda.db
│
├── tests/
│
├── reports/
│
├── docs/
│
├── .github/
│   └── workflows/
│
├── pyproject.toml
├── README.md
└── LICENSE
```

---

# 6. Recommended Technology Stack

## Core

```text
Python 3.12+
requests / httpx
BeautifulSoup4
lxml
pdfplumber
pandas
openpyxl
SQLAlchemy
Pydantic
tenacity
pytest
```

## Optional

```text
Playwright
PostgreSQL
Alembic
Polars
Ruff
Mypy
```

## Development Database

```text
SQLite
```

## Production/large deployment

```text
PostgreSQL
```

---

# 7. Development Order

Follow this order instead of implementing all sources simultaneously.

```text
1. Requirements
2. Source feasibility
3. Architecture
4. Database schema
5. DRAVYA URL discovery
6. DRAVYA downloader/cache
7. DRAVYA parser
8. Raw JSON format
9. Validation
10. SQLite import
11. Dosha normalization
12. API PDF parser
13. Botanical taxonomy resolver
14. NAMASTE importer
15. Condition crosswalk
16. e-Charak enrichment
17. IMPPAT enrichment
18. Deduplication
19. Python API
20. CLI
21. Testing
22. Documentation
23. CI/CD
24. Release
25. Maintenance
```

---

# 8. MVP Definition of Done

The MVP is complete when all of the following are true:

- [ ] DRAVYA records can be discovered automatically
- [ ] Pages can be downloaded with retries and caching
- [ ] Raw HTML is stored
- [ ] DRAVYA sections are parsed
- [ ] Raw JSON is generated
- [ ] Validation runs automatically
- [ ] SQLite database can be rebuilt
- [ ] Doshakarma normalization is deterministic
- [ ] Original source terminology is preserved
- [ ] Provenance is stored
- [ ] Python library can query herbs
- [ ] Tests pass
- [ ] Documentation explains extraction and normalization
- [ ] Licensing/provenance information is documented

---

# 9. First 10 Implementation Tickets

## TICKET-001
Create project repository and Python environment.

## TICKET-002
Create `docs/requirements.md`.

## TICKET-003
Create database ER diagram and SQLAlchemy models.

## TICKET-004
Build reusable HTTP client with retry, timeout and caching.

## TICKET-005
Build DRAVYA plant-directory crawler.

## TICKET-006
Build DRAVYA detail-page downloader.

## TICKET-007
Build DRAVYA section parser.

## TICKET-008
Create raw JSON schema and validation models.

## TICKET-009
Build SQLite import pipeline.

## TICKET-010
Implement Dosha normalization rules and unit tests.

---

# 10. Immediate Next Step

The first coding milestone should be:

```text
M1:
DRAVYA discovery
      +
DRAVYA downloader
      +
DRAVYA parser
      +
raw JSON
```

Do not start with API OCR, clinical translation, or IMPPAT integration.

Once the DRAVYA pipeline is reliable, use the same architecture to add API, NAMASTE, taxonomy and e-Charak as independent source adapters.

---

# 11. Long-Term Target Architecture

```text
                    AUTHORITATIVE SOURCES
                           │
       ┌───────────────────┼────────────────────┐
       │                   │                    │
     DRAVYA               API                NAMASTE
       │                   │                    │
       ▼                   ▼                    ▼
    HTML parser         PDF parser          XLSX importer
       │                   │                    │
       └───────────────────┼────────────────────┘
                           ▼
                       RAW DATA
                           │
                           ▼
                    NORMALIZATION
              ┌────────────┼─────────────┐
              │            │             │
              ▼            ▼             ▼
           TAXONOMY      DOSHA       CONDITIONS
              │            │             │
              ▼            ▼             ▼
           POWO/IPNI      RULES        NAMASTE/WHO
              │            │             │
              └────────────┼─────────────┘
                           ▼
                       VALIDATION
                           │
                           ▼
                      SQL DATABASE
                           │
                 ┌─────────┴─────────┐
                 ▼                   ▼
             Python API             CLI
                 │                   │
                 └─────────┬─────────┘
                           ▼
                       Open Source
                         Library
```

## Guiding principles

1. **Source-first:** preserve authoritative source data.
2. **Deterministic:** normalization rules should be reproducible.
3. **Provenance-aware:** every important relationship should be traceable.
4. **Taxonomy-aware:** botanical synonyms must not create duplicate herbs.
5. **No forced inference:** missing values remain unspecified.
6. **Modular:** every source is an independent adapter.
7. **Rebuildable:** the SQL database should be reproducible from source artifacts.
8. **License-aware:** source availability and redistribution rights are tracked separately.
9. **Testable:** parsers and normalization rules require regression tests.
10. **Versioned:** source data, parser versions and database releases should be identifiable.
