<!--
  GitHub repo README for clarity-bank (English version)
  Repo: github.com/JorgePulgar/clarity-bank
  Place this file as README.md at the root of the repo.
-->

<p align="right"><sub><b>English</b> · <a href="./README.es.md">Español</a></sub></p>

<h1 align="center">ClarityBank — Transaction Intelligence</h1>

<p align="center">
  <b>Two-level transaction categorisation pipeline for a Spanish fintech aggregator</b> · FastAPI backend · Streamlit dashboard<br>
  <sub>LightGBM · Azure OpenAI · Presidio GDPR anonymisation · Anomaly detection · TFM prototype</sub>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/FastAPI-0.110%2B-009688?style=flat-square&logo=fastapi&logoColor=white"/>
  <img src="https://img.shields.io/badge/Azure%20OpenAI-gpt--4o--mini-0078D4?style=flat-square&logo=microsoftazure&logoColor=white"/>
  <img src="https://img.shields.io/badge/Streamlit-1.33%2B-FF4B4B?style=flat-square&logo=streamlit&logoColor=white"/>
  <img src="https://img.shields.io/badge/tests-55%20passed-4CAF50?style=flat-square"/>
</p>

---

A FastAPI + Streamlit prototype that classifies raw bank transaction descriptions into 12 expense categories using a two-level pipeline: a local LightGBM classifier first, Azure OpenAI `gpt-4o-mini` as fallback for uncertain cases — with GDPR anonymisation applied before any external call.

> 🇪🇸 *También disponible en español: [README.es.md](README.es.md)*

## TL;DR

- **Two-level classification**: LightGBM (91.2% L1 accuracy, 16.8ms) escalates to Azure OpenAI only when confidence < 0.70 — L1+L2 combined accuracy reaches 96.1%
- Built with **FastAPI + SQLite + Streamlit + Azure OpenAI + LightGBM + sentence-transformers**
- **GDPR-compliant by design**: Presidio + regex anonymisation strips names, IBANs, DNIs, phones before any LLM call — 100% PII recall, 0 false positives in tests
- **Anomaly detection** on each user's historical spending — z-score (σ = 3.0) + subscription change detector — 1.2% flag rate on realistic data
- **Monthly natural language insights** via `gpt-4o-mini` with deterministic template fallback — demo runs without cloud credentials
- TFM prototype for **ClarityBank**, a Spanish fintech aggregator (340K users, 2.1M transactions/month)

## Project summary

ClarityBank is a TFM (Master's Final Project) prototype for a Spanish open-banking aggregator. The system receives raw bank transaction descriptions and amounts, and automatically assigns each transaction to one of 12 fixed expense categories. Beyond classification, it detects spending anomalies against each user's historical profile and generates monthly financial summaries in natural language.

The project is split in two: my classmate trained the ML classifier (LightGBM + multilingual sentence embeddings). I built the infrastructure: REST API, SQLite persistence, GDPR anonymisation pipeline, anomaly detection engine, insight generation with LLM fallback, and the Streamlit dashboard. The classifier interface is a single `load()` function — until the model was delivered, a keyword-based mock ran transparently in its place.

## Table of Contents

- [Key Features](#key-features)
- [Technology stack](#technology-stack)
- [Local setup](#local-setup)
- [Project structure](#project-structure)
- [What it does](#what-it-does)
- [Why this matters](#why-this-matters)
- [Architecture](#architecture)
- [Stats](#stats)
- [Key design decisions](#key-design-decisions)
- [How the core guarantees are met](#how-the-core-guarantees-are-met)
- [Known limitations](#known-limitations)
- [Development process & lessons learned](#development-process--lessons-learned)
- [Technical documentation](#technical-documentation)

---

## Key Features

- **Two-level classification**: L1 classifier (LightGBM + 384-dim multilingual embeddings) runs locally in ~16.8ms; L2 (Azure OpenAI) only fires when L1 confidence < 0.70
- **GDPR anonymisation**: Presidio NER + regex strips PII before any external call; degrades gracefully to regex-only if `spacy` is not installed — the API starts either way
- **Anomaly detection**: z-score per expense category (σ = 3.0, min 10 samples) + dedicated subscription change detector; 4 anomalies in 329 test transactions (1.2%)
- **Insight generation**: monthly spend summaries in natural language via `gpt-4o-mini`, with deterministic template fallback when no Azure credentials are configured
- **Mock-substitutable classifier**: `models/load_classifier.py::load()` raises `NotImplementedError`; `core/classify.py` catches it and falls back to keyword matching — `GET /health` reports the active mode
- **55 tests, 0 failed**: API endpoints, anonymisation, anomaly detection, and insight generation tested independently

---

## Technology stack

### Backend

- **Python 3.11+** — tested locally on 3.14; Presidio/spacy degrade gracefully on 3.14 (see [Known limitations](#known-limitations))
- **FastAPI >= 0.110** — async REST framework, Pydantic v2 validation, auto OpenAPI docs at `/docs`
- **SQLite** (Python `sqlite3`) — single-file persistence, no migration tooling needed for prototype scale
- **pydantic-settings >= 2.2** — centralised config via `api/config.py`, reads `.env`

### AI / ML

- **LightGBM >= 4.0** — L1 classifier, trained on 2,946 transactions (80/10/10 split); 97.6% validation accuracy
- **sentence-transformers >= 2.7** — `paraphrase-multilingual-MiniLM-L12-v2`, 384-dim multilingual embeddings
- **Azure OpenAI `gpt-4o-mini`** — L2 classification fallback + monthly insight generation (deployed in Sweden Central for GDPR compliance)
- **Presidio Analyzer + Anonymizer >= 2.2** — NER-based PII detection and masking
- **spacy `es_core_news_md`** — Spanish NER model for Presidio (optional)

### Dashboard

- **Streamlit >= 1.33** — interactive demo with live transaction feed, anomaly highlighting, and monthly insight view
- **pandas >= 2.2** — data manipulation for Streamlit tables and charts

### Testing

- **pytest >= 8.1**
- **httpx >= 0.27** — FastAPI `TestClient`

---

## Local setup

### Prerequisites

- Python 3.11 or 3.12 recommended (3.14 works but Presidio NER degrades — see [Known limitations](#known-limitations))
- An Azure OpenAI deployment with `gpt-4o-mini` in Sweden Central — **optional**, the system runs fully without it

### Install

```bash
git clone https://github.com/JorgePulgar/clarity-bank.git
cd clarity-bank
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

For full NER anonymisation (requires Python 3.11/3.12):

```bash
python -m spacy download es_core_news_md
```

### Configure

```bash
cp .env.example .env
# Edit .env — the defaults work for a local run without Azure.
# Fill AZURE_OPENAI_* to enable LLM classification and insights.
```

Key variables in `.env.example`:

```env
CLARITY_DB_PATH=data/clarity.db
CLARITY_API_URL=http://127.0.0.1:8000

# Azure OpenAI — leave empty to use template fallback and mock classifier
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini
AZURE_OPENAI_REGION=swedencentral

# Force mock classifier even if models/classifier.pkl exists
USE_MOCK_CLASSIFIER=false

# spacy model for Presidio NER
PRESIDIO_SPACY_MODEL=es_core_news_md
```

### Run

```bash
# Terminal 1 — API
uvicorn api.main:app --reload

# Terminal 2 — Dashboard
streamlit run dashboard/streamlit_app.py
```

On Windows, double-click `start_demo.bat` — it installs dependencies, starts both services in separate windows, waits for the health check, and opens the browser.

The API runs at `http://localhost:8000` (OpenAPI docs at `/docs`). The dashboard opens at `http://localhost:8501`.

---

## Project structure

```
clarity-bank/
├── api/
│   ├── config.py              # pydantic-settings, reads .env
│   ├── main.py                # FastAPI app, CORS, router registration
│   ├── service.py             # Pipeline: anonymise → classify → detect → persist
│   ├── db/
│   │   ├── database.py        # SQLite connection
│   │   └── queries.py         # CRUD operations
│   ├── models/
│   │   └── schemas.py         # Pydantic request/response schemas
│   └── routers/
│       ├── transactions.py    # POST /transactions, POST /transactions/import, GET /transactions
│       ├── insights.py        # GET /insights/{user_id}
│       └── users.py           # GET/POST /users
├── core/
│   ├── anonymization.py       # Presidio NER + regex, degradable
│   ├── classify.py            # L1/L2 wrapper, mock fallback
│   ├── anomalies.py           # Z-score + subscription change detection
│   └── insights.py            # Azure OpenAI + template fallback
├── models/
│   ├── load_classifier.py     # Classifier interface (load() → callable)
│   ├── classifier.pkl         # LightGBM model (joblib)
│   └── model_metadata.json    # Metrics, threshold, embedding info
├── dashboard/
│   └── streamlit_app.py       # Streamlit demo UI
├── scripts/
│   ├── generate_history.py    # Generate synthetic transaction history
│   └── e2e_demo.py            # End-to-end smoke test
├── tests/
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_anomalies.py
│   ├── test_anonymization.py
│   └── test_insights.py
├── fases/                     # Development phase plans and progress
├── docs/
│   ├── claritybank_prototipo.drawio.png
│   └── claritybank_produccion.drawio.png
├── data/
│   └── clarity.db             # SQLite database (gitignored)
├── start_demo.bat             # One-click launch (Windows)
├── start_demo.ps1             # PowerShell equivalent
├── requirements.txt
└── .env.example
```

---

## What it does

- **Classifies transactions** — `POST /transactions` receives a raw description (e.g. `PAGO TARJETA MERCADONA SL MADRID`) and amount, runs the full pipeline, and returns `{ "categoria": "alimentacion", "confianza": 1.0, "nivel_usado": 1 }`. The anonymised description and all metadata are persisted to SQLite.
- **Bulk import** — `POST /transactions/import` accepts a JSON array; each transaction runs through the same pipeline independently. Used by `scripts/generate_history.py` to seed a realistic user history.
- **Detects anomalies** — every new transaction is checked against that user's historical spending in the same category. If the z-score exceeds 3.0 (and the user has at least 10 prior samples), the transaction is flagged with a reason string. Subscription transactions additionally check for price changes at the merchant level.
- **Generates monthly insights** — `GET /insights/{user_id}` sends the user's last 30 days of categorised transactions to `gpt-4o-mini` and returns a 4-paragraph natural language summary: top spending categories, anomalies observed, income/expense balance, one actionable recommendation. Falls back to a deterministic template if no Azure credentials are configured.
- **Exposes system health** — `GET /health` reports `{ "classifier": "real" | "mock", "llm": "configured" | "not configured", "anonymiser": "presidio+regex" | "regex_only" }`.

[↑ Back to top](#table-of-contents)

---

## Why this matters

### The problem

A Spanish open-banking aggregator processes 2.1 million transactions per month from 340,000 users. Every raw transaction arrives as a bank-formatted string — `COMPRA TPV 12345 MERCADONA SL MADRID` or `RECIBO ENDESA CONTRATO 87654321` — with no category attached. Assigning categories manually doesn't scale. Sending all 2.1M descriptions directly to a cloud LLM would cost hundreds of euros per month for what is largely a solved problem, and introduce 500–1,500ms of latency per transaction. Neither is viable.

### Who has this problem

PFM (Personal Finance Management) teams at open-banking aggregators, neobanks, and any fintech processing multi-source bank transactions at scale. In the Spanish market: Fintonic, Plum, and the PFM layers inside major banks.

### Why sending everything to a cloud LLM is not enough

Three reasons. First, cost: at 2.1M transactions/month and `gpt-4o-mini` pricing, full LLM classification runs to hundreds of euros per month for transactions that classify trivially. Second, latency: LLM round-trips add 500–1,500ms; the API target is < 3s total. Third, GDPR: raw transaction descriptions contain names, IBANs, phone numbers — they cannot leave EU infrastructure unredacted.

### How this project addresses it

- **Cost** → L1 classifier handles > 91% of transactions locally at zero marginal cost; LLM is called only for uncertain cases (confidence < 0.70).
- **Latency** → L1 pipeline completes in ~55ms at the API level (16.8ms pure classifier). L2 adds 500–1,500ms only for the minority that needs it.
- **GDPR** → `core/anonymization.py` runs before every external call. The LLM sees `TRANSFERENCIA DE <PERSONA>`, not `TRANSFERENCIA DE JUAN GARCÍA`.

### Concrete use cases

A user receives a salary transfer: `NOMINA MAYO 2026 EMPRESA SL`. The classifier assigns `ingresos` with confidence 1.0 in 16.8ms. A second user makes a 1,450 EUR Amazon purchase — 40× their usual amount with that merchant — the anomaly detector flags it and the monthly insight names it explicitly: "1.450 EUR en compras, 40 veces superior a la media." A third user's `APPLE` transaction has confidence 0.36 (below 0.70): the LLM resolves it to `suscripciones`. No manual intervention at any step.

### What it is NOT

It is not a production-grade banking system — there is no authentication, no row-level user isolation, and SQLite does not support concurrent writes at aggregator scale. It does not replace human review for genuinely ambiguous transactions. It is not a multi-bank connector or a data normaliser — it processes whatever descriptions are POSTed to the API.

[↑ Back to top](#table-of-contents)

---

## Architecture

The prototype is a single-host deployment: FastAPI backend + SQLite + Streamlit on the same machine, calling Azure OpenAI only for uncertain L2 classification and monthly insight generation.

### Prototype architecture

![Prototype architecture](docs/claritybank_prototipo.drawio.png)

### Production architecture

In a production deployment the Streamlit demo is replaced by a proper frontend, SQLite by PostgreSQL, and transaction ingestion by a real-time Kafka consumer. The API and ML inference layers scale horizontally; the anonymisation and classification pipeline remains the same.

![Production architecture](docs/claritybank_produccion.drawio.png)

### Components

| Layer | Technology | Role |
|-------|-----------|------|
| API | FastAPI + uvicorn | REST endpoints, request validation, CORS |
| Persistence | SQLite (`sqlite3`) | Users, transactions, classifications, anomaly flags |
| Config | pydantic-settings | Centralised `.env` reading, validated at startup |
| Anonymisation | Presidio + regex | PII stripping before any external call |
| Classification L1 | LightGBM + sentence-transformers | Local inference, ~16.8ms |
| Classification L2 | Azure OpenAI `gpt-4o-mini` | Fallback for confidence < 0.70 |
| Anomaly detection | Z-score + subscription detector | Per-user historical comparison |
| Insight generation | Azure OpenAI `gpt-4o-mini` | Monthly NL summaries, template fallback |
| Dashboard | Streamlit | Interactive demo UI |

### Transaction processing flow

1. `POST /transactions` reaches `api/routers/transactions.py`
2. `api/service.py::process_transaction()` takes over — single function for both single and bulk endpoints
3. `core/anonymization.py::anonymize()` — Presidio NER + regex strips PII; returns anonymised text and list of detected entity types
4. `core/classify.py::classify()` — calls L1 (LightGBM + embeddings); if confidence < 0.70, calls L2 (`gpt-4o-mini`); returns `{ categoria, confianza, nivel_usado }`
5. `core/anomalies.py::detect_zscore_anomaly()` — z-score vs the user's historical spending in the same category (min 10 samples)
6. If `categoria == "suscripciones"` and not already flagged: `detect_subscription_change()` checks merchant-level payment history for price deviations
7. `api/db/queries.py` inserts the complete row to SQLite

[↑ Back to top](#table-of-contents)

---

## Stats

| Metric | Value |
|--------|-------|
| Total commits | 35 |
| Python LOC | 3,479 |
| Test files | 4 |
| Tests | **55 passed, 0 failed** |
| L1 accuracy (threshold 0.70, test set) | 91.2% |
| L1 + L2 combined accuracy | 96.1% |
| F1-macro (L1, test set) | 91.3% |
| L1 classifier latency — mean | 16.8ms |
| L1 classifier latency — p95 | 37ms |
| API pipeline latency — mean | 55.5ms |
| API pipeline latency — p95 | 105.9ms |
| PII anonymisation recall | 100% (5/5 test cases) |
| Anonymisation false positives | 0 |
| Anomaly rate (329 transactions, tuned params) | 1.2% (4 flagged) |
| Development phases complete | 5 / 6 |

[↑ Back to top](#table-of-contents)

---

## Key design decisions

### 1. Single pipeline in `api/service.py`

**Choice:** one `process_transaction()` function called by both `POST /transactions` (single) and `POST /transactions/import` (bulk).

**Alternative considered:** duplicate pipeline logic inside each router.

**Rationale:** two entry points that do the same thing will eventually diverge. One function is one place to read, one place to test, one place to change.

### 2. Anonymise before classify, not just before the LLM call

**Choice:** `anonymize()` is step 1 in the pipeline — before the L1 classifier runs.

**Alternative considered:** strip PII only from the L2 prompt, letting L1 see the raw text.

**Rationale:** two reasons. First, `description_anonymized` is what persists to SQLite — we never store raw PII at rest. Second, the training data included anonymised tokens (`<PERSONA>`, `<IBAN>`), so the classifier is already calibrated to handle masked text. The ordering enforces the GDPR guarantee structurally, not by convention.

### 3. Mock-substitutable classifier via `NotImplementedError`

**Choice:** `models/load_classifier.py::load()` raises `NotImplementedError`; `core/classify.py` catches that exception and falls back to keyword matching.

**Alternative considered:** a `USE_MOCK_CLASSIFIER` environment flag (the flag exists for CI but is not the primary mechanism).

**Rationale:** the `NotImplementedError` pattern makes substitution zero-touch — once `load()` returns a callable, the mock is gone without touching any other file. It made it possible to deliver a working API weeks before the ML model was ready. `GET /health` reports the active mode.

### 4. Production threshold 0.70, not the pkl's embedded 0.90

**Choice:** override the model's stored confidence threshold from 0.90 to 0.70.

**Alternative considered:** use the classifier's embedded threshold of 0.90.

**Rationale:** at threshold 0.90, 10.84% of transactions escalated to the LLM even when the L1 prediction was correct. Testing showed 0.70 reduces LLM call volume meaningfully while keeping combined L1+L2 accuracy at 96.1%. The stored threshold was tuned for maximum standalone L1 accuracy, not for cost efficiency at 2.1M transactions/month.

### 5. Degradable anonymisation

**Choice:** `core/anonymization.py` always runs the regex layer; Presidio NER is imported at module load and silently skipped if unavailable.

**Alternative considered:** raise an import error at startup if Presidio is missing.

**Rationale:** `presidio-analyzer`/`spacy` had no wheels for Python 3.14 at development time. Making them hard dependencies would have blocked API development. The regex layer handles the core PII surface (IBANs, DNIs, phones, emails, name patterns); Presidio adds recall on edge cases. The API starts and anonymises regardless.

### 6. Template fallback for insights

**Choice:** `core/insights.py` returns a deterministic template-based insight (`source="template"`) when `AZURE_OPENAI_API_KEY` is empty.

**Alternative considered:** return HTTP 503 if LLM is unconfigured.

**Rationale:** the TFM evaluation requires a working demo. A meaningful static insight is better than a 503 for evaluators without Azure access. When credentials are present, the real LLM path activates transparently — the response schema is identical.

[↑ Back to top](#table-of-contents)

---

## How the core guarantees are met

| Guarantee | Implementation evidence |
|-----------|------------------------|
| No PII reaches the LLM | `process_transaction()` calls `anonymize()` before `classify()`. The anonymised string — with `<PERSONA>`, `<IBAN>`, etc. — is what the L2 prompt receives. No path exists where raw text reaches Azure OpenAI. |
| Two cost tiers | L2 fires only when `confianza < 0.70`. At the tuned threshold, > 91% of transactions stay at L1 (free, local). |
| API latency < 3s | L1 pipeline: 55.5ms mean. L2 adds 500–1,500ms for the minority that escalates. L1-path p99 is comfortably under the 3s target. |
| GDPR storage | `description_raw` is stored in SQLite for internal audit only. `description_anonymized` is what the application layer uses and what is sent externally. |
| Demo without cloud credentials | `USE_MOCK_CLASSIFIER=false` + empty `AZURE_OPENAI_API_KEY` → mock classifier + template insights. The system starts, classifies, detects anomalies, and returns insights without any external call. |

[↑ Back to top](#table-of-contents)

---

## Known limitations

- **SQLite** — no concurrent write support. Acceptable at prototype scale; production requires PostgreSQL with connection pooling.
- **No authentication** — `user_id` is a plain string in the request body. No JWT, no sessions, no per-user isolation at the API level.
- **Python 3.14 + Presidio** — `presidio-analyzer`/`spacy` had no wheels for 3.14 at development time. On 3.14 the anonymisation degrades to regex-only, which misses edge cases like names in full uppercase. For full NER coverage: Python 3.11 or 3.12 + `python -m spacy download es_core_news_md`.
- **Simulated streaming** — the Streamlit "live feed" uses `st.rerun()` polling, not real-time push. In production this would be a Kafka consumer or webhook listener on the same `POST /transactions` endpoint.
- **suscripciones/ocio boundary** — when the exact platform name is absent from the description (e.g. `PAGO PLATAFORMA STREAMING`), the classifier's precision on `suscripciones` drops to ~62% on robustness tests. More training examples for generic subscription descriptions is the documented fix.
- **sklearn version mismatch** — `classifier.pkl` was trained on scikit-learn 1.6.1; `requirements.txt` pins >= 1.4. This triggers `InconsistentVersionWarning`. The model works correctly, but retraining on 1.8.x is recommended before final TFM submission.
- **Phase 6 incomplete** — end-to-end integration tests, API documentation export, and model card are pending.

[↑ Back to top](#table-of-contents)

---

## Development process & lessons learned

### SQLite + Python 3.14 timestamp bug

The first time `GET /transactions` ran against a populated database, it returned `ValueError: not enough values to unpack (expected 2, got 1)`. Not an obvious message for what turned out to be a three-line change. `sqlite3.connect(..., detect_types=PARSE_DECLTYPES)` activates a legacy timestamp converter that expects `YYYY-MM-DD HH:MM:SS` format. We stored ISO 8601 with a `T` separator. That converter was deprecated in Python 3.12 and breaks in 3.14. Fix: remove `detect_types` entirely. Timestamps flow as plain strings throughout — `api/db/database.py`.

### Classifier booting in mock mode despite the model being present

On the first run after the real model was delivered, `GET /health` still returned `"classifier": "mock"`. Two independent bugs. Bug one: the API started before the ~270MB `paraphrase-multilingual-MiniLM-L12-v2` model finished downloading from HuggingFace. `_load_real()` failed silently and locked the module-level singleton as mock for the session. Bug two: `streamlit_app.py` was reading `h.get("classifier_mode", "mock")` but the API's JSON uses the key `"classifier"`. The dashboard would always show mock regardless of what the API reported. Bug one resolves itself after the initial download cache is warm — subsequent restarts are instant. Bug two was a one-character key fix.

### Presidio anonymising merchant names

After wiring Presidio into the pipeline, `PAGO TARJETA MERCADONA SL MADRID` came back as `PAGO TARJETA <ORGANIZATION> <GPE>`. The merchant name — the primary classification signal — was gone. Root cause: calling `_analyzer.analyze()` without an entity whitelist made Presidio tag ORG, LOC, and GPE alongside actual PII. Fix: pass `entities=_PII_ENTITIES`, a whitelist limited to PERSON, EMAIL, PHONE_NUMBER, IBAN_CODE, NRP, and equivalents. ORGANIZATION and LOCATION are business names (classification signal), not personal data.

### Names in ALL CAPS not detected by Presidio

After fixing the entity whitelist, `TRASFERENCIA JUAN PACO` still passed through unmasked. The spacy `es_core_news_md` model was trained on mixed-case text; it does not recognise PER entities written in full uppercase. Fix: `_to_ner_case()` converts input to "NER case" before the Presidio pass — banking keywords stay in uppercase, everything else is title-cased. This preserves span positions so Presidio's offset-based replacement still works. (`core/anonymization.py`)

### Anomaly rate of 39%

First test against a 329-transaction synthetic history: 128 transactions flagged. The initial parameters — `MIN_SAMPLES=5`, `Z_THRESHOLD=2.5`, `JUMP_FACTOR=3.0` — were too aggressive. With only 5 samples, early transactions have high variance, and the fallback `JUMP_FACTOR` (used when standard deviation is zero) fired frequently. Tuning to `Z_THRESHOLD=3.0` (3-sigma, ~0.3% statistical tail), `MIN_SAMPLES=10`, `JUMP_FACTOR=5.0` brought the rate to 4/329 (1.2%). The 1,450 EUR Amazon outlier — 40× the user's ~140 EUR mean — correctly flagged. Normal 45 EUR Amazon purchases: not flagged.

### `detect_subscription_change` applied to all merchants

A 50 EUR Amazon purchase was being flagged because the user's historical mean for Amazon was ~145 EUR. Root cause: `detect_subscription_change` was running on every transaction with ≥3 merchant payments and a strict 10% threshold — but the function was designed for subscriptions (fixed recurring amounts), not general shopping merchants. Fix: `detect_subscription_change` now runs only when `categoria == "suscripciones"` — one guard condition in `api/service.py`.

### Looking back

The anonymise-before-classify ordering is correct — GDPR-safe by construction, not by convention. What made debugging harder was that when a classification was wrong, I had to mentally reconstruct what the pre-anonymisation text looked like. In a future version I'd add structured internal logging that records both forms (redacted in any external sink) to make pipeline diagnosis faster.

[↑ Back to top](#table-of-contents)

---

## Technical documentation

- [`fases/README.md`](fases/README.md) — development phase plan and completion status
- [`fases/FASE_1_cimientos.md`](fases/FASE_1_cimientos.md) through [`FASE_6_e2e_entregables.md`](fases/FASE_6_e2e_entregables.md) — per-phase task checklists with commit references
- [`docs/claritybank_prototipo.drawio.png`](docs/claritybank_prototipo.drawio.png) — prototype architecture diagram
- [`docs/claritybank_produccion.drawio.png`](docs/claritybank_produccion.drawio.png) — production architecture diagram
- [`models/model_metadata.json`](models/model_metadata.json) — classifier metrics, threshold, and embedding configuration
- `.env.example` — all configuration variables with inline descriptions

[↑ Back to top](#table-of-contents)
