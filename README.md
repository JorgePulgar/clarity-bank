# ClarityBank — Prototipo TFM

![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)
![Streamlit](https://img.shields.io/badge/Streamlit-1.45-FF4B4B?logo=streamlit)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite)
![Azure OpenAI](https://img.shields.io/badge/Azure_OpenAI-gpt--4o--mini-0089D6?logo=microsoftazure)
![License](https://img.shields.io/badge/licencia-TFM--solo-lightgrey)

> **Estado**: prototipo funcional · Python 3.11–3.14 · no produccion

---

## Descripcion

ClarityBank es el backend de un sistema de inteligencia financiera personal para una fintech
agregadora simulada (340 000 usuarios, 2,1 M transacciones/mes).

El sistema cubre tres funcionalidades:

1. **Categorizacion automatica** — texto crudo del movimiento → una de 12 categorias.
2. **Deteccion de anomalias** — compara cada transaccion contra el historico del usuario
   (z-score por categoria + deteccion de salto en suscripciones).
3. **Insights mensuales en lenguaje natural** — resumen narrativo del mes generado por
   Azure OpenAI gpt-4o-mini o por plantilla local si no hay credenciales.

**Reparto del TFM**: mi companera entrega el modelo ML de clasificacion
(`models/load_classifier.py`). Yo llevo la infraestructura: API REST, base de datos,
anonimizacion RGPD, deteccion de anomalias, insights y dashboard.

---

## Arquitectura

```
                         ┌──────────────────────────────────────┐
 Peticion HTTP           │         FastAPI  (api/)              │
 POST /transactions ────►│                                      │
                         │  ┌──────────────────────────────┐   │
                         │  │   service.process_transaction │   │
                         │  │                              │   │
                         │  │  1. anonymize()              │   │
                         │  │     regex (siempre)          │   │
                         │  │     + Presidio NER (opcional)│   │
                         │  │                              │   │
                         │  │  2. classify()               │   │
                         │  │     L1: clasificador local   │   │
                         │  │     L2: Azure OpenAI LLM     │   │
                         │  │         (casos dificiles)    │   │
                         │  │                              │   │
                         │  │  3. detect_anomaly()         │   │
                         │  │     z-score por categoria    │   │
                         │  │     + salto en suscripcion   │   │
                         │  │                              │   │
                         │  │  4. INSERT en SQLite         │   │
                         │  └──────────────────────────────┘   │
                         │                                      │
                         │  POST /insights/generate             │
                         │     agrega mes → prompt → LLM/tpl   │
                         └──────────────────────────────────────┘
                                          │
                                    SQLite (data/)
                                          │
                         ┌────────────────▼─────────────────────┐
                         │    Dashboard  (Streamlit)            │
                         │  pantalla 1: transaccion individual  │
                         │  pantalla 2: importar historico      │
                         │  pantalla 3: insights del mes        │
                         └──────────────────────────────────────┘
```

### Dos niveles de clasificacion

| Nivel | Quien          | Cuando                          | Coste  |
|-------|----------------|---------------------------------|--------|
| L1    | Modelo local   | siempre (primer intento)        | 0 EUR  |
| L2    | Azure OpenAI   | confianza < umbral o sin match  | ~0.001 EUR/tx |

El LLM recibe **unicamente la descripcion anonimizada** (nunca datos personales).

### Componentes con fallback

| Componente    | Real                        | Fallback                        |
|---------------|-----------------------------|---------------------------------|
| Clasificador  | `models/load_classifier.py` | mock por palabras clave         |
| Anonimizacion | Presidio + regex            | solo regex (si falta Presidio)  |
| Insights      | Azure OpenAI gpt-4o-mini    | plantilla local determinista    |

`GET /health` informa del modo activo de cada componente.

---

## Instalacion y puesta en marcha

### Requisitos

- Python 3.11, 3.12, 3.13 o 3.14
- (Opcional) Credenciales Azure OpenAI para LLM real e insights
- (Opcional) Python 3.11/3.12 + spacy para anonimizacion NER completa

### 1. Entorno virtual e instalacion

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Variables de entorno (opcionales)

```bash
copy .env.example .env    # Windows
cp .env.example .env      # macOS / Linux
```

Editar `.env` con las credenciales Azure si se dispone de ellas:

```
AZURE_OPENAI_ENDPOINT=https://tu-recurso.openai.azure.com/
AZURE_OPENAI_API_KEY=tu-clave
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini
```

Sin credenciales el sistema funciona igual, usando el clasificador mock y
la plantilla de insights.

### 3. Arrancar la API

```bash
uvicorn api.main:app --reload
# Swagger interactivo: http://127.0.0.1:8000/docs
```

### 4. Arrancar el dashboard (en otra terminal, con la API levantada)

```bash
streamlit run dashboard/streamlit_app.py
# Abre automaticamente http://localhost:8501
```

### 5. (Opcional) Anonimizacion NER completa

Requiere Python 3.11 o 3.12:

```bash
pip install presidio-analyzer presidio-anonymizer spacy
python -m spacy download es_core_news_md
```

---

## Demo end-to-end

Un solo comando arranca la API, carga 6 meses de historico simulado,
procesa 5 transacciones representativas (clara, ambigua, escalada a LLM,
anomala y normal), genera el insight del mes y muestra las metricas:

```bash
python scripts/e2e_demo.py
```

Salida esperada (resumida):

```
==============================================================
  ClarityBank - Demo end-to-end  |  2026-05-27 08:25:47 UTC
==============================================================

  [1/5] Arrancando API ...  OK  (1.0 s)
  [2/5] Historico (149 tx) importado  ...  OK  (0.9 s)

  [3/5] Transacciones de demo
  [CLARA       ] alimentacion     L1 92%      -43.27 EUR
  [AMBIGUA     ] ingresos         L1 55%      150.00 EUR
  [ESCALADA LLM] otros            L2 40%      -80.00 EUR
  [ANOMALA     ] compras          L1 92%    -1450.00 EUR  <-- ANOMALIA
  [NORMAL      ] suscripciones    L1 92%      -12.99 EUR

  [4/5] Insight mensual generado (fuente: template)
  [5/5] Metricas: 154 tx · 73 anomalias · 1 llamada LLM (0.6%)
```

---

## Prueba manual paso a paso

Con la API arrancada (`uvicorn api.main:app --reload`), ejecutar en orden:

### 1. Verificar que todo esta OK

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","classifier":"mock","anonymization":"regex","insights":"template"}
```

### 2. Clasificar una transaccion (con y sin PII)

```bash
# Transaccion limpia -> alimentacion L1 92%
curl -X POST http://127.0.0.1:8000/transactions \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"u1\",\"description\":\"PAGO TARJETA MERCADONA SL MADRID\",\"amount\":-43.27}"

# Transaccion con PII -> ver description_anonymized con <IBAN> <EMAIL>
curl -X POST http://127.0.0.1:8000/transactions \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"u1\",\"description\":\"TRANSFERENCIA ES9121000418450200051332 juan@mail.com\",\"amount\":-200.0}"

# Sin match de palabras clave -> otros L2 40% (caso dificil, escalaria a LLM)
curl -X POST http://127.0.0.1:8000/transactions \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"u1\",\"description\":\"CUOTA ASOCIACION CULTURAL MADRID\",\"amount\":-80.0}"
```

### 3. Cargar historico e introducir anomalia

```bash
# Generar 6 meses de datos simulados
python scripts/generate_history.py --user-id u1 --months 6

# Importar via CSV
curl -X POST http://127.0.0.1:8000/transactions/import \
  -F "file=@data/history_u1.csv"

# Ahora enviar un outlier: deberia marcarse is_anomaly=true
curl -X POST http://127.0.0.1:8000/transactions \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"u1\",\"description\":\"AMAZON COMPRA ONLINE\",\"amount\":-1450.0}"
```

### 4. Consultar estadisticas

```bash
curl http://127.0.0.1:8000/users/u1/stats
curl http://127.0.0.1:8000/users/u1/cost-stats
curl http://127.0.0.1:8000/transactions/u1?limit=5
```

### 5. Generar insight del mes

```bash
# Cambiar YYYY-MM al mes actual
curl -X POST http://127.0.0.1:8000/insights/generate \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"u1\",\"month\":\"2026-05\"}"
```

### 6. Dashboard interactivo

Con la API levantada, en otra terminal:

```bash
streamlit run dashboard/streamlit_app.py
# Abre http://localhost:8501
```

Pantallas disponibles: clasificar transaccion · importar historico · generar insight.

### 7. Swagger (UI grafica de todos los endpoints)

```
http://127.0.0.1:8000/docs
```

---

## Endpoints

| Metodo | Ruta                           | Descripcion                              |
|--------|--------------------------------|------------------------------------------|
| GET    | `/health`                      | estado y modo (real/mock/fallback)       |
| POST   | `/transactions`                | procesa y guarda una transaccion         |
| GET    | `/transactions/{user_id}`      | historico del usuario                    |
| POST   | `/transactions/import`         | importa CSV o JSON en lote               |
| POST   | `/insights/generate`           | insight mensual en lenguaje natural      |
| GET    | `/users/{user_id}/stats`       | agregados: gastos, ingresos, anomalias   |
| GET    | `/users/{user_id}/cost-stats`  | estadisticas de coste LLM               |

Swagger completo en `http://127.0.0.1:8000/docs` con la API levantada.

---

## Categorias (lista cerrada de 12)

`alimentacion · restauracion · transporte · ocio · compras · hogar · salud ·
suscripciones · transferencias · ingresos · impuestos_tasas · otros`

---

## Tests

```bash
pytest -q                  # toda la suite
pytest -q --tb=short       # con traza compacta de fallos
```

La suite cubre: endpoints de transacciones, anonimizacion por regex, deteccion
de anomalias z-score y generacion de insights con LLM mockeado.

---

## Estructura del repositorio

```
clarity-bank/
├── api/
│   ├── main.py            # app FastAPI + /health + lifespan
│   ├── config.py          # settings desde .env (pydantic-settings)
│   ├── service.py         # pipeline unico: anon -> clasif -> anomalia -> save
│   ├── routers/           # transactions.py, insights.py, users.py
│   ├── models/            # schemas.py — contrato HTTP (pydantic)
│   └── db/                # database.py (conexion SQLite) + queries.py (CRUD)
├── core/
│   ├── anonymization.py   # regex + Presidio NER (opcional)
│   ├── classify.py        # mock o clasificador real (sustitucion transparente)
│   ├── anomalies.py       # z-score por categoria + salto en suscripciones
│   └── insights.py        # agregacion + prompt + LLM/plantilla
├── models/
│   ├── load_classifier.py # contrato load()/classify (ML lo implementa)
│   └── model_metadata.json
├── dashboard/
│   └── streamlit_app.py   # 3 pantallas interactivas
├── scripts/
│   ├── generate_history.py # genera CSV de historico simulado
│   └── e2e_demo.py         # demo real end-to-end
├── tests/                  # suite pytest
├── fases/                  # plan de trabajo por fases (fuente de verdad)
├── data/                   # SQLite + datasets (no versionado)
├── MEMORIA.md              # decisiones tecnicas y errores resueltos
└── .env.example            # plantilla de variables de entorno
```

---

## Decisiones tecnicas principales

- **Pipeline unico** (`api/service.py`). Los endpoints `POST /transactions` y
  `POST /transactions/import` comparten el mismo `process_transaction`. Evita
  divergencia de comportamiento y simplifica los tests.

- **Clasificador sustituible sin tocar codigo**. `core/classify.py` intenta
  importar `models/load_classifier.load()`. Si falla (modelo no entregado aun),
  cae al mock por palabras clave. El cambio es transparente: `GET /health`
  reporta el modo activo.

- **Anonimizacion degradable**. Regex es la capa base (siempre disponible);
  Presidio + spacy se activa solo si esta instalado. La API arranca en cualquier
  entorno sin dependencias pesadas.

- **Dos niveles de coste con trazabilidad**. El nivel usado (L1 local vs L2 LLM)
  se guarda en cada transaccion. `GET /users/{id}/cost-stats` ofrece el desglose.

- **Insight con fallback de plantilla**. Sin credenciales Azure, `generate_insight`
  produce un resumen determinista a partir de los agregados del mes. La demo nunca
  depende del LLM.

- **Timestamps ISO 8601 como texto en SQLite**. Se evita el conversor `PARSE_DECLTYPES`
  (deprecado en Python 3.12+) que causaba fallos al leer columnas TIMESTAMP con el
  formato `T` de ISO 8601.

---

## Limitaciones conocidas

- **Prototipo, no produccion**: sin autenticacion, sin HTTPS, SQLite de un solo
  fichero. Para escalar: PostgreSQL + autenticacion JWT + contenedores.
- **Presidio/spacy no disponibles en Python 3.14** (sin wheel). Funciona solo-regex.
  Para NER completo usar Python 3.11/3.12.
- **Clasificador real pendiente**: hasta que ML entregue `models/load_classifier.py`
  el sistema usa el mock por palabras clave (L1 siempre, L2 en caso de no-match).
- **Deteccion de anomalias basada en historico**: necesita suficientes transacciones
  previas para que el z-score sea significativo (minimo ~10 por categoria).
- **Coste LLM**: las llamadas a Azure OpenAI por `POST /insights/generate` tienen
  coste real si se usan credenciales de produccion.

---

## Memoria de desarrollo

Las decisiones de diseno detalladas, errores encontrados y sus soluciones se
documentan en [`MEMORIA.md`](MEMORIA.md).

---

---

# ClarityBank — TFM Prototype (English)

> **Status**: functional prototype · Python 3.11–3.14 · not for production

## Description

ClarityBank is the backend of a personal financial intelligence system for a
simulated aggregator fintech (340 000 users, 2.1 M transactions/month).

Three core features:

1. **Automatic categorization** — raw transaction text → one of 12 categories.
2. **Anomaly detection** — compares each transaction against the user's history
   (z-score per category + subscription price jump detection).
3. **Monthly insights in natural language** — narrative summary generated by
   Azure OpenAI gpt-4o-mini or a local template if no credentials are available.

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn api.main:app --reload          # API at http://127.0.0.1:8000/docs
streamlit run dashboard/streamlit_app.py  # Dashboard at http://localhost:8501
python scripts/e2e_demo.py             # Full end-to-end demo (no extra setup needed)
```

## API Endpoints

| Method | Route                          | Description                             |
|--------|--------------------------------|-----------------------------------------|
| GET    | `/health`                      | system status and component modes       |
| POST   | `/transactions`                | process and store a transaction         |
| GET    | `/transactions/{user_id}`      | user transaction history                |
| POST   | `/transactions/import`         | bulk import from CSV or JSON            |
| POST   | `/insights/generate`           | monthly insight in natural language     |
| GET    | `/users/{user_id}/stats`       | aggregates: spending, income, anomalies |
| GET    | `/users/{user_id}/cost-stats`  | LLM cost statistics                     |

## Two-level Classification

| Level | Who             | When                              | Cost        |
|-------|-----------------|-----------------------------------|-------------|
| L1    | Local model     | always (first attempt)            | 0 EUR       |
| L2    | Azure OpenAI    | low confidence or no keyword match| ~0.001 EUR  |

Only **anonymized descriptions** are ever sent to the LLM (GDPR compliance).

## Known Limitations

- No authentication or HTTPS (prototype only).
- Presidio/spacy unavailable on Python 3.14 (no wheel) — NER layer disabled, regex only.
- Anomaly detection requires sufficient history (~10+ transactions per category).
- Real ML classifier pending delivery from teammate (`models/load_classifier.py`).

## Development Notes

Design decisions and resolved bugs are documented in [`MEMORIA.md`](MEMORIA.md).
