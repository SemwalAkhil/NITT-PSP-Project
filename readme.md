# Herbal Almanac

---

## Goal

To create a library to know about various illness and their treatments using herbs in ayurveda and vice versa

---

## Current implementation

The current MVP supports the CCRAS DRAVYA source. It discovers plant URLs,
downloads pages with retries and timeouts, parses semantic tables and the
Vernacular Names card, cleans and validates `PlantRecord` objects, and writes
them directly to SQLite.

Each vernacular language is stored as an attribute such as
`Vernacular Names.Hindi`. The first English vernacular value becomes the
primary herb name; all other language values remain available in
`herb_attributes`. Therapeutic Usage values are also normalized into illness
and treatment relationships.

The CLI can export stored record groups to JSON or CSV after ingestion. Those
exports are optional views of the database and are not an intermediate
scraping stage.

## Plan of Action

### Step 1: Data Collection

### Step 2: Database Creation

### Step 3: API Creation

### Step 4: Optimizations

---

## Design

### 1. Scrapper

Evaluate sites to understand their structures, parse source records, clean
them, validate them, and insert them directly into SQLite.

### 2. Database

Initial tables:

1. Herbs
2. Illnesses
3. Treatment (Join between herbs and illnesses)

The database operator owns schema creation, transactions, and persistence.
Cleaning and normalization are kept in a separate module so source parsing
does not become coupled to SQL.

### 3. Cleaning

### 4. Multi-Lingual API

* Fetch data from databases and present it in multiple languages
<br>
* Query in a way to be able to search incomplete or misspelled queries

The current CLI stores multilingual vernacular attributes but does not yet
provide a dedicated translation API or fuzzy-search implementation.

### 5. Look for further optimizations

---

## Execution

1. Python for backend
2. SQLite for database

---

## How to Use

The project is accessed through the Typer command-line interface. Install the
Python dependencies first:

```bash
pip install -r requirements.txt
```

Create the database schema:

```bash
python cli.py setup
```

Scrape plant records from the currently supported DRAVYA site:

```bash
python cli.py scrape dravya
```

For a smaller development run, limit the number of pages or plants:

```bash
python cli.py scrape dravya --max-pages 1 --max-plants 5
```

Search the database for herbs, illnesses, or treatments:

```bash
python cli.py herbs tulsi
python cli.py illnesses fever
python cli.py treatments HERB_ID
python cli.py attributes HERB_ID
```

View all stored records, or export a record group as JSON or CSV:

```bash
python cli.py records
python cli.py records herbs
python cli.py records attributes
python cli.py records all --format json --output records.json
python cli.py records treatments --format csv --output treatments.csv
python cli.py records attributes --format csv --output attributes.csv
```

Attributes for one herb can also be exported directly:

```bash
python cli.py attributes HERB_ID --output attributes.json
python cli.py attributes HERB_ID --format csv --output attributes.csv
```

Add individual records manually. Use the IDs printed by the herb and illness
commands when creating a treatment relationship:

```bash
python cli.py herb "Tulsi" --botanical-name "Ocimum tenuiflorum"
python cli.py illness "Cough"
python cli.py treatment HERB_ID ILLNESS_ID
```

Use a different SQLite database by passing `--database` to any command:

```bash
python cli.py setup --database /tmp/ayurvedic-test.db
python cli.py herbs tulsi --database /tmp/ayurvedic-test.db
```

Run `python cli.py --help` or `python cli.py COMMAND --help` to see all
available commands and options.

---

## Testing

Run the focused regression suite:

```bash
python -m pytest tests/test_scrapper.py -q
```

The tests currently cover section-aware table parsing, vernacular-name
extraction and primary-name selection, vernacular persistence, and treatment
link refresh behavior.
