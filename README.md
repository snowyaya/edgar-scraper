# EDGAR Intelligence — SEC Filing AI Scraping Pipeline

A production-minded pipeline that crawls SEC EDGAR, extracts and cleans financial filings, enriches them with AI-relevant signals, and serves the corpus via a REST API and browser UI.

---

## Why SEC EDGAR

EDGAR (Electronic Data Gathering, Analysis, and Retrieval) is the SEC's public filing database — freely accessible, explicitly allows programmatic access, and contains high-value financial documents (10-K, 10-Q, 8-K) that are ideal for AI workflows:

- **Structured content**: Mandatory section structure (Item 1A, Item 7, Item 8) enables section-targeted RAG without re-chunking at query time
- **Rich provenance**: Every document has a stable accession number, CIK, filing date, and period
- **Scale**: 35+ million filings going back to 1993 across every public US company
- **Quality signal**: SEC filings are professionally written, legally reviewed, and consistently formatted — far higher signal-to-noise than web scrapes

Instead of following HTML links (fragile, maintenance-heavy), this pipeline uses EDGAR's structured JSON API (`data.sec.gov/submissions/`) as its navigation source — a deliberate choice that makes the crawler resilient to site layout changes.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Compose                           │
│                                                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │    db    │    │   api    │    │ scraper  │    │    ui    │  │
│  │ Postgres │◄───│ FastAPI  │    │  Python  │    │  React   │  │
│  │    16    │    │ port 8000│    │   CLI    │    │  Nginx   │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
│                       ▲               │               │         │
│                       │               ▼               │         │
│                       └─────── PostgreSQL ◄───────────┘         │
└─────────────────────────────────────────────────────────────────┘

Scraper pipeline (per document):
  crawler.py → parser.py → transformer.py → writer.py
  (fetch)       (parse)      (enrich)         (store)
```

**Four services:**
- **`db`** — PostgreSQL 16 with 5 tables, GIN full-text indexes, array indexes on tags
- **`api`** — FastAPI with async SQLAlchemy, 15+ endpoints across 3 routers
- **`scraper`** — One-shot async crawler triggered via CLI or `POST /api/runs`
- **`ui`** — React + Vite + Recharts, served by Nginx which also reverse-proxies `/api`

---

## Quick Start

### Prerequisites

- Docker + Docker Compose v2

### 1. Clone and configure

```bash
git clone https://github.com/snowyaya/edgar-scraper.git

# Edit .env — the only required change is SEC_USER_AGENT
cp .env
nano .env
```

**Required:** Set your real name and email in `.env`:
```
SEC_USER_AGENT="YourName@email.com"
```
The SEC uses this to identify your scraper. Requests without a valid User-Agent may be rate-limited.

### 2. Start infrastructure

```bash
docker compose up db api ui -d
```

Wait ~10 seconds for Postgres to initialise and Alembic migrations to run. Check readiness:

```bash
curl http://localhost:8000/health/db
# → {"status":"ok","db":"connected"}
```

The UI is now available at **http://localhost** (port 80).

### 3. Run your first scrape

**Option A — CLI:**
```bash
# Run with multiple companies
docker compose run --rm scraper python -m scraper.main \
  --ciks GOOGL 0001045810 \
  --output output/*.jsonl \
  --max-filings 50

# Check the JSONL output
ls output/
head -n1 output/*.jsonl | python3 -m json.tool
```

**Option B — API:**
```bash
curl -X POST http://localhost:8000/api/runs \
  -H "Content-Type: application/json" \
  -d '{"ciks": ["0000320193"], "filing_types": ["10-K"], "max_filings": 50}'
```

**Option C — UI:** Open http://localhost → Runs → "New Run" button 
> Note: enter tickers or CIK numbers (e.g. `0000320193`) in the `tickers or CIKS` field until ticker resolution is fixed.

### 4. Browse results

- **UI**: http://localhost — Overview, Documents, Analytics, Export pages
- **API docs**: http://localhost:8000/docs — Swagger UI with all endpoints
- **JSONL export**: http://localhost:8000/api/export (streams full corpus)

---

## CLI Reference

```bash
docker compose run --rm scraper python -m scraper.main [OPTIONS]
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--tickers TICKER [...]` | Ticker symbols to scrape (e.g. `AAPL AMZN MSFT`) | — |
| `--ciks CIK [...]` | SEC CIK numbers, alternative to `--tickers` | — |
| `--filing-types TYPE [...]` | Form types to collect (see below) | `10-K` |
| `--max-filings N` | Max filings per company | `10` |
| `--date-from YYYY-MM-DD` | Only include filings on or after this date | — |
| `--date-to YYYY-MM-DD` | Only include filings on or before this date | — |
| `--output PATH` | Write results to a JSONL file at this path | — |
| `--run-id UUID` | Resume or tag an existing crawl run | — |
| `--log-level LEVEL` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` | `INFO` |

`--tickers` and `--ciks` are mutually exclusive; one is required.

### Supported Filing Types

| Form | Type | Who files it |
|------|------|--------------|
| `10-K` | Annual report | US domestic companies |
| `10-Q` | Quarterly report | US domestic companies |
| `8-K` | Current report (material events) | US domestic companies |
| `DEF 14A` | Proxy statement | US domestic companies |
| `20-F` | Annual report | Foreign private issuers |
| `6-K` | Current report | Foreign private issuers |
| `40-F` | Annual report | Canadian issuers |

> **Note:** Foreign private issuers (e.g. JD.com, Alibaba, Nintendo) file `20-F` and `6-K`
> instead of `10-K` and `8-K`. Passing domestic form types for these companies will return
> zero results.

### Examples

```bash
# Apple's last 5 annual reports
docker compose run --rm scraper python -m scraper.main \
  --tickers AAPL \
  --filing-types 10-K \
  --max-filings 5

# Five companies, two filing types, filtered by date range
docker compose run --rm scraper python -m scraper.main \
  --tickers AAPL AMZN MSFT GOOGL META \
  --filing-types 10-K 10-Q \
  --max-filings 20 \
  --date-from 2020-01-01 \
  --date-to 2023-12-31 \
  --output output/faang.jsonl

# Using CIKs directly (useful for companies without tickers)
docker compose run --rm scraper python -m scraper.main \
  --ciks 0000320193 0001018724 \
  --filing-types 10-K

# Foreign private issuer (must use 20-F / 6-K, not 10-K / 8-K)
docker compose run --rm scraper python -m scraper.main \
  --tickers BABA JD \
  --filing-types 20-F 6-K \
  --max-filings 10

# Recent earnings releases across multiple companies
docker compose run --rm scraper python -m scraper.main \
  --tickers MSFT GOOGL AAPL \
  --filing-types 8-K \
  --max-filings 5 \
  --date-from 2024-01-01 \
  --output output/earnings.jsonl
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/documents` | Paginated document list with 8+ filters |
| `GET` | `/api/documents/{id}` | Full document detail + sections |
| `GET` | `/api/documents/{id}/sections` | Sections only — RAG chunking endpoint |
| `GET` | `/api/export` | Stream filtered corpus as JSONL |
| `GET` | `/api/runs` | List crawl runs |
| `GET` | `/api/runs/{id}` | Run detail with config |
| `POST` | `/api/runs` | Trigger new crawl (async) |
| `GET` | `/api/runs/{id}/errors` | Per-run error log |
| `GET` | `/api/analytics/overview` | Corpus-level stats |
| `GET` | `/api/analytics/filing-types` | Distribution by filing type |
| `GET` | `/api/analytics/languages` | Language distribution |
| `GET` | `/api/analytics/quality-histogram` | Quality score histogram |
| `GET` | `/api/analytics/timeline` | Documents crawled per day |
| `GET` | `/api/analytics/top-companies` | Companies by document count |
| `GET` | `/api/analytics/reading-time` | Reading time distribution |
| `GET` | `/health` | Liveness probe |
| `GET` | `/health/db` | Readiness probe (checks DB) |

Full interactive docs at **http://localhost:8000/docs**.

---

## Data Schema

Each scraped document is stored as an AI document object. See `schema/ai_document.schema.json` for the full JSON Schema. Key fields:

| Field | Type | Description |
|-------|------|-------------|
| `id` | `uuid` | Unique document identifier |
| `content_hash` | `string` | SHA-256 of `body_text` — dedup key |
| `url` | `string` | Source URL on SEC EDGAR |
| `accession_number` | `string` | SEC accession number (e.g. `0000320193-23-000077`) |
| `company.cik` | `string` | 10-digit SEC Central Index Key |
| `company.name` | `string` | Registrant legal name |
| `company.tickers` | `string[]` | Exchange ticker symbols |
| `company.sic_code` | `string` | SEC Standard Industrial Classification |
| `filing_type` | `enum` | `10-K` \| `10-Q` \| `8-K` \| `DEF 14A` |
| `filing_date` | `date` | Date submitted to SEC |
| `period_of_report` | `date` | Fiscal period end date |
| `fiscal_year` | `int` | Calendar year of reporting period |
| `fetched_at` | `datetime` | Scrape timestamp |
| `title` | `string` | Document title |
| `body_text` | `string` | Clean full text — primary LLM input |
| `sections` | `object[]` | Pre-split sections with SEC item tags |
| `sections[].sec_item` | `string` | Canonical item ID (e.g. `item_1a`) |
| `word_count` | `int` | For LLM context window budgeting |
| `reading_time_minutes` | `float` | At 238 wpm |
| `language` | `string` | ISO 639-1 detected language |
| `content_type` | `enum` | `annual_report` \| `quarterly_report` \| etc. |
| `quality_score` | `float` | Composite 0.0–1.0 quality signal |
| `has_tables` | `bool` | Contains financial statement tables |
| `tags` | `string[]` | Derived: filing type, sector, detected SEC items |

### Quality Score Formula

```
quality_score =
  0.30 × length_score       (word_count ≥ 500 → 1.0, scales linearly below)
  0.25 × lang_confidence    (langdetect probability for detected language)
  0.25 × density_score      (body_text chars / raw HTML chars)
  0.20 × structure_score    (min(section_count / 5, 1.0))
```

Scores ≥ 0.70 indicate documents suitable for fine-tuning. The score is transparent and re-weightable — all raw components are stored as separate fields.

### Section `sec_item` Values

Sections are tagged with canonical SEC item identifiers detected by regex:

| `sec_item` | Section |
|------------|---------|
| `item_1` | Business |
| `item_1a` | Risk Factors |
| `item_2` | Properties |
| `item_7` | Management's Discussion & Analysis |
| `item_7a` | Quantitative Disclosures |
| `item_8` | Financial Statements |
| `item_9a` | Controls & Procedures |
| `item_15` | Exhibits |

Use `GET /api/documents/{id}/sections?sec_item=item_1a` to retrieve just the Risk Factors section without re-parsing.

---

## Design Decisions

### Crawler: structured API over link-following

The crawler uses `data.sec.gov/submissions/CIK{id}.json` as its navigation source instead of following HTML links. This provides:
- **Resilience**: Layout changes on EDGAR never break the crawler
- **Completeness**: The API returns the full filing history, not just what's linked from the current page
- **Metadata for free**: Accession number, filing date, period, and primary document filename come pre-structured

### Parser: layered content root fallback

SEC filings span multiple generations of HTML across 30 years of EDGAR. The parser tries `div#document` → `div.formContent` → `div#main-content` → `main` → `article` → `div#content` → body in sequence, requiring at least 200 characters of text before accepting a candidate. This handles both modern inline XBRL filings and older flat HTML.

### Idempotency: two-level dedup

1. **URL-level** (in-memory, per-run): `seen_urls` set loaded from DB at startup skips HTTP requests for already-known URLs
2. **Content-level** (DB, cross-run): `INSERT ... ON CONFLICT (content_hash) DO NOTHING` silently skips identical content even if accessed at a new URL

Running the scraper twice produces zero duplicates and makes zero redundant HTTP requests.

### AI Metadata: designed for downstream use

Fields were chosen to answer specific AI workflow questions:
- `word_count` → "Does this fit in my context window?"
- `sections[].sec_item` → "Give me all Risk Factors sections from 2023"
- `quality_score` → "Pre-filter before expensive LLM calls"
- `tags` → "Give me all finance-sector 10-Ks with detected MD&A"
- `has_tables` → "Find quantitative documents for financial Q&A"
- `language` → "Exclude non-English before embedding"
- `reading_time_minutes` → "Estimate processing cost before batching"

---

## Development Setup (without Docker)

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Start only postgres
docker compose up db -d

# Run migrations
uv run alembic upgrade head

# Run scraper
uv run python -m scraper.main --tickers AAPL --filing-types 10-K --max-filings 3

# Run API
uv run uvicorn api.main:app --reload --port 8000

# Run tests
uv run pytest tests/ -v

# Run analytics
uv run python analytics/stats.py --input output/edgar.jsonl
```

---

## Running Tests

```bash
# All tests
uv run pytest tests/ -v

# With coverage
uv run pytest tests/ --cov=scraper --cov-report=term-missing

# Specific module
uv run pytest tests/test_parser.py -v
uv run pytest tests/test_transformer.py -v
uv run pytest tests/test_writer.py -v
```

Tests are pure unit tests — no network calls, no database. All tests use HTML fixtures from `tests/fixtures/`.

---

## Analytics Script

```bash
# Load output/edgar.jsonl and print corpus stats
python analytics/stats.py

# Custom file
python analytics/stats.py --input path/to/custom_corpus.jsonl

# Filter to one filing type
python analytics/stats.py --filing-type 10-K

# Export as JSON for further processing
python analytics/stats.py --json > report.json
```

Outputs: corpus size, word count distribution, quality histogram, filing type breakdown, language distribution, top companies, SEC item coverage, and top/bottom documents by quality.

---

## Project Structure

```
edgar-scraper/
├── scraper/                # Core pipeline
│   ├── config.py           # Pydantic settings (reads .env)
│   ├── db.py               # SQLAlchemy async models + engine
│   ├── crawler.py          # Async EDGAR crawler (SEC API-based)
│   ├── parser.py           # HTML → ParsedPage (BeautifulSoup)
│   ├── transformer.py      # ParsedPage → AIDocument (enrichment)
│   ├── writer.py           # AIDocument → PostgreSQL (idempotent)
│   └── main.py             # CLI entry point
├── api/                    # REST API
│   ├── main.py             # FastAPI app factory
│   ├── db.py               # Session dependency
│   ├── models.py           # Pydantic response schemas
│   └── routers/
│       ├── documents.py    # Document CRUD + export
│       ├── runs.py         # Crawl run management
│       └── analytics.py    # Aggregate stats
├── migrations/             # Alembic schema migrations
│   └── versions/
│       └── 001_initial_schema.py
├── ui/                     # React frontend
│   └── src/
│       ├── api/client.ts   # Typed API fetch wrappers
│       ├── components/
│       └── pages/          # Overview, Documents, Runs, Analytics, Export
├── tests/                  # Unit tests
│   ├── conftest.py         # Shared fixtures
│   ├── test_parser.py
│   ├── test_transformer.py
│   └── test_writer.py
├── analytics/
│   └── stats.py            # Corpus statistics script
├── schema/
│   └── ai_document.schema.json  # JSON Schema for AI document object
├── docker-compose.yml
├── Dockerfile.api
├── Dockerfile.scraper
├── Dockerfile.ui
├── pyproject.toml          # Python deps (uv)
├── alembic.ini
├── entrypoint.sh           # API container startup (migrations → uvicorn)
├── .env.example
└── README.md
```

---

## Future Work

### Authentication
Add JWT-based auth to the API. Support API keys for programmatic access
(RAG systems, model training pipelines). Role-based access: read-only vs
admin (trigger crawls, delete runs).

### Schema Evolution
Increment `schema_version` in `documents` for each structural change.
Downstream consumers filter by version to avoid schema mismatch. Run
backfill migrations when adding new enrichment fields.

### Scheduling & orchestration
Replace the one-shot Docker service with a scheduler (Celery + Redis, or Prefect). Run nightly incremental crawls per company — only fetching filings newer than the most recent `filing_date` in the DB.

### S&P 500 company list
Add a seeding script that loads the current S&P 500 constituent list from a maintained source and runs the full pipeline across all 500 companies. Estimated corpus: ~50,000 documents, ~2B words.

### Monitoring & alerting
Add Prometheus metrics (crawl rate, error rate, quality score distribution over time) and alert on quality degradation or EDGAR API changes.

### Distributed Crawling
Replace direct HTTP calls with a Celery + Redis task queue. Multiple worker
containers process URLs in parallel. Enables 10× throughput without changing
the core parsing logic.

### De-duplication across sources
Extend `content_hash` dedup to work across multiple sources (EDGAR + company IR pages). The hash-based approach already supports this — no schema changes needed.

### Embedding pipeline
Add a post-processing step that generates embeddings for each section using a sentence transformer model and stores them in pgvector. This converts the existing section table directly into a vector store for semantic search.

### Incremental section diffing
For 10-K filings, diff the Risk Factors section year-over-year to detect material changes. Store the diff as a derived document type for change-detection use cases.

### XBRL structured data extraction
Parse XBRL inline tags to extract structured financial data (revenue, EPS, total assets) alongside the text. Store as a separate `financial_facts` table with a FK to `documents`.
