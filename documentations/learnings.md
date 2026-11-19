# Learnings

## SQLite connection context managers

A SQLite connection used as a context manager controls transactions but does not close the connection. Nest `with connection:` inside `try/finally` and close in the `finally` block to preserve commit/rollback behavior while guaranteeing cleanup on success and failure. `contextlib.closing()` alone is insufficient when transaction semantics are required.

## SQLite initialization locking

An in-memory lock protects only threads sharing the same Python object. Independent instances and processes need database-level coordination. Acquire a writer reservation with `BEGIN IMMEDIATE` before changing schema state, and keep the migration-version check, migration body, and version-row insert in the same transaction. Avoid `sqlite3.Connection.executescript()` inside an active transaction: it implicitly commits pending work. Execute trusted static DDL statements individually when the surrounding transaction must retain its writer lock. Configure a bounded busy timeout so competing initializers can wait for the lock. Use separate operation-scoped connections rather than sharing a connection across worker threads.


## Python environment

### Creating

```bash
python -m venv .venv
```

### Activating

Linux/macOS:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use a process-scoped policy change:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.venv\Scripts\Activate.ps1
```

### Deactivating

```bash
deactivate
```

### Install the package and its development tools from the repository root:

```bash
python -m pip install -e ".[dev]"
```

Translation is optional and can be installed separately:

```bash
python -m pip install -e ".[translate]"
```

## Foreign Keys in Python SQLite3

SQLite does not enforce foreign keys by default, so execute the following for
each connection:

```python
conn.execute("PRAGMA foreign_keys = ON;")
```

## Setting up git

```bash

# Run the initialization command. It is recommended to explicitly set your default branch name to main
git init -b main

# 1. Stage all files in the directory
git add .

# 2. Save the snapshot with a message
git commit -m "Initial commit"

git remote add origin <PASTE_REMOTE_REPOSITORY_URL>
git push -u origin main

# 3. Pull task before continuing further on local environment to stay up to date with repository
git pull

# 4. In case you forgot to pull and worked locally
git add .
git commit -m "Temporary commit"
git pull --rebase
git push
# This downloads the latest commit and apply fresh changes from local commit on them avoiding any merge conflicts
```

## Creating progress bar in Python

The current scraper uses Rich's `Progress` context manager in `scrape()` to
show the plant currently being processed, completion count, and estimated time
remaining. Presentation stays in the orchestration layer; the parser and
database operator do not depend on Rich.

## Using retry

The scraper creates a `requests.Session` and mounts an `HTTPAdapter` configured
with `urllib3.util.retry.Retry`.

```python
retry = Retry(
    total=3,
    backoff_factor=0.5,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=("GET",),
)
```

This retries temporary rate-limit and server failures. Read retries are
disabled because retrying a response that is already connected but slow can
make a scrape appear to hang. It does not replace timeouts or status
validation: `fetch()` uses a `(connect_timeout, read_timeout)` pair and calls
`raise_for_status()` so permanent HTTP errors remain visible.

Using one session also allows the HTTP adapter and User-Agent to be reused for
all directory and plant requests.

## `re.compile` versus `re.search`

`re.compile()` creates a reusable regular-expression pattern. The scraper
compiles the plant URL pattern once:

```python
PLANT_PATH = re.compile(r"/plant/(\d+)(?:/|$)")
```

`re.search()` then checks that pattern against each discovered link. This
extracts the numeric source record ID while avoiding false matches from
unrelated URLs.

The parser uses `re.search()` directly for field labels such as
`Scientific Name`, `Botanical Name`, and `Family`, because those expressions
are used only while inspecting the small set of fields in one page.

## Imports used by the scraper

- `requests`: HTTP sessions and responses.
- `urllib3.util.retry.Retry`: retry policy for temporary HTTP failures.
- `requests.adapters.HTTPAdapter`: attaches the retry policy to the session.
- `bs4.BeautifulSoup`: parses directory and plant HTML.
- `argparse`: exposes the scraper as a command-line program.
- `datetime`: records the UTC retrieval timestamp.
- `urllib.parse.urljoin`: converts relative plant links into absolute URLs.
- `re`: identifies plant URLs and source fields.
- `cleaning`: owns record cleanup and validation.
- `database_operator`: owns SQLite persistence.
- `translation`: optionally enriches names with `deep-translator`.

The modules are imported without performing network requests. Scraping starts
only when `scrape()` or the command-line `main()` function is called.

## `ON CONFLICT` in SQL

The `herbs` table uses `(source, source_record_id)` as the source identity.
`insert_record()` uses SQLite's upsert form:

```sql
ON CONFLICT(source, source_record_id) DO UPDATE SET ...
```

This makes repeated runs idempotent. A plant already stored from the same
source is updated rather than duplicated. The attributes for that plant are
deleted and reinserted so removed source values do not remain stale.

After the upsert, the code queries the row by its natural key instead of
trusting `lastrowid`. `lastrowid` is not a reliable way to identify the row
when the statement takes the conflict-update path.

## How text cleaning works

`clean_text()` applies Unicode NFC normalization and collapses all whitespace
to single spaces. NFC is important because it normalizes equivalent Unicode
representations without removing Devanagari characters or Sanskrit diacritics.

`clean_values()` applies `clean_text()`, removes empty values, and preserves
only the first occurrence of each value. `split_values()` additionally splits
source text on newlines, semicolons, and pipe characters.

`PlantRecord.clean()` cleans the main identity fields, attribute names,
attribute values, and preserved source text. `PlantRecord.validate()` then
checks the source ID, HTTP(S) URL, and required Ayurvedic name before the
record reaches SQLite.

The original extracted table text is retained in `source_values`. Cleaning
therefore improves queryability without losing provenance.

## Translation enrichment

`GoogleNameTranslator` caches requests by `(text, target language)`, waits at
least 0.25 seconds between new requests, and treats an individual translation
failure as missing enrichment. Source vernacular values are never replaced.
The scraper remains usable without translation network access, but translated
attributes may be incomplete.

## Direct ingestion design

The primary ingestion pipeline intentionally avoids an intermediate JSON file:

```text
HTML → PlantRecord → clean → validate → SQLite upsert
```

Raw HTML is still the source artifact, while the typed `PlantRecord` is the
in-memory boundary between parsing, cleaning, validation, and persistence.

JSON and CSV remain available as explicit CLI exports from the stored SQLite
records. They are output formats, not intermediate stages of scraping.

## Dosha normalization

Dosha expressions are normalized by parsing complete Dosha/effect groups from
left to right. This allows mixed expressions such as
`VātavardhakaPittahara` to assign Vata `increase` and Pitta `decrease`
independently. Missing Doshas remain `unspecified`; they are never inferred.
Unknown, incomplete, conflicting, or partially matched expressions are treated
as ambiguous and return `unspecified` for every Dosha. The normalized effects
are persisted in `herb_doshas`, while the original expression remains
available for review and provenance.

## Normalized schema design

The normalized Dravyaguna design separates stable herb identity from source
records and claim-level provenance. Names, parts, properties, Karma, Dosha
effects, taxonomy, and condition relationships can therefore receive evidence
from multiple sources without overwriting source expressions. Migration 1
implements only the core identity/provenance tables; the remaining domain
tables still require an additive migration and compatibility adapter.

## Schema refinement decisions

Source claims belong to source records and are attached to herbs through the
domain rows they support. Requiring a non-null claim reference on each
claim-bearing row keeps provenance explicit while allowing one claim to support
multiple normalized rows. Names and synonyms share one table with a typed
`name_type`. Relationship rows use surrogate IDs and unique indexes over
non-null identity columns because SQLite allows duplicate `NULL` values in
UNIQUE constraints. Manual corrections append claims and supersede earlier
claims instead of overwriting source data.

## Migration 1 core identity and provenance

The first normalized migration is additive and versioned. It creates source,
source-record, claim, legacy-map, and herb-name tables while leaving the
legacy application tables active. Legacy records without an external key retain
an explicit artifact reference rather than receiving an invented identifier.
The migration creates only a justified claim-backed source alias for each
existing herb name; attributes, treatment relationships, and Dosha rows are
preserved for later domain migrations.

## Migration 1 provenance hardening

Legacy source identity is validated before any normalized migration tables are
created. Non-null duplicate `(source, source_record_id)` pairs fail with the
legacy herb IDs; null IDs use explicit artifact references. Backfill keeps the
inserted source-record ID rather than reselecting by a potentially ambiguous
key. SQLite foreign keys provide existence checks, while `_validate_herb_claim`
provides the application-level subject check for herb names. Manual claims are
accepted only with an explicit `legacy_herb_id:<id>` binding.

## Migration 2 botanical taxonomy

Taxonomy backfill must preserve source expressions without inventing a complete
hierarchy. Botanical names are `unknown` rank, family values are `family` rank,
and both become non-preferred source-identification associations backed by
Migration 1 claims. Matching names on different herbs are not merged during
backfill; explicit taxonomic curation is required before concept identity is
shared.

## Harvard-Kyoto Convention

The project uses a compatibility transliteration for English-facing database
fields and search keys. `ascii_text()` first applies the explicit romanization
map, then removes Unicode combining marks and non-ASCII characters. For
example, `Kāsa` becomes `KAsa`, while the original Unicode value remains in
the source-facing fields.

This is a search/display normalization, not a claim that every Sanskrit word
has one universally correct romanization. Regional scripts and original source
values are preserved separately.

## Fuzzy match

Search values are normalized by `search_key()`: text is cleaned, case-folded,
and reduced to letters, numbers, and whitespace. `search_herbs()` and
`search_illnesses()` compare that key with `difflib.SequenceMatcher` and reject
weak matches below the `0.65` score threshold. Exact matches therefore rank
first, while small spelling or transliteration differences remain searchable.
Illnesses also use a canonical key that folds ASCII transliteration variants
and known aliases such as `fever` and `jvara`.

## pyproject.toml

`pyproject.toml` is the packaging and build source of truth. It defines the
`herbal-almanac` distribution, the `src/` package directory, the
`herbal-almanac` console entry point, and Python 3.10 or newer support. Core
dependencies cover scraping, persistence, and CLI operation. The `dev` extra
adds pytest, build, Twine, and translation support; the `translate` extra adds
only `deep-translator`.

The standard release checks are:

```bash
python -m pytest -q
python -m build
python -m twine check dist/*
```

## Automated tests

Tests import `herbal_almanac` through the configured `src` path and use saved
HTML strings, fake sessions, temporary SQLite files, and fake translators.
They do not contact DRAVYA or Google. The suite currently covers parser
sections, malformed HTML, retries and failures, database migrations, search,
CLI exports, and translation caching. CI installs `.[dev]` and runs the suite
on Python 3.10 through 3.14.
## Orchestration modules

`cli.py` is the user-facing orchestration layer. It validates Typer arguments,
selects the database path, calls `scrape()` or database operations, formats
tables and exports, and converts expected failures into exit code 1. It does
not contain HTML parsing or SQL schema logic.

`scrapper.py` orchestrates HTTP discovery, parsing, optional translation,
validation, retries, progress output, and database insertion. `cleaning.py`
and `database_operator.py` remain usable independently as library modules.

## Responses 429, 500, 502, 503, 504

The scraper retries these temporary HTTP statuses through `urllib3.Retry`.
The default policy allows two connection and status retries with exponential
backoff, while read retries remain disabled. Requests use a five-second
connect timeout and a configurable fifteen-second read timeout. A final HTTP
failure remains visible to the per-plant failure report instead of silently
creating an incomplete record.
## DRAVYA page structure and extracted data

The directory page contains links matching `/plant/` followed by a numeric ID.
Each plant page may contain a title, a scientific-profile card, a Vernacular
Names card, and accordion tables. The parser extracts:

- the Ayurvedic name from the title when written as `English - Ayurvedic`;
- scientific and family names from the profile card or table attributes;
- section-qualified table fields such as `Parts Used.Name`;
- language-qualified values such as `Vernacular Names.Hindi`;
- the source URL, numeric record ID, and UTC retrieval timestamp.

Section qualification prevents repeated headers such as `Name` from colliding
across unrelated tables. Therapeutic Usage values are later normalized into
unverified illness and treatment records.
## _function_name convention

Names beginning with one underscore are implementation helpers rather than
stable public API. The scraper uses this convention for parsing stages such as
`_discover_plants()`, `_table_attributes()`, and `_scientific_profile()`.
Public entry points include `discover_plants()`, `parse_plant()`, `scrape()`,
`PlantRecord`, and `AyurvedicAlmanac`. Tests may exercise private helpers when
that gives precise coverage of parser behavior, but application code should
prefer the public functions.

## Release validation status

The source distribution and wheel build successfully and pass `twine check`.
The clean wheel smoke test verifies library imports, the installed CLI, and a
user-selected database path without the optional translation dependency. The
TestPyPI upload is still pending valid TestPyPI credentials after a rejected
upload, so no public package release has been made.

## assert keyword
The `assert` keyword in Python is a debugging aid that tests a condition as a internal sanity check. If the condition evaluates to `True`, the program carries on running normally. If the condition evaluates to `False`, Python immediately crashes the program and raises an AssertionError

## Versioned additive schema migrations

A migration ledger makes schema upgrades repeatable, but a ledger row must
describe work that actually committed. Apply each migration body and its
version record in the same transaction. Validate legacy natural keys before
backfill and fail with an actionable error when the old data is ambiguous;
do not silently choose one duplicate. When introducing normalized tables in
stages, explicitly document which tables are active application storage and
which are only additive migration targets.

## Claim provenance and subject validation

Foreign keys can establish that a claim and a herb both exist, but they cannot
prove that the source record behind a claim belongs to that herb. Validate
that association in the application before creating a claim-backed name row.
Manual curation should also retain an explicit source/artifact binding so its
origin is auditable.

## Conservative botanical taxonomy migration

Legacy botanical-name text does not prove an accepted taxon, authorship, or
parent-child relationship. Backfill botanical names at `unknown` rank and
family values at `family` rank, preserve the original fields, and avoid
inferring hierarchy or synonym relationships without evidence.

## Web interface as a separate application layer

Keep the browser interface separate from the scraper and database
implementation. FastAPI routes should orchestrate existing domain/read methods;
Jinja2 should render the results. Add only narrowly scoped database read
helpers when the existing API cannot provide an efficient page model. Keep
runtime database selection explicit and test routes against temporary SQLite
files. A first read-only milestone avoids mixing request/response handling
with long-running scraping or write operations.

## Static assets in a Python web package

A Starlette/FastAPI static mount serves files from the directory supplied at
application construction time. Keep templates and static assets inside the
installable package and declare them as package data so wheels include them.
A route-level test should request the CSS URL, assert HTTP 200 and
`text/css`, and inspect a representative rule; a passing HTML route alone
does not prove the stylesheet is available. Version static asset URLs when
browser caching can otherwise conceal a newly deployed stylesheet.

## Application CRUD and presentation queries

Centralizing manual curation (`add_herb`, `add_illness`, `add_treatment`) and
presentation queries (`dashboard_summary`, `get_herb`, `treatment_details`) within
`AyurvedicAlmanac` ensures that both the CLI and the FastAPI web GUI share identical
validation, transactional boundaries, and relevance ranking without duplicating
SQL queries across entry points. Presentation layers remain thin and query-agnostic.

## Operational provenance and claim supersession

Connecting scraping pipelines to claim-level provenance requires separating assertion
extraction from destructive overwrites. When a web page or source document is re-ingested:
1. Active claims that match the current source text are reused idempotently without churn.
2. When single-value fields (such as primary Ayurvedic name, botanical identity, or family) change at the source, earlier assertions are marked `superseded` (`verification_status = 'superseded'`) and new claims record `supersedes_claim_id`, retaining an immutable history of revisions.
3. Multi-value attributes (vernacular names, section attributes, Dosha expressions) record separate claims per value, preserving the exact source wording, normalized value, and detected ISO 15924 scripts.
4. Domain relationships (`herb_names`, `herb_taxa`) validate that a claim's source record belongs to the target entity before creating an association, preventing cross-record data corruption.
5. Ingestion transactions commit legacy tables, normalized tables, and provenance claims atomically, ensuring rollback on failure leaves zero orphaned claims.

## Stage C semantic Dravyaguna integrity and verification

Moving from lexical string attributes to a normalized semantic ontology requires strict integrity guarantees:
1. **Multilingual label verification safeguards:** Prevent unreviewed or machine-generated translations from masquerading as verified botanical/clinical facts. Enforce via SQLite triggers that a label cannot attain `verified` status unless it originated from human curation or classical lexicons, possesses a non-empty authority citation in `concept_label_sources`, and records the verified curator's identity and timestamp. Protect the last verified citation from deletion or blanking while the parent label remains verified.
2. **Snapshot integrity in source reconciliation:** Ingestion pipelines capturing complete snapshots must guarantee transactional completeness. Check constraints and triggers on `source_reconciliation_events` ensure that incomplete or failed extraction runs (`extraction_status != 'completed'`) cannot have `is_complete_snapshot = 1`.
3. **Cross-entity mapping contamination:** Enforce provenance boundaries across relational joins. A concept mapping derived from one source claim cannot be attached to an herb derived from a different source record. Triggers comparing the herb's `source_record_id` with the mapping's claim `source_record_id` eliminate cross-herb data contamination at the database layer.
4. **Nullable composite uniqueness via partial unique indexes:** Standard SQL and SQLite treat `NULL` values as distinct in composite unique constraints (`UNIQUE(a, b, nullable_c)`), permitting accidental duplicate records when `nullable_c IS NULL`. Enforce strict uniqueness for unspecified attributes by pairing the table unique constraint with a partial unique index (`CREATE UNIQUE INDEX ... ON table(a, b) WHERE nullable_c IS NULL`). This preserves multi-part specificity while prohibiting duplicate unspecified relationships.
5. **Source-claim assertion immutability:** In-place modification of original assertion text (`source_expression`, `claim_type`, `source_field`, `language_code`) corrupts historical mapping provenance. SQLite triggers must freeze these core assertion-defining fields once a claim is referenced by domain mappings or assertions, while permitting review status updates and supersession workflows.
6. **Transactional migration version checks and write-lock serialization:** To eliminate Time-of-Check to Time-of-Use (TOCTOU) concurrency race conditions between competing migration runners, migrations must acquire an immediate write lock (`BEGIN IMMEDIATE;`) before reading `MAX(version)` from `schema_migrations`. Testing this invariant requires distinguishing three distinct concurrency scenarios: (a) genuine write-lock contention across competing connections where a second connection is locked out under a bounded busy timeout; (b) sequential stale-version prerequisite rejection after another transaction has committed; and (c) multi-threaded concurrent lock serialization synchronized via deterministic thread events without arbitrary sleeps.
7. **Dual-layer visibility and Dosha assertion supersession synchronization:** In Stage C, database trigger `trg_cascade_claim_supersession` cascades status updates on `source_claims` only to `concept_claim_mappings`. To maintain status parity across all semantic layers without mutating Stage C.1 DDL, the application ingestion pipeline must explicitly synchronize dependent `dosha_claim_assertions.verification_status` in the same transaction. Furthermore, reporting views filter presence (`source_presence_status = 'active'`), while the repository query layer must additionally gate on review status (`verification_status NOT IN ('superseded', 'rejected')`) to prevent superseded or rejected clinical assertions from appearing as active medical facts.
8. **Decoupled concept, claim, and label verification lifecycles with migration ledger validation:** In classical pharmacology and semantic knowledge graphs, abstract concept ontology lifecycles (`dravyaguna_concepts.status`: `active`, `provisional`, `deprecated`) must remain strictly isolated from lexical representation statuses (`concept_labels.verification_status`: `unreviewed`, `reviewed`, `verified`, `disputed`, `rejected`) and claim/mapping assertion statuses (`verification_status`: `unreviewed`, `reviewed`, `verified`, `rejected`, `superseded`). Routine claim pipelines strictly enforce forward transitions, rejecting rollbacks and terminal revisions, whereas exceptional administrative interventions (downgrades, terminal reopenings) must route through an explicit adjudication pathway (`adjudicate_claim_status_override()`). Crucially, verified status cannot be attained merely by supplying a reviewer ID; any transition to `verified` strictly mandates an explicit authority citation (treatise, pharmacopoeia monograph). Furthermore, the adjudication helper documents the authenticated actor for provenance and audit logging, but the caller service layer remains strictly responsible for authenticating the actor and verifying administrative authorization before execution. Capability gating must validate the exact migration ledger sequence (`[1, 2]` for v2, `[1, 2, 3]` for v3) rather than a coarse maximum version check, preventing premature execution on corrupt or future-versioned databases.
9. **Trigger execution ordering, application-level schema invariants, and active profile filtering:** In relational semantic architectures, database triggers may enforce coarse integrity boundaries that require precise application-level orchestration:
   - *Cascading trigger hazards:* SQLite trigger `trg_cascade_claim_supersession` blindly overwrites all child mappings when a parent source claim becomes superseded or rejected. To prevent destroying independently terminal child provenance (e.g. an independently rejected mapping being forced to superseded), the application transaction must pre-capture child states before updating the parent and explicitly restore independently terminal children post-trigger. Furthermore, child mappings and Dosha assertions must be tagged with a deterministic lineage annotation (`[INHERITED_FROM_CLAIM:{source_claim_id}:PRIOR={prior_status}]`) upon cascading transition so that if a parent claim is subsequently reopened via administrative adjudication, the reopening algorithm selectively reopens only inheriting children while leaving independently terminal children untouched.
   - *Audit scoping boundaries:* When audit tables (`source_reconciliation_events`) are scoped at the source level without direct claim or herb foreign keys, granular entity traceability and child transition lineage must be embedded within structured event notes (`[CLAIM_ID: ...]`, `[HERB_ID: ...]`), recognizing that append-only immutability is maintained as an application-level contract rather than a database-enforced constraint.
   - *Section completeness vs source completeness:* Source-level complete snapshots authorize omission detection only for specific sections that were actually present, successfully parsed, and reliably mapped to target relationship tables.
   - *Disputed mapping filtering in active profiles:* Semantic repository queries for active herb Dravyaguna profiles must explicitly filter out disputed mappings (`AND (:include_disputed = 1 OR m.mapping_type != 'disputed')`) while projecting a derived `is_disputed` boolean indicator, ensuring provisional or disputed interpretations do not taint active clinical profiles by default.
   - *Classical textual variants in ontology curation:* Classical Ayurvedic texts exhibit minor taxonomic variations across samhitās (e.g. the 8th *virya* in *Ashta-Virya* enumerated as *Mridu* in Charaka/Sushruta vs *Manda* in Vagbhata/Bhavaprakasha). Ontology architecture must accommodate such canonical variants via domain placement guidelines and curator sign-off before seeding canonical concept records.
10. **Canonical concept ontology seeding, multilingual label representations, and single-preferred-label invariant:** In domain ontology initialization:
    - *Namespace prefix validation & enum whitelisting:* Enforcing uppercase regex patterns (`^[A-Z]+_[A-Z0-9_]+$`), strict domain-to-prefix mappings, and DDL enum whitelisting prevents accidental cross-domain or malformed entity creation before database writes.
    - *Single-preferred-label invariant & normalized label uniqueness:* Enforcing that at most one label per `(concept_id, language_code, script_code)` has `is_preferred = 1` and that normalized labels are unique within each concept guarantees 1:1 parity between seed definitions and SQLite rows, eliminating duplicate label divergence across presentation layers.
    - *Trigger-compatible seeder lifecycle:* Because Stage C triggers prohibit direct insertion of labels with `verification_status = 'verified'`, catalog seeders must initialize all labels as `unreviewed` with NULL verification metadata, attaching authoritative treatise citations in `concept_label_sources` for subsequent curator promotion.
    - *Quarantine of provisional and deprecated concepts:* Extended potency models (such as *Ashta-Virya* potencies beyond *Dvividha-Virya*) seeded as `provisional` are cataloged for scholarly concordance but quarantined from default active profile resolution and binary reconciliation queries. In contrast, `deprecated` concepts are strictly quarantined unconditionally even when provisional access is requested.
    - *Display label fallback transparency:* When all candidate labels for an active concept are disputed or rejected, resolution helpers must fall back to returning `concept_code` with `display_label_status = 'unreviewed'` and `is_fallback = True`, ensuring clinical presentation layers maintain transparency rather than failing silently.
    - *Caller transaction preservation via savepoints:* Seeders operating against SQLite connections must utilize nested `SAVEPOINT` blocks rather than connection context managers (`with conn:`), ensuring that caller-managed outer transactions (`BEGIN IMMEDIATE`) are neither committed prematurely nor contaminated upon rollback.
11. **Deterministic migration ledger validation and capability gating:**
    - *Full-sequence ledger inspection:* Relying on `MAX(version)` is inadequate for capability gating because it fails to detect sequence gaps (e.g. `[1, 3]`), missing baseline tables, duplicate entries, or unsupported future versions.
    - *Deterministic capability gating:* By comparing the exact ordered list of migration versions against canonical baselines (`[1, 2]` for v2, `[1, 2, 3]` for v3), the application cleanly distinguishes between normal operation on an older baseline (failing fast with `FeatureUnavailableError` when semantic features are invoked) and database corruption or unsupported schema states (failing fast with `MigrationError`).
    - *Isolation of baseline database:* Verifying that default initialization (`create_database()`) consistently yields `[1, 2]` ensures that migration 3 remains an explicit, isolated opt-in upgrade path until production deployment is formally authorized.
12. **Claim lifecycle management, dual-pathway transition enforcement, trigger-order hazard defense, and section-level omission detection:**
    - *Dual-pathway transition architecture:* Separating routine ingestion/curation (`transition_claim_status`) from administrative intervention (`adjudicate_claim_status_override`). Routine pipelines enforce forward progression and block curator rollbacks/reopenings with clear error messages directing callers to adjudication, while administrative adjudication enforces caller-side authentication, minimum justification length, explicit citations on verification, and mandatory audit logging in `source_reconciliation_events`.
    - *Defense against cascading trigger destruction (`trg_cascade_claim_supersession`):* SQLite trigger `trg_cascade_claim_supersession` blindly overwrites all child mappings when a parent source claim becomes superseded or rejected. Pre-capturing child mappings and Dosha assertions before parent updates, restoring independently terminal children post-trigger, and applying deterministic lineage tags (`[INHERITED_FROM_CLAIM:{claim_id}:PRIOR={status}]`) prevents the trigger from destroying independent terminal statuses and enables selective reopening.
    - *Selective reopening contract:* When an administrator reopens a terminal parent claim, independently terminal children (those without `[INHERITED_FROM_CLAIM:...]` tags) remain strictly terminal (`rejected`/`superseded`), while inheriting children are selectively resynchronized (restoring to `unreviewed` or `reviewed`, and never automatically regaining `verified` status without explicit child re-verification).
    - *Parent constraint and lineage tagging in child interpretation review:* Child interpretations (`concept_claim_mappings`, `dosha_claim_assertions`) cannot be promoted to `reviewed` or `verified` if the parent claim is `unreviewed`, `rejected`, or `superseded`. Transitioning an inheriting child independently to a terminal status strips its inherited lineage tag to establish independent terminal provenance.
    - *Calibrated mapping confidence discipline:* Exact lexical mappings (`lexicon_exact`) must strictly retain `mapping_confidence = None` to avoid projecting false quantitative precision, while probabilistic methods must validate confidence within `[0.0, 1.0]`.
    - *Section-level omission detection with completeness gating:* Omission detection requires both a completed source snapshot (`is_complete_snapshot = 1` and `extraction_status = 'completed'`) and explicit presence of the parsed section domain (`parsed_sections[section_domain] is True`), preventing partial or failed scrapes from erroneously flagging unattested attributes as omissions.
13. **Semantic backfill engine, cryptographic table invariance, and calibrated mapping generation:**
    - *Cryptographic legacy table invariance:* Migrating relational knowledge graphs with active clinical/historical data requires mathematically proving that legacy application tables remain pristine. Capturing pre- and post-migration snapshots (schema columns, data types, exact row counts, and ordered SHA-256 row hashes) across all 13 Stage B legacy tables guarantees zero unintended mutations or data loss during ontology backfill.
    - *No synthetic claims & provenance preservation:* Backfilled concept mappings must strictly reference genuine, pre-existing `source_claims` records. Creating synthetic or unanchored claims during backfill corrupts historical auditability.
    - *Calibrated mapping discipline during backfill:* Automated ruleset backfill must always assign `mapping_method = 'lexicon_exact'`, `mapping_confidence = NULL`, and `verification_status = 'unreviewed'`. Exact lexical matches must not be assigned artificial numeric probabilities (e.g. 1.0), maintaining strict epistemic conservatism.
    - *Compound Doshakarma decomposition:* Compound multi-dosha expressions (such as *KaphaVatahara* or *Tridoshahara*) must be deterministically decomposed into discrete directional effect assertions (`EFFECT_DECREASE` / `EFFECT_INCREASE`) for each target Dosha concept (`DOSHA_VATA`, `DOSHA_PITTA`, `DOSHA_KAPHA`), eliminating compound ambiguity in downstream clinical queries.
    - *Savepoint-isolated failure rollback safety:* Wrapping backfill execution in nested SQLite savepoints (`SAVEPOINT wp4_backfill;`) ensures that unexpected constraint violations or data anomalies immediately rollback Stage C inserts while preserving the outer transaction and guaranteeing Stage B database integrity.
    - *True semantic backfill idempotency:* Designing backfill insertion queries to check for existing `(source_claim_id, concept_id)` and relationship keys ensures that re-running the backfill process multiple times executes with zero additional insertions, zero duplicate mappings, and zero data drift.
14. **Repository API, presentation services, and multi-tier reconciliation executor contracts:**
    - *Multi-concept active-status quarantine & localized profile aggregation:* In normalized multi-concept relationships (such as Dravyaguna properties combining a primary property concept and an optional plant part concept, or preparations combining a dosage form and plant part), presentation queries (`herb_dravyaguna_profile`) must enforce that all referenced concepts are active (`c.status = 'active'` and `c_part.status = 'active'`). Concepts flagged as `provisional` are quarantined from default profiles and only exposed when explicit research flags (`include_provisional=True`) are enabled.
    - *Disputed mapping policy and derived visibility:* Relational mapping quality (`mapping_type = 'disputed'`) reflects unresolved clinical or pharmacological dissent. Public profiles strictly omit disputed mappings by default (`include_disputed=False`), while audit and curation callers project a derived boolean attribute (`is_disputed = True`) without requiring an un-normalized column in the schema.
    - *Read-only preservation of accepted Stage C.1 SQL artifacts:* When accepted SQL files (such as `stage_c_review/virya_reconciliation.sql`) are finalized as authoritative milestone deliverables, higher-level services must consume them verbatim rather than altering their text. Herb-scoped reconciliation (`reconcile_herb_virya`) wraps the global accepted queries in outer subquery filters (`SELECT * FROM (<query>) AS q WHERE q.herb_1_id = ? OR q.herb_2_id = ?`), ensuring 100% SQL text fidelity.
    - *Executor contract active concept filtering across reconciliation tiers:* Because the accepted SQL queries in `virya_reconciliation.sql` omit `c.status = 'active'` from their inner joins, the Python application executor contract assumes responsibility for querying active concept codes (`SELECT concept_code FROM dravyaguna_concepts WHERE status = 'active'`) and actively pruning any divergence row referencing non-active (`provisional` or `deprecated`) concepts before calculating summary counts and returning `ViryaReconciliationReport`.
    - *Deterministic 4-tier summary count reconciliation:* Virya divergence reports structure evidence across mutually exclusive tiers (Tier 1 unreviewed candidate divergence, Tier 2 reviewed candidate divergence, Tier 3 verified source disagreement) alongside Query 4 same-claim intra-source ambiguity, guaranteeing exact arithmetic consistency (`total_reconciled_pairs = tier_1 + tier_2 + tier_3 + same_claim_ambiguity`) and transparent audit provenance.
15. **Version-aware web presentation, capability degradation banners, and FastAPI template extension:**
    - *Dynamic capability detection:* Rather than maintaining static environment flags or separate application builds for different database schema states, the web application dynamically interrogates the active SQLite database schema capability via `get_database_capability(almanac)` on each request. When operating on Schema Version 2, the web application renders standard legacy profiles while displaying an informative capability degradation banner (`"Stage C Semantic Dravyaguna features require Schema Version 3"`). When running against Schema Version 3, the application dynamically unlocks full Dravyaguna property cards (Rasa, Guna, Virya, Vipaka, Prabhava, Karma), plant part associations, Sanskrit lexical references (Devanagari script & IAST transliteration), and Virya reconciliation summary pills.
    - *Template directory chaining & inheritance:* By configuring Jinja2 with an ordered multi-directory search path (`directory=[str(STAGE_C_TEMPLATE_DIR), str(PACKAGE_TEMPLATE_DIR)]`), review and extension packages can host specialized templates (`herb_detail_semantic.html`, `virya_reconciliation.html`) that inherit seamlessly from base layout templates (`base.html`) and share static CSS stylesheets (`styles.css`) without mutating, copying, or diverging from production package templates.
    - *HTTP 501 capability gating for API & GUI routes:* REST JSON endpoints (`/api/stage-c/herbs/{herb_id}/profile`, `/api/stage-c/herbs/{herb_id}/reconciliation`) and specialized GUI views (`/stage-c/reconciliation/{herb_id}`) enforce strict capability gating. When requested against a Schema Version 2 database, these routes immediately reject the call with HTTP 501 Not Implemented and a structured JSON diagnostic payload (`{"error": "Stage C semantic features require Schema Version 3", "current_version": 2, "required_version": 3}`), ensuring programmatic clients receive clear, non-corrupting error states.
    - *Transparent FastAPI route override:* In modular FastAPI architectures where enhanced presentation layers extend legacy applications, removing legacy route handlers from `app.router.routes` (`[r for r in app.router.routes if getattr(r, "name", None) != "herb_detail"]`) before registering version-aware endpoints (`/herbs/{herb_id}`) ensures deterministic request routing without handler conflicts, duplicate route warnings, or unpredictable resolution order.
16. **Production package promotion, serialized upgrade workflows, and cryptographic invariance verification in CLI tooling:**
    - *Explicit target authorization for database schema mutations:* In production-grade pharmacology systems, migrations that alter schema capabilities (such as upgrading from Schema Version 2 to Version 3) must never run silently or against unconfirmed defaults. Enforcing mandatory `--database` arguments and interactive confirmation (bypassable only via an explicit `--yes` flag) ensures database operators cannot accidentally mutate production databases.
    - *Multi-stage upgrade orchestration:* Decoupling schema DDL execution (`upgrade_to_stage_c()`) from semantic data ingestion (`run_stage_c_backfill()`) allows fine-grained auditability, while high-level CLI commands (`upgrade-stage-c`) orchestrate the full pipeline (DDL application, canonical catalog seeding, ruleset-based semantic backfill, and cryptographic Stage B row invariance verification) in sequential, savepoint-isolated transactions.
    - *Dual-snapshot row invariance verification:* Verifying that legacy application tables remain 100% unaltered requires capturing a comprehensive schema and SHA-256 data snapshot immediately prior to mutation and comparing it against a fresh snapshot captured immediately post-mutation before committing, mathematically proving zero data loss or unintentional mutation across legacy rows.
    - *Test suite promotion and module namespace isolation:* When promoting verified staging modules from an isolated review directory into a production package namespace (`src/herbal_almanac/`), mirroring test suites into the official test runner (`tests/`) guarantees continuous CI/CD coverage while verifying that all package-internal relative imports, SQL resource resolution paths, and CLI entry points operate correctly in installed environments.
17. **Hermetic session-scoped test fixtures for uncommitted SQLite artifacts:**
    - *Decoupling CI test runs from uncommitted local databases:* In open-source and collaborative Python packages where database files (`*.db`) are gitignored and forbidden from being committed, test suites that depend on pre-scraped local databases fail immediately in fresh CI environments.
    - *Synthesizing realistic offline baselines:* By creating a session-scoped fixture (`hermetic_v2_db_path` in `tests/conftest.py`) that initializes a pristine Schema Version 2 database via `AyurvedicAlmanac.create_database()` and populates it through `parse_plant()` and `insert_record()` using repository HTML fixtures (`sample.html`), tests acquire a realistic, fully populated database with genuine claims, attributes, and relationships without live network calls.
    - *Skip-guarding developer environment safeguards:* Local integrity tests that verify an author's development database remains unmutated are valuable safeguards during development. Marking these tests with `pytest.skip` when the local database file is absent preserves local protection while guaranteeing 100% green builds in clean CI runner environments.
18. **Packaging non-Python assets (SQL scripts, templates, static files) in standard wheels:**
    - *Explicit package-data inclusion:* When runtime modules depend on non-Python assets (such as SQL DDL files, migration scripts, Jinja2 HTML templates, or CSS stylesheets), these files must be explicitly declared in `pyproject.toml` under `[tool.setuptools.package-data]`. Omitting them results in source installations succeeding while built binary wheels (`.whl`) silently omit the files, causing unexpected `FileNotFoundError` exceptions in downstream environments.
    - *Canonical path resolution:* Resolving asset paths relative to the locating module's directory (`Path(__file__).resolve().parent / "migrations" / "virya_reconciliation.sql"`) rather than relying on current working directories (`cwd`) or fragile relative traversal ensures reliable asset discovery across editable developer installations, standalone wheel installations, and virtual environments.
19. **Continuous integration packaging smoke testing:**
    - *Distinguishing editable test runs from wheel consumers:* Running unit tests with `pip install -e .[dev]` tests the Python source tree with all development tools, but fails to detect missing non-Python package data, broken wheel installation metadata, or malformed console script entry points.
    - *Independent package-smoke CI jobs:* Incorporating an isolated CI job that executes `python -m build`, installs the resulting wheel artifact into an unadorned environment without editable links, and executes smoke suites (`smoke_installed_package.py`) and CLI entry points (`herbal-almanac --help`) guarantees that binary distribution packages distributed to users are completely functional.
20. **Post-promotion repository hygiene and de-duplication:**
    - *Staging artifact retirement:* Once staging review packages (such as `stage_c_review/`) are formally accepted and their components are promoted into the canonical package namespace (`src/herbal_almanac/`) and official test runner (`tests/`), all duplicate code, SQL, and test files must be deleted from staging to avoid code drift, duplicate test executions, and stale imports.
    - *Preservation of architectural decision records:* Design review directories are retained as documentation archives housing only accepted ADRs, coverage reports, and technical manuals.
    - *Clean relative imports over fallback imports:* Inside promoted package modules, fragile runtime import fallbacks (`try: from .xxx import ... except ImportError: from xxx import ...`) and `sys.path` injections should be replaced with direct, canonical intra-package relative imports (`from .xxx import yyy`), guaranteeing consistent module resolution and static type analyzer correctness.
    - *Git hygiene for distribution artifacts:* Generated build directories (`build/`, `dist/`, `*.egg-info/`) must never be committed to source control and must be untracked (`git rm -r --cached`) and ignored in `.gitignore`.
21. **Formal milestone gate verification protocol:**
    - *Multi-dimensional milestone readiness:* Closing a database-driven semantic architecture gate requires auditing across five orthogonal vectors: (1) schema and constraint alignment across DDL, triggers, and service code; (2) legacy database preservation and cryptographic row invariance; (3) epistemic and multilingual representation fidelity; (4) complete test runner and CI matrix parity; and (5) adherence to non-clinical domain boundaries (no medical recommendations, no symptom matching).
    - *Distinguishing active production baseline from supported capabilities:* In phased database migrations, establishing an explicit, user-authorized upgrade path allows a repository to achieve complete milestone capability readiness without mutating existing production databases prior to operator sign-off.
22. **Multi-source evidence architecture and epistemic deduplication:**
    - *The false corroboration hazard:* Repeating secondary or tertiary claims across multiple internet sources creates artificial epistemic consensus unless claims are anchored to their primary publication, treatise, or monograph.
    - *Canonical persistent identifiers and mirror tagging:* Using normalized persistent identifiers (`doi`, `pmid`) alongside text shingling detects derivative sources, enabling the ingestion pipeline to record multiple citations while preventing duplicate evidence weighting.
    - *Strict segregation of traditional and biomedical models:* Scientific pharmacology findings must be recorded as distinct, evidence-anchored claims without mutating, replacing, or retrofitting classical Ayurvedic concepts.
23. **Automated packaging asset verification and AST skip-guard enforcement:**
    - *Wheel asset inspection testing:* Unit tests can dynamically execute `build --wheel --no-isolation` into a temporary directory and inspect the wheel archive's internal ZIP manifest (`zipfile.ZipFile.namelist()`), verifying that every SQL migration file, HTML template, and CSS stylesheet is bundled prior to distribution.
    - *Static AST skip-guard enforcement:* By parsing all test modules via `ast.parse` and inspecting functions referencing uncommitted databases (`data/inspection.db`), tests can programmatically fail if any developer introduces an unguarded query or test that assumes the local database exists, protecting against CI breaks before code merges.
24. **AST-based guard discrimination vs naive substring searching:**
    - *Avoiding false positives in static test guards:* Naive string search (e.g. searching raw file text for `"inspection.db"`) fails when a test's name, docstring, or explanatory comments mention the artifact while the executable code uses a hermetic synthetic fixture. By using `ast.parse`, explicitly excluding the docstring node (`node.body[0]`), and collecting string constants from executable AST nodes only, static analysis guards avoid false positives while strictly catching un-guarded runtime references in executable expressions.
25. **Multi-tier packaging verification: core vs optional extras:**
    - *Distinguishing core installability from extras:* Packages with optional presentation layers (such as FastAPI/Jinja2 under `[web]`) must ensure the core engine functions cleanly without optional dependencies. Testing the built wheel in an environment installed with only core dependencies proves that non-web workflows (data operations, DDL upgrades, CLI commands) never inadvertently import optional packages at the root module level.
    - *Explicit extras installation in CI smoke jobs:* Smoke tests targeting presentation layers (`smoke_installed_package.py`) must install the wheel specifying the required extra (`python -m pip install "dist/*.whl[web]"`) to avoid `ModuleNotFoundError` during CI package verification.
26. **Explicit build dependencies in development extras for PEP 517 non-isolated builds:**
    - *Default environment omissions in Python 3.12+:* Python 3.12 and newer standard library virtual environments no longer include `setuptools` or `wheel` by default. When tests execute `python -m build --no-isolation` to test wheel generation offline without network access to PyPI, the build backend (`setuptools.build_meta`) fails with `ModuleNotFoundError: No module named 'setuptools'` unless `setuptools>=68` and `wheel` are explicitly declared in `[project.optional-dependencies] dev`.
    - *Non-short-circuiting CI matrices:* Configuring `fail-fast: false` on GitHub Actions test matrix runners prevents a failure on one Python version from aborting the remaining matrix jobs, ensuring complete diagnostics across Python 3.10 through 3.14.
27. **Pre-push verification protocol and disciplined commit boundaries:**
    - *Eliminating false green declarations:* Declaring CI check failures resolved without local verification against the exact failure modes (e.g. testing with `build`, inspecting wheel archives, smoke-testing clean virtual environments with and without extras) risks repeated broken builds.
    - *Deterministic pre-push checklist:* Formalizing a 6-step checklist in developer guidelines (`agents.md`)—covering mandatory scraper regression, full test suite pass, wheel build, multi-tier clean venv smoke installation, git status artifact checks, and strict commit truthfulness—ensures all contributors and agents verify package health before pushing to remotes.
28. **Deterministic offline demo database synthesis and multi-milestone evaluation workflows:**
    - *Bridging uncommitted database policies and evaluation needs:* In projects enforcing strict 'no committed databases' policies, prospective evaluators, instructors, and CI runners require a turnkey, zero-network mechanism to generate a rich database containing multi-milestone artifacts (scraped records, manual curations, schema upgrades, seeded concept ontologies, and backfilled semantic profiles).
    - *End-to-end orchestration scripts:* Providing an explicit script (`scripts/make_demo_db.py`) that chains baseline schema creation (`create_database`), offline HTML parsing (`parse_plant`), record upsert (`insert_record`), manual entity creation (`add_illness`, `add_treatment`), Stage C migration (`upgrade_to_stage_c`), and ruleset backfill (`run_stage_c_backfill`) outputs a deterministic SQLite artifact to a gitignored location (`data/demo.db`) and prints ready-to-run server commands, enabling instant multi-layer evaluation without external dependencies.
29. **Starlette `url_for` query parameter constraints and multi-page pagination test fixtures:**
    - *Starlette URL generation contract:* Starlette's `url_for()` only matches and interpolates declared path template parameters (e.g. `{herb_id}`). Passing unexpected keyword arguments for query parameters (e.g. `url_for('herb_list', q=query, page=page+1)`) raises `starlette.routing.NoMatchFound` (HTTP 500) rather than appending them as a query string. Query strings must be built explicitly via query-string formatting or Jinja's `urlencode` filter (e.g. `{{ url_for('herb_list') }}?{{ {'q': query, 'page': page+1}|urlencode }}`).
    - *Multi-page fixture testing discipline:* Pagination logic cannot be verified with minimal fixtures of 1–2 records. Regression test suites for paginated views must construct fixtures that span across multiple pages (e.g. 35+ records with `PAGE_SIZE=12`) to exercise forward/backward pagination links, search query preservation across pages, and out-of-range page clamping.
30. **Condition-first botanical exploration and clinical attribution boundaries:**
    - *Bidirectional knowledge exploration:* Users often query botanical repositories from the condition perspective rather than plant names. Implementing `illness_summaries()` and `herbs_for_illness()` enables bidirectional discovery (browsing diseases to find candidate herbs) using existing `search_illnesses()` ranking with `ILLNESS_ALIASES` (e.g. mapping colloquial "fever" to classical "jvara") and treatment aggregations without altering normalized database schemas.
    - *Preserving provenance and epistemic safety in UI presentation:* When presenting disease-herb relationships, presentation layers must explicitly distinguish between scraped associations (`link_source = 'scraped'`) and verified manual links (`link_source = 'manual'`), while rendering prominent medical disclaimers to prevent users from mistaking scraped research associations for clinical guidance.
31. **Display-only transliteration normalization without database mutation:**
    - *Harvard-Kyoto / ITRANS capitalization artifacts:* Classical Ayurvedic terms scraped from botanical sources like CCRAS DRAVYA often feature internal capital letters denoting phonetic distinctions (e.g. `KAsa` for cough, `AgnimAndya` for impaired digestion, `khAlityam/khalati` for alopecia). Storing these verbatim preserves provenance and transliteration fidelity.
    - *Presentation-layer filtering:* To provide human-readable typography in web views without altering underlying SQLite data, a presentation filter (`format_readable_illness` / Jinja `readable_illness`) splits compound words and slashes, applying title casing (`Kasa`, `Agnimandya`, `Khalityam/Khalati`). This decouples textual presentation from canonical database storage.













