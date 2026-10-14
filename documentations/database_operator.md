# Database Operator

## Purpose

`database_operator.py` owns SQLite persistence for cleaned DRAVYA records. It
does not download pages or interpret HTML. Its responsibilities are connection
management, schema creation, lightweight migration, transactional persistence,
and idempotent updates.

## `AyurvedicAlmanac`

### Constructor

`AyurvedicAlmanac(database_path=None)` uses `AyurvedicDB.db` beside the module
when no path is supplied. Tests and development runs should pass a separate
path so they do not modify the project database.

### `connect()`

Every connection enables:

```sql
PRAGMA foreign_keys = ON;
```

SQLite does not enforce foreign keys by default on every new connection.
Connections return `sqlite3.Row` objects so columns can be accessed by name.

## Schema

### `herbs`

Stores the main plant identity, source name, source record ID, source URL,
botanical name, and family. The original `english_name` field is retained for
compatibility with the first prototype.

The pair `(source, source_record_id)` identifies one source record across
repeated scrapes.

### `illness`

Stores illness names for the planned herb-to-illness model. The current DRAVYA
scraper populates this table from values found in the `Therapeutic Usage`
section. `english_name` is unique so the same illness can be shared by many
herbs.

### `treatment`

This many-to-many join table connects herbs and illnesses through `herb_id`
and `illness_id`. Its composite primary key prevents duplicate relationships,
and foreign keys use cascading deletes. The scraper only creates relationships
from fields whose section contains `Therapeutic Usage`; arbitrary table text
is not treated as an illness.

### `herb_attributes`

Stores flexible fields that do not yet have dedicated normalized columns:

- `herb_id`
- `field_name`
- `value`
- `source_text`

The composite primary key prevents duplicate values for one herb and field.
`source_text` preserves the original extracted wording for review.

Vernacular names use the same flexible attribute store with field names such
as `Vernacular Names.English` and `Vernacular Names.Hindi`. English is included
in the supported language list because it is the source's primary display-name
language. The first English vernacular value is also stored in the compatibility
`herbs.english_name` column and is therefore the primary searchable plant name.
Other language values remain available through `herb_attributes` without
adding a fixed column for every language.

Translated values use the same store with `Translated Names.<Language>` field
names. They are persisted by `insert_record()` exactly like source
attributes, so JSON and CSV exports include them automatically.

## Schema migration

`create_database()` is safe to call repeatedly. It creates missing tables and
adds the newer columns to the original prototype `herbs` table when needed.
It also creates a unique source-record index and migrates legacy illness
tables. The illness migration consolidates duplicate names, redirects or
removes duplicate treatment links, and creates a unique index on
`illness(english_name)` so illness upserts have a valid conflict target.

This is a lightweight migration approach suitable for the current prototype.
A formal migration tool can be introduced when schema changes become frequent.

## `insert_record()`

One record is written in a single transaction:

1. Ensure the schema exists.
2. Insert or update the herb using `(source, source_record_id)`.
3. Resolve the actual local herb ID using that natural key.
4. Delete the herb's previous attributes.
5. Delete the herb's previous treatment links.
6. Insert the current cleaned attributes.
7. Create or reuse illnesses from `Therapeutic Usage` attributes and insert the
	current herb-to-illness links.
8. Commit only after all steps succeed.

If an attribute insert fails, the context manager rolls back the whole update.
This prevents partially updated records.

The local ID is queried after the upsert instead of relying on `lastrowid`.
When SQLite takes the conflict-update path, `lastrowid` is not a reliable way
to identify the existing row.

## Other methods

`insert_records()` persists an iterable of `PlantRecord` objects by delegating
to `insert_record()`.

`_insert_treatments_from_attributes()` selects section-qualified fields whose
names contain `Therapeutic` and `Usage`. It cleans and deduplicates their
values, inserts missing illness names, and creates the corresponding treatment
links. Since `insert_record()` deletes links first, a later scrape reflects
the source's current therapeutic usage rather than accumulating stale links.

`insert_herb()` and `insert_illness()` remain as compatibility helpers for the
original prototype. New ingestion should use `insert_record()` to retain
provenance and attributes.

## Design principle

The database stores searchable cleaned values together with source context.
This supports future normalization while keeping the dataset auditable and
rebuildable from source pages.