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
scraper does not populate this table.

### `treatment`

This many-to-many join table connects herbs and illnesses through `herb_id`
and `illness_id`. Its composite primary key prevents duplicate relationships,
and foreign keys use cascading deletes.

The scraper does not infer treatment relationships from arbitrary table text.
That requires a defined illness extraction and mapping process.

### `herb_attributes`

Stores flexible fields that do not yet have dedicated normalized columns:

- `herb_id`
- `field_name`
- `value`
- `source_text`

The composite primary key prevents duplicate values for one herb and field.
`source_text` preserves the original extracted wording for review.

## Schema migration

`create_database()` is safe to call repeatedly. It creates missing tables and
adds the newer columns to the original prototype `herbs` table when needed.
It also creates a unique source-record index.

This is a lightweight migration approach suitable for the current prototype.
A formal migration tool can be introduced when schema changes become frequent.

## `insert_record()`

One record is written in a single transaction:

1. Ensure the schema exists.
2. Insert or update the herb using `(source, source_record_id)`.
3. Resolve the actual local herb ID using that natural key.
4. Delete the herb's previous attributes.
5. Insert the current cleaned attributes.
6. Commit only after all steps succeed.

If an attribute insert fails, the context manager rolls back the whole update.
This prevents partially updated records.

The local ID is queried after the upsert instead of relying on `lastrowid`.
When SQLite takes the conflict-update path, `lastrowid` is not a reliable way
to identify the existing row.

## Other methods

`insert_records()` persists an iterable of `PlantRecord` objects by delegating
to `insert_record()`.

`insert_herb()` and `insert_illness()` remain as compatibility helpers for the
original prototype. New ingestion should use `insert_record()` to retain
provenance and attributes.

## Design principle

The database stores searchable cleaned values together with source context.
This supports future normalization while keeping the dataset auditable and
rebuildable from source pages.