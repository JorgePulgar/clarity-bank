# ClarityBank (prototipo TFM)

Sistema de categorizacion de transacciones bancarias, deteccion de anomalias e
insights mensuales. Fintech agregadora simulada. Prototipo, no produccion.

Arquitectura de dos niveles: clasificador local (gratis) + LLM solo para casos
dificiles. Todo lo que sale al LLM se anonimiza antes (RGPD).

## Estructura

```
clarity-bank/
├── api/                 # FastAPI
│   ├── main.py          # app + /health + arranque (crea tablas)
│   ├── config.py        # settings desde .env
│   ├── service.py       # pipeline: anonimizar -> clasificar -> anomalia -> guardar
│   ├── routers/         # transactions, insights, users
│   ├── models/          # schemas pydantic (contrato HTTP)
│   └── db/              # SQLite: conexion (database.py) + CRUD (queries.py)
├── core/
│   ├── anonymization.py # regex (siempre) + Presidio (opcional)
│   ├── classify.py      # mock por palabras clave; usa el modelo real si existe
│   ├── anomalies.py     # z-score + salto sobre maximo historico
│   └── insights.py      # agregacion + prompt; LLM o plantilla
├── models/              # artefactos del clasificador (los aporta ML)
│   ├── load_classifier.py  # contrato load()/classify (hoy: NotImplementedError -> mock)
│   └── model_metadata.json
├── dashboard/
│   └── streamlit_app.py # 3 pantallas: transaccion, importar, insights
├── scripts/
│   ├── generate_history.py # historico simulado -> CSV en data/
│   └── e2e_demo.py         # simulacion completa en proceso (sin servidor)
├── tests/               # smoke tests de los 5 endpoints
└── data/                # BD SQLite + datasets generados (no versionado)
```

## Estado de los componentes (dia 1)

| Componente     | Real                          | Fallback (activo ahora)            |
|----------------|-------------------------------|------------------------------------|
| Clasificador   | `models/load_classifier.py`   | mock por palabras clave            |
| Anonimizacion  | Presidio + regex              | solo regex (si falta Presidio)     |
| Insights       | Azure OpenAI gpt-4o-mini      | plantilla local (sin credenciales) |

`GET /health` indica que modo esta activo.

## Puesta en marcha

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt
copy .env.example .env            # rellenar credenciales (opcional dia 1)
```

### Arrancar la API

```bash
uvicorn api.main:app --reload
# docs interactivas: http://127.0.0.1:8000/docs
```

### Arrancar el dashboard (en otra terminal, con la API levantada)

```bash
streamlit run dashboard/streamlit_app.py
```

### Verificacion rapida sin servidor

```bash
python scripts/e2e_demo.py        # ejercita todo el pipeline e imprime resultados
```

### Generar datos de demo

```bash
python scripts/generate_history.py --user user_demo --months 3
# luego importar el CSV desde el dashboard o por POST /transactions/import
```

## Endpoints

| Metodo | Ruta                      | Descripcion                                  |
|--------|---------------------------|----------------------------------------------|
| POST   | `/transactions`           | procesa y guarda una transaccion             |
| GET    | `/transactions/{user_id}` | historico del usuario                        |
| POST   | `/transactions/import`    | importa CSV/JSON en lote                     |
| POST   | `/insights/generate`      | insight en lenguaje natural de un mes        |
| GET    | `/users/{user_id}/stats`  | agregados para el dashboard                  |
| GET    | `/health`                 | estado y modo (real/mock) de cada componente |

## Categorias (lista cerrada de 12)

`alimentacion, restauracion, transporte, ocio, compras, hogar, salud,
suscripciones, transferencias, ingresos, impuestos_tasas, otros`

## Tests

```bash
pytest -q
```

## Notas

- **Python 3.14**: `presidio-analyzer`/`spacy` pueden no tener wheel. El sistema
  funciona igual (anonimizacion solo-regex). Para la capa NER completa, usar
  Python 3.11/3.12 e instalar el modelo: `python -m spacy download es_core_news_md`.
- El clasificador real lo entrega ML en `models/load_classifier.py`; el codigo lo
  detecta y sustituye al mock sin cambios adicionales.
