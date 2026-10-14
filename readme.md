# Herbal Almanac

---

## Goal

To create a library to know about various illness and their treatments using herbs in ayurveda and vice versa

---

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

### 5. Look for further optimizations

---

## Execution

1. Python for backend
2. SQLite for database

---

## Testing

1. Check for searching via herbs
2. Check for searching via illness
3. Check for searching incomplete queries
4. Check for searching in another language 
