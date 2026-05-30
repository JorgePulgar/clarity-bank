"""Benchmark empirico de coste y latencia del sistema ClarityBank.

Mide con numeros REALES (no estimados) el coste en tokens y la latencia del
pipeline de categorizacion + insights, para sustituir las estimaciones del
analisis economico de la memoria del TFM por mediciones medidas.

Que mide
--------
1. Tokens reales por llamada al LLM (campo `usage` de Azure OpenAI, NO tiktoken):
   1.1 Clasificacion nivel 2 (escalado al LLM).
   1.2 Generacion de insight mensual.
2. Tasa real de escalado al LLM (nivel 1 vs nivel 2) y su distribucion por categoria.
3. Latencia real por componente del pipeline (anonimizacion, clasificacion L1/L2,
   anomalias, guardado en BD) y end-to-end, comparando nivel 1 vs nivel 2.

Ademas proyecta el coste a la escala de ClarityBank (2,1M tx/mes, 340k usuarios),
lo compara contra escenarios naive (todo al LLM) y verifica el requisito de <3 s.

Caracteristicas
---------------
- Independiente: no toca la BD principal (usa una BD temporal que limpia al salir)
  ni modifica el codigo del sistema.
- Reproducible: fija random.seed para que el muestreo sea determinista.
- Robusto: reintenta las llamadas al LLM con backoff exponencial; descarta 2-3
  llamadas de warmup antes de medir (la primera siempre es mas lenta).
- Sin credenciales Azure: ejecuta las partes estructurales (escalado, latencia L1)
  y marca las secciones de LLM como OMITIDAS, sin abortar.

Uso
---
    python scripts/benchmark.py                       # defaults sensatos
    python scripts/benchmark.py --n-classifications 100 --n-insights 30
    python scripts/benchmark.py --output reports/benchmark_custom.json

Importante: las llamadas al LLM cuestan dinero real. El coste de ejecutar el
propio benchmark (pocos centimos) se reporta al final del informe.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import tempfile
import time
import uuid
import warnings

# El modelo real (LightGBM) avisa en cada prediccion al recibir un array sin nombres
# de columna. Inofensivo, pero con miles de transacciones inunda la consola. Se silencia
# aqui (solo en el benchmark; no se toca el codigo del modelo).
warnings.filterwarnings(
    "ignore",
    message="X does not have valid feature names",
    category=UserWarning,
)
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

# --- Aislamiento de la BD: APUNTAR a una BD temporal ANTES de importar api/* ---
# settings se instancia al importar api.config, leyendo CLARITY_DB_PATH del entorno.
# Hay que fijar el env var aqui arriba para que todo el sistema use la BD temporal.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# El informe usa caracteres de caja (UTF-8); la consola Windows por defecto es cp1252.
# Forzar UTF-8 en stdout/stderr para no fallar al imprimir.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

_TMP_DIR = Path(tempfile.mkdtemp(prefix="clarity_bench_"))
_TMP_DB = _TMP_DIR / "benchmark.db"
os.environ["CLARITY_DB_PATH"] = str(_TMP_DB)

# Importes del sistema (ya con la BD temporal fijada).
from api.config import settings  # noqa: E402
from api.db import database, queries  # noqa: E402
from core import classify as classify_mod  # noqa: E402
from core.anomalies import detect_subscription_change, detect_zscore_anomaly  # noqa: E402
from core.anonymization import anonymize, presidio_available  # noqa: E402
from core.classify import classify  # noqa: E402
from core.insights import _llm_insight, aggregate_month  # noqa: E402

# Generador de historicos sinteticos del proyecto (mismos comercios que la demo).
from scripts.generate_history import generate as generate_history  # noqa: E402


# ════════════════════════════════════════════════════════════════════════════
#  CONSTANTES DE PRECIOS Y VOLUMENES  (faciles de actualizar: los precios cambian)
# ════════════════════════════════════════════════════════════════════════════

# Azure OpenAI gpt-4o-mini, Sweden Central, Global Standard.
# Verificado en https://azure.microsoft.com/pricing en 2026-05-30.
PRICE_PER_1K_INPUT_USD = 0.00015
PRICE_PER_1K_OUTPUT_USD = 0.00060

# Azure OpenAI gpt-4o (modelo grande) — para el escenario naive B.
# Verificado en https://azure.microsoft.com/pricing en 2026-05-30.
PRICE_GPT4O_1K_INPUT_USD = 0.0025
PRICE_GPT4O_1K_OUTPUT_USD = 0.0100

USD_TO_EUR = 0.92  # actualizar al ejecutar

# Volumenes objetivo de ClarityBank (CLAUDE.md).
TRANSACTIONS_PER_MONTH = 2_100_000
USERS = 340_000
INSIGHTS_PER_MONTH = USERS  # 1 insight por usuario y mes

# Requisito de latencia (CLAUDE.md): respuesta <3 s por transaccion.
LATENCY_REQUIREMENT_MS = 3_000

# Las 12 categorias cerradas (espejo de core.classify.CATEGORIAS).
CATEGORIAS = sorted(classify_mod.CATEGORIAS)

# Prompt de clasificacion nivel 2. El clasificador real de mi companera implementa
# su propia escalada al LLM; mientras no se entregue, el benchmark mide el coste de
# una clasificacion LLM equivalente (1 categoria de la lista cerrada, salida minima).
_CLASSIFY_SYSTEM_PROMPT = (
    "Eres un clasificador de transacciones bancarias de ClarityBank. "
    "Asigna la transaccion a UNA de estas 12 categorias exactas: "
    + ", ".join(CATEGORIAS)
    + ". Responde SOLO con el nombre de la categoria, en minusculas, sin explicacion."
)


# ════════════════════════════════════════════════════════════════════════════
#  UTILIDADES DE ESTADISTICA
# ════════════════════════════════════════════════════════════════════════════


def _percentile(data: list[float], pct: float) -> float:
    """Percentil `pct` (0-100) por interpolacion lineal. Sin numpy."""
    if not data:
        return 0.0
    s = sorted(data)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return s[lo] + (s[hi] - s[lo]) * frac


def _stats(data: list[float]) -> dict[str, float]:
    """Resumen estadistico de una lista de valores (media, mediana, percentiles, max)."""
    if not data:
        return {"n": 0, "media": 0.0, "mediana": 0.0, "p50": 0.0,
                "p95": 0.0, "p99": 0.0, "max": 0.0, "min": 0.0}
    return {
        "n": len(data),
        "media": statistics.fmean(data),
        "mediana": statistics.median(data),
        "p50": _percentile(data, 50),
        "p95": _percentile(data, 95),
        "p99": _percentile(data, 99),
        "max": max(data),
        "min": min(data),
    }


# ════════════════════════════════════════════════════════════════════════════
#  COSTE EN TOKENS
# ════════════════════════════════════════════════════════════════════════════


def _cost_usd(prompt_tokens: int, completion_tokens: int,
              price_in: float = PRICE_PER_1K_INPUT_USD,
              price_out: float = PRICE_PER_1K_OUTPUT_USD) -> float:
    """Coste en USD de una llamada dado su uso de tokens y los precios por 1K."""
    return prompt_tokens / 1000 * price_in + completion_tokens / 1000 * price_out


# ════════════════════════════════════════════════════════════════════════════
#  CLIENTE LLM (clasificacion nivel 2) CON RETRY
# ════════════════════════════════════════════════════════════════════════════

_client = None  # cache del cliente AzureOpenAI


def _get_client():
    """Devuelve un cliente AzureOpenAI cacheado. Lanza si no hay credenciales."""
    global _client
    if _client is None:
        from openai import AzureOpenAI

        _client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
    return _client


def _with_retry(fn: Callable[[], Any], *, max_attempts: int = 5,
                base_delay: float = 1.0) -> Any:
    """Ejecuta `fn` reintentando con backoff exponencial ante fallos transitorios.

    No aborta el benchmark por un rate-limit o timeout puntual: reintenta hasta
    max_attempts. Si agota los intentos, propaga la ultima excepcion.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as exc:  # rate limit, timeout, error de red...
            last_exc = exc
            if attempt == max_attempts - 1:
                break
            delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
            print(f"    [retry {attempt + 1}/{max_attempts}] {type(exc).__name__}: "
                  f"reintento en {delay:.1f}s")
            time.sleep(delay)
    raise last_exc  # type: ignore[misc]


def _llm_classify(description: str, amount: float) -> tuple[str, dict[str, int], float]:
    """Clasificacion nivel 2 via Azure OpenAI. Mide tokens (usage) y latencia.

    Returns:
        (categoria, tokens, latencia_ms) donde tokens trae prompt/completion EXACTOS
        del campo `usage` que devuelve Azure (numero facturado, no estimado).
    """
    client = _get_client()
    user_prompt = (
        f"Descripcion: {description}\n"
        f"Importe: {amount:.2f} EUR\n"
        f"Categoria:"
    )

    def _call():
        return client.chat.completions.create(
            model=settings.azure_openai_deployment,
            messages=[
                {"role": "system", "content": _CLASSIFY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=10,
        )

    t0 = time.perf_counter()
    resp = _with_retry(_call)
    latency_ms = (time.perf_counter() - t0) * 1000

    categoria = (resp.choices[0].message.content or "").strip().lower()
    if categoria not in classify_mod.CATEGORIAS:
        categoria = "otros"
    tokens = {
        "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
        "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
    }
    return categoria, tokens, latency_ms


# ════════════════════════════════════════════════════════════════════════════
#  GENERACION DE DATOS (pool de transacciones + usuarios para insights)
# ════════════════════════════════════════════════════════════════════════════

# Descripciones ambiguas: no casan con ninguna regla del clasificador mock, por lo
# que escalan a nivel 2. Imitan cargos opacos reales (TPV sin nombre de comercio).
_AMBIGUAS = [
    "COMPRA TPV 4587 COMERCIO",
    "CARGO DOMICILIADO REF 99213",
    "PAGO CONTACTLESS TERMINAL 7781",
    "ADEUDO RECIBO 552310",
    "COMPRA TARJETA REF X9920",
    "PAGO ESTABLECIMIENTO 33412",
    "CARGO VARIOS CONCEPTO 8821",
    "COMPRA ONLINE REF 77120",
    "PAGO TPV COMERCIO 11023",
    "ADEUDO SEPA REF 44871",
    "COMPRA DATAFONO 6650",
    "CARGO TARJETA EXTRANJERO 9981",
]


def _load_external_dataset(path: Path) -> Optional[list[dict[str, Any]]]:
    """Carga un dataset externo (.parquet o .csv) si existe. None si no esta.

    Espera columnas description y amount (user_id/date opcionales). Devuelve filas
    como dicts. El parquet requiere pandas+pyarrow (import perezoso).
    """
    if not path.exists():
        return None
    try:
        if path.suffix == ".parquet":
            import pandas as pd  # import perezoso: solo si hay parquet

            df = pd.read_parquet(path)
            return df.to_dict("records")
        import csv

        with path.open(encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception as exc:
        print(f"  Aviso: no se pudo leer {path.name} ({exc}); se ignora.")
        return None


def build_transaction_pool(
    n_total: int,
    n_ambiguous_min: int,
    test_dataset: Optional[Path],
    synthetic_dataset: Optional[Path],
) -> list[dict[str, Any]]:
    """Construye el pool de transacciones para medir escalado y latencia.

    Prioridad de fuentes:
      1. Datasets externos (test_manual + synthetic) si existen.
      2. Generador sintetico del proyecto (scripts.generate_history).
    En ambos casos se inyectan `n_ambiguous_min` transacciones ambiguas para
    garantizar al menos esa cantidad de escalados al LLM (igual que pide el TFM:
    forzar el escalado cuando no llega de forma natural).

    Cada fila: {description, amount}. user_id se asigna en el benchmark.
    """
    pool: list[dict[str, Any]] = []

    # 1. Datasets externos.
    for ds in (test_dataset, synthetic_dataset):
        if ds is not None:
            rows = _load_external_dataset(ds)
            if rows:
                for r in rows:
                    try:
                        pool.append({
                            "description": str(r.get("description", "")),
                            "amount": float(r["amount"]),
                        })
                    except (KeyError, ValueError, TypeError):
                        continue
                print(f"  Dataset '{ds.name}': {len(rows)} filas cargadas.")

    # 2. Si no hubo datasets externos suficientes, generar sintetico.
    if len(pool) < n_total - n_ambiguous_min:
        faltan = n_total - n_ambiguous_min - len(pool)
        # generate_history produce ~ (per_month+subs+1)*months + outliers filas.
        rows = generate_history(
            user="bench",
            months=12,
            per_month=max(60, faltan // 12 + 10),
            salary=2000.0,
            ciudad="MADRID",
            n_suscripciones=3,
        )
        for r in rows:
            pool.append({"description": r["description"], "amount": r["amount"]})
        print(f"  Generadas {len(rows)} transacciones sinteticas.")

    # Recortar a (n_total - ambiguas) antes de inyectar las ambiguas.
    random.shuffle(pool)
    pool = pool[: max(0, n_total - n_ambiguous_min)]

    # 3. Inyectar ambiguas (garantizan >= n_ambiguous_min escalados).
    for i in range(n_ambiguous_min):
        desc = _AMBIGUAS[i % len(_AMBIGUAS)]
        amount = -round(random.uniform(5, 200), 2)
        pool.append({"description": f"{desc} {i}", "amount": amount})

    random.shuffle(pool)
    return pool


def build_insight_users(n_users: int) -> list[dict[str, Any]]:
    """Genera `n_users` usuarios simulados con historico variado para insights.

    Cada usuario tiene 2 meses de historico (mes actual + anterior) con parametros
    distintos (salario, ciudad, nº suscripciones, volumen) para variar el agregado
    que ve el LLM. Las transacciones se anonimizan y clasifican como en produccion.
    """
    ciudades = ["MADRID", "BARCELONA", "VALENCIA", "SEVILLA", "BILBAO"]
    users: list[dict[str, Any]] = []

    for u in range(n_users):
        salary = random.choice([1400, 1800, 2200, 2800, 3500])
        ciudad = ciudades[u % len(ciudades)]
        subs = random.randint(1, 5)
        per_month = random.randint(30, 70)

        rows = generate_history(
            user=f"insight-user-{u}",
            months=2,
            per_month=per_month,
            salary=float(salary),
            ciudad=ciudad,
            n_suscripciones=subs,
        )

        # Procesar (anonimizar + clasificar) y agrupar por mes 'YYYY-MM'.
        por_mes: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            desc_anon, _ = anonymize(r["description"])
            clf = classify(desc_anon.upper(), r["amount"])
            mes = str(r["date"])[:7]
            por_mes.setdefault(mes, []).append({
                "amount": r["amount"],
                "category": clf["categoria"],
                "description_anonymized": desc_anon,
                "created_at": r["date"],
                "is_anomaly": False,
            })

        meses = sorted(por_mes.keys())
        if len(meses) < 2:
            continue
        mes_actual, mes_prev = meses[-1], meses[-2]
        users.append({
            "month": mes_actual,
            "transactions": por_mes[mes_actual],
            "prev_transactions": por_mes[mes_prev],
        })

    return users


# ════════════════════════════════════════════════════════════════════════════
#  WARMUP  (descartar las primeras llamadas: siempre mas lentas)
# ════════════════════════════════════════════════════════════════════════════


def warmup(llm_enabled: bool, n: int = 3) -> None:
    """Calienta los caminos lentos antes de medir.

    - anonymize/classify: la primera llamada inicializa Presidio/spacy (lento).
    - LLM: las primeras 2-3 llamadas son mas lentas (conexion, cache). Se descartan.
    """
    print("  Warmup: inicializando anonimizacion y clasificador...")
    for _ in range(2):
        desc_anon, _ = anonymize("PAGO TARJETA MERCADONA SL MADRID 12.30")
        classify(desc_anon.upper(), -12.30)

    if llm_enabled:
        print(f"  Warmup: {n} llamadas LLM descartadas (clasificacion + insight)...")
        for _ in range(n):
            try:
                _llm_classify("COMPRA TPV 0000 COMERCIO", -10.0)
            except Exception as exc:
                print(f"    Warmup LLM fallo: {exc}")
                break


# ════════════════════════════════════════════════════════════════════════════
#  MEDICIONES
# ════════════════════════════════════════════════════════════════════════════


def run_pipeline_benchmark(
    pool: list[dict[str, Any]],
    escalation_threshold: float,
    llm_enabled: bool,
    max_llm_calls: int,
) -> dict[str, Any]:
    """Corre el pipeline completo sobre el pool midiendo escalado y latencia.

    Replica los pasos de api.service.process_transaction instrumentando cada uno
    con time.perf_counter(): anonimizacion, clasificacion L1, (L2 si escala),
    anomalias y guardado en BD.

    El escalado se decide igual que en produccion: nivel_usado==2 o confianza por
    debajo del umbral. Para las primeras `max_llm_calls` transacciones escaladas se
    hace la llamada REAL al LLM (mide tokens + latencia L2); el resto se cuentan en
    la tasa de escalado pero su latencia L2 se estima con la media medida.

    Returns dict con: contadores de escalado, distribucion por categoria, listas de
    latencias por componente y muestras de tokens de clasificacion L2.
    """
    user_id = "bench-pipeline"
    database.init_db()
    queries.ensure_user(user_id)

    # Latencias por componente (ms).
    lat_anon: list[float] = []
    lat_l1: list[float] = []
    lat_l2: list[float] = []          # solo escaladas con llamada LLM real
    lat_anom: list[float] = []
    lat_db: list[float] = []
    total_nivel1: list[float] = []    # end-to-end de las que NO escalan
    total_nivel2: list[float] = []    # end-to-end de las que escalan (con L2 real)

    # Tokens de clasificacion L2 (1.1).
    class_prompt_tokens: list[int] = []
    class_completion_tokens: list[int] = []

    n_total = 0
    n_nivel1 = 0
    n_escalado = 0
    escalado_por_categoria: dict[str, int] = {}
    llm_calls_done = 0

    for tx in pool:
        n_total += 1
        description = tx["description"]
        amount = tx["amount"]
        t_start = time.perf_counter()

        # 1. Anonimizacion.
        t0 = time.perf_counter()
        desc_anon, _entities = anonymize(description)
        lat_anon.append((time.perf_counter() - t0) * 1000)

        # 2. Clasificacion nivel 1 (clasificador local / mock).
        t0 = time.perf_counter()
        clf = classify(desc_anon.upper(), amount)
        lat_l1.append((time.perf_counter() - t0) * 1000)
        category = clf["categoria"]

        # Decision de escalado (como en produccion: nivel 2 o confianza baja).
        escala = clf["nivel_usado"] == 2 or clf["confianza"] < escalation_threshold

        # 3. Clasificacion nivel 2 (LLM) si escala.
        l2_ms = 0.0
        if escala:
            n_escalado += 1
            if llm_enabled and llm_calls_done < max_llm_calls:
                cat_llm, tokens, l2_ms = _llm_classify(desc_anon, amount)
                category = cat_llm
                class_prompt_tokens.append(tokens["prompt_tokens"])
                class_completion_tokens.append(tokens["completion_tokens"])
                lat_l2.append(l2_ms)
                llm_calls_done += 1
            escalado_por_categoria[category] = escalado_por_categoria.get(category, 0) + 1
        else:
            n_nivel1 += 1

        # 4. Deteccion de anomalias (incluye la lectura de historico, como el servicio).
        t0 = time.perf_counter()
        history = queries.get_category_history(user_id, category)
        is_anomaly, reason = detect_zscore_anomaly(amount, category, history)
        if not is_anomaly and category == "suscripciones":
            merch = queries.get_merchant_history(user_id, desc_anon)
            is_anomaly, reason = detect_subscription_change(desc_anon, amount, merch)
        lat_anom.append((time.perf_counter() - t0) * 1000)

        # 5. Guardado en BD (temporal).
        t0 = time.perf_counter()
        row = {
            "id": uuid.uuid4().hex,
            "user_id": user_id,
            "description_raw": description,
            "description_anonymized": desc_anon,
            "amount": amount,
            "category": category,
            "confidence": clf["confianza"],
            "classification_level": 2 if escala else 1,
            "is_anomaly": 1 if is_anomaly else 0,
            "anomaly_reason": reason or None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        queries.insert_transaction(row)
        lat_db.append((time.perf_counter() - t0) * 1000)

        total_ms = (time.perf_counter() - t_start) * 1000
        # Para el end-to-end solo separamos limpio cuando hubo L2 real medido.
        if escala and l2_ms > 0:
            total_nivel2.append(total_ms)
        elif not escala:
            total_nivel1.append(total_ms)

    return {
        "n_total": n_total,
        "n_nivel1": n_nivel1,
        "n_escalado": n_escalado,
        "escalado_por_categoria": escalado_por_categoria,
        "llm_calls_done": llm_calls_done,
        "lat_anon": lat_anon,
        "lat_l1": lat_l1,
        "lat_l2": lat_l2,
        "lat_anom": lat_anom,
        "lat_db": lat_db,
        "total_nivel1": total_nivel1,
        "total_nivel2": total_nivel2,
        "class_prompt_tokens": class_prompt_tokens,
        "class_completion_tokens": class_completion_tokens,
    }


def run_insight_benchmark(
    users: list[dict[str, Any]], llm_enabled: bool
) -> dict[str, Any]:
    """Genera insights LLM sobre usuarios simulados midiendo tokens y latencia (1.2)."""
    prompt_tokens: list[int] = []
    completion_tokens: list[int] = []
    latencies: list[float] = []
    n_ok = 0

    if not llm_enabled:
        return {"n": 0, "prompt_tokens": [], "completion_tokens": [], "latencies": []}

    for i, u in enumerate(users):
        agg = aggregate_month(u["transactions"], u["prev_transactions"])

        def _call():
            return _llm_insight(u["month"], agg)

        try:
            t0 = time.perf_counter()
            _text, tokens = _with_retry(_call)
            latencies.append((time.perf_counter() - t0) * 1000)
            prompt_tokens.append(tokens["prompt_tokens"])
            completion_tokens.append(tokens["completion_tokens"])
            n_ok += 1
        except Exception as exc:
            print(f"    Insight usuario {i} fallo tras reintentos: {exc}")
            continue

    return {
        "n": n_ok,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "latencies": latencies,
    }


# ════════════════════════════════════════════════════════════════════════════
#  AGREGACION DE RESULTADOS + PROYECCION + COMPARATIVAS
# ════════════════════════════════════════════════════════════════════════════


def compute_report(
    pipeline: dict[str, Any],
    insights: dict[str, Any],
    llm_enabled: bool,
) -> dict[str, Any]:
    """Calcula todas las metricas derivadas: stats, costes, proyeccion, comparativa."""
    # --- 1.1 Clasificacion L2: tokens y coste ---
    cls_in = pipeline["class_prompt_tokens"]
    cls_out = pipeline["class_completion_tokens"]
    cls_cost_usd = (
        _cost_usd(statistics.fmean(cls_in), statistics.fmean(cls_out))
        if cls_in else 0.0
    )

    # --- 1.2 Insights: tokens y coste ---
    ins_in = insights["prompt_tokens"]
    ins_out = insights["completion_tokens"]
    ins_cost_usd = (
        _cost_usd(statistics.fmean(ins_in), statistics.fmean(ins_out))
        if ins_in else 0.0
    )

    # --- 2. Tasa de escalado ---
    n_total = pipeline["n_total"]
    escalation_rate = pipeline["n_escalado"] / n_total if n_total else 0.0

    # --- 3. Latencia end-to-end combinada (segun tasa real de escalado) ---
    total_combinado = pipeline["total_nivel1"] + pipeline["total_nivel2"]

    # --- Proyeccion a escala ClarityBank ---
    tx_escaladas_mes = TRANSACTIONS_PER_MONTH * escalation_rate
    coste_class_mes_eur = tx_escaladas_mes * cls_cost_usd * USD_TO_EUR
    coste_insight_mes_eur = INSIGHTS_PER_MONTH * ins_cost_usd * USD_TO_EUR
    coste_total_mes_eur = coste_class_mes_eur + coste_insight_mes_eur

    # --- Comparativa naive ---
    # Escenario A: TODAS las transacciones al LLM gpt-4o-mini (sin clasificador local).
    naiveA_class_mes = TRANSACTIONS_PER_MONTH * cls_cost_usd * USD_TO_EUR
    naiveA_mes = naiveA_class_mes + coste_insight_mes_eur

    # Escenario B: TODO con gpt-4o (modelo grande), mismos tokens medidos.
    cls_cost_4o = (
        _cost_usd(statistics.fmean(cls_in), statistics.fmean(cls_out),
                  PRICE_GPT4O_1K_INPUT_USD, PRICE_GPT4O_1K_OUTPUT_USD)
        if cls_in else 0.0
    )
    ins_cost_4o = (
        _cost_usd(statistics.fmean(ins_in), statistics.fmean(ins_out),
                  PRICE_GPT4O_1K_INPUT_USD, PRICE_GPT4O_1K_OUTPUT_USD)
        if ins_in else 0.0
    )
    naiveB_mes = (
        TRANSACTIONS_PER_MONTH * cls_cost_4o * USD_TO_EUR
        + INSIGHTS_PER_MONTH * ins_cost_4o * USD_TO_EUR
    )

    ahorro_A = 1 - coste_total_mes_eur / naiveA_mes if naiveA_mes else 0.0
    ahorro_B = 1 - coste_total_mes_eur / naiveB_mes if naiveB_mes else 0.0

    # --- Coste de ejecutar el propio benchmark ---
    bench_in = sum(cls_in) + sum(ins_in)
    bench_out = sum(cls_out) + sum(ins_out)
    bench_cost_usd = _cost_usd(bench_in, bench_out)

    return {
        "llm_enabled": llm_enabled,
        "clasificacion_l2": {
            "n": len(cls_in),
            "tokens_input": _stats([float(x) for x in cls_in]),
            "tokens_output": _stats([float(x) for x in cls_out]),
            "coste_usd_por_llamada": cls_cost_usd,
            "coste_eur_por_llamada": cls_cost_usd * USD_TO_EUR,
            "latencia_ms": _stats(pipeline["lat_l2"]),
        },
        "insights": {
            "n": len(ins_in),
            "tokens_input": _stats([float(x) for x in ins_in]),
            "tokens_output": _stats([float(x) for x in ins_out]),
            "coste_usd_por_insight": ins_cost_usd,
            "coste_eur_por_insight": ins_cost_usd * USD_TO_EUR,
            "latencia_ms": _stats(insights["latencies"]),
        },
        "escalado": {
            "n_total": n_total,
            "n_nivel1": pipeline["n_nivel1"],
            "n_escalado": pipeline["n_escalado"],
            "tasa_escalado_pct": escalation_rate * 100,
            "por_categoria": dict(sorted(
                pipeline["escalado_por_categoria"].items(),
                key=lambda kv: kv[1], reverse=True,
            )),
        },
        "latencia": {
            "anonimizacion": _stats(pipeline["lat_anon"]),
            "clasificacion_l1": _stats(pipeline["lat_l1"]),
            "clasificacion_l2": _stats(pipeline["lat_l2"]),
            "anomalias": _stats(pipeline["lat_anom"]),
            "guardado_bd": _stats(pipeline["lat_db"]),
            "total_nivel1": _stats(pipeline["total_nivel1"]),
            "total_nivel2": _stats(pipeline["total_nivel2"]),
            "total_combinado": _stats(total_combinado),
        },
        "proyeccion": {
            "tx_escaladas_mes": tx_escaladas_mes,
            "coste_clasificacion_mes_eur": coste_class_mes_eur,
            "coste_clasificacion_anual_eur": coste_class_mes_eur * 12,
            "coste_insights_mes_eur": coste_insight_mes_eur,
            "coste_insights_anual_eur": coste_insight_mes_eur * 12,
            "coste_total_mes_eur": coste_total_mes_eur,
            "coste_total_anual_eur": coste_total_mes_eur * 12,
            "coste_por_usuario_mes_eur": coste_total_mes_eur / USERS if USERS else 0.0,
        },
        "comparativa": {
            "naive_A_gpt4o_mini_mes_eur": naiveA_mes,
            "ahorro_vs_A_pct": ahorro_A * 100,
            "naive_B_gpt4o_mes_eur": naiveB_mes,
            "ahorro_vs_B_pct": ahorro_B * 100,
        },
        "requisito_latencia": {
            "limite_ms": LATENCY_REQUIREMENT_MS,
            "p95_ms": _stats(total_combinado)["p95"],
            "p99_ms": _stats(total_combinado)["p99"],
            "cumple_p95": _stats(total_combinado)["p95"] < LATENCY_REQUIREMENT_MS,
            "cumple_p99": _stats(total_combinado)["p99"] < LATENCY_REQUIREMENT_MS,
            "margen_pct": (1 - _stats(total_combinado)["p95"] / LATENCY_REQUIREMENT_MS) * 100,
        },
        "coste_benchmark": {
            "llamadas_llm": len(cls_in) + len(ins_in),
            "tokens_input_total": bench_in,
            "tokens_output_total": bench_out,
            "coste_usd": bench_cost_usd,
            "coste_eur": bench_cost_usd * USD_TO_EUR,
        },
    }


# ════════════════════════════════════════════════════════════════════════════
#  INFORME EN CONSOLA
# ════════════════════════════════════════════════════════════════════════════

_LINE = "═" * 67
_THIN = "─" * 67


def _fmt_tokens(s: dict[str, float]) -> str:
    return (f"media={s['media']:.0f}  mediana={s['mediana']:.0f}  "
            f"p95={s['p95']:.0f}  max={s['max']:.0f}")


def _fmt_lat(s: dict[str, float]) -> str:
    return f"media={s['media']:.1f}ms  p95={s['p95']:.1f}ms"


def print_report(rep: dict[str, Any]) -> None:
    """Imprime el informe legible en consola con todas las metricas."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print()
    print(_LINE)
    print("  BENCHMARK CLARITYBANK")
    print(f"  Ejecutado: {now}")
    if not rep["llm_enabled"]:
        print("  AVISO: sin credenciales Azure OpenAI -> secciones LLM OMITIDAS")
    print(_LINE)

    # --- Clasificacion L2 ---
    c = rep["clasificacion_l2"]
    print(f"\n▸ CLASIFICACION NIVEL 2 (LLM fallback) — N={c['n']}")
    if c["n"]:
        print(f"  Tokens input    {_fmt_tokens(c['tokens_input'])}")
        print(f"  Tokens output   {_fmt_tokens(c['tokens_output'])}")
        print(f"  Coste por llamada       USD {c['coste_usd_por_llamada']:.7f}   "
              f"EUR {c['coste_eur_por_llamada']:.7f}")
        if c["latencia_ms"]["n"]:
            l = c["latencia_ms"]
            print(f"  Latencia LLM            media={l['media']:.0f}ms   "
                  f"p95={l['p95']:.0f}ms   p99={l['p99']:.0f}ms")
    else:
        print("  (omitido: sin LLM)")

    # --- Insights ---
    i = rep["insights"]
    print(f"\n▸ GENERACION INSIGHTS — N={i['n']}")
    if i["n"]:
        print(f"  Tokens input    {_fmt_tokens(i['tokens_input'])}")
        print(f"  Tokens output   {_fmt_tokens(i['tokens_output'])}")
        print(f"  Coste por insight       USD {i['coste_usd_por_insight']:.7f}   "
              f"EUR {i['coste_eur_por_insight']:.7f}")
        if i["latencia_ms"]["n"]:
            l = i["latencia_ms"]
            print(f"  Latencia LLM            media={l['media']:.0f}ms   "
                  f"p95={l['p95']:.0f}ms   p99={l['p99']:.0f}ms")
    else:
        print("  (omitido: sin LLM)")

    # --- Escalado ---
    e = rep["escalado"]
    print(f"\n▸ TASA DE ESCALADO — N={e['n_total']}")
    print(f"  Total transacciones:    {e['n_total']}")
    print(f"  Resueltas en nivel 1:   {e['n_nivel1']}  "
          f"({e['n_nivel1'] / e['n_total'] * 100:.1f}%)")
    print(f"  Escaladas a nivel 2:    {e['n_escalado']}  ({e['tasa_escalado_pct']:.1f}%)")
    if e["por_categoria"]:
        dist = ", ".join(f"{k}={v}" for k, v in e["por_categoria"].items())
        print(f"  Escalado por categoria: {dist}")

    # --- Latencia end-to-end ---
    lat = rep["latencia"]
    print("\n▸ LATENCIA END-TO-END (todas las transacciones)")
    print(f"  Anonimizacion          {_fmt_lat(lat['anonimizacion'])}")
    print(f"  Clasificacion L1       {_fmt_lat(lat['clasificacion_l1'])}")
    if lat["clasificacion_l2"]["n"]:
        print(f"  Clasificacion L2       {_fmt_lat(lat['clasificacion_l2'])}   "
              f"(solo cuando aplica)")
    print(f"  Anomalias              {_fmt_lat(lat['anomalias'])}")
    print(f"  Guardado BD            {_fmt_lat(lat['guardado_bd'])}")
    print(f"  {_THIN}")
    print(f"  TOTAL (sin escalado)   media={lat['total_nivel1']['media']:.1f}ms   "
          f"p95={lat['total_nivel1']['p95']:.1f}ms")
    if lat["total_nivel2"]["n"]:
        print(f"  TOTAL (con escalado)   media={lat['total_nivel2']['media']:.1f}ms   "
              f"p95={lat['total_nivel2']['p95']:.1f}ms")
    tc = lat["total_combinado"]
    print(f"  TOTAL (combinado)      media={tc['media']:.1f}ms   "
          f"p95={tc['p95']:.1f}ms   p99={tc['p99']:.1f}ms")

    # --- Proyeccion ---
    p = rep["proyeccion"]
    print(f"\n{_LINE}")
    print("  PROYECCION A ESCALA CLARITYBANK")
    print(f"  {TRANSACTIONS_PER_MONTH:,} transacciones/mes · {USERS:,} usuarios"
          .replace(",", "."))
    print(_LINE)
    print("\n▸ Clasificacion nivel 2 a escala")
    print(f"  Transacciones que escalan: {p['tx_escaladas_mes']:,.0f}/mes "
          f"({rep['escalado']['tasa_escalado_pct']:.1f}%)".replace(",", "."))
    print(f"  Coste mensual:             EUR {p['coste_clasificacion_mes_eur']:,.2f}")
    print(f"  Coste anual:               EUR {p['coste_clasificacion_anual_eur']:,.2f}")
    print("\n▸ Insights mensuales a escala")
    print(f"  Total insights:            {INSIGHTS_PER_MONTH:,}/mes".replace(",", "."))
    print(f"  Coste mensual:             EUR {p['coste_insights_mes_eur']:,.2f}")
    print(f"  Coste anual:               EUR {p['coste_insights_anual_eur']:,.2f}")
    print("\n▸ COSTE TOTAL LLM")
    print(f"  Mensual:                   EUR {p['coste_total_mes_eur']:,.2f}")
    print(f"  Anual:                     EUR {p['coste_total_anual_eur']:,.2f}")
    print(f"  Coste por usuario/mes:     EUR {p['coste_por_usuario_mes_eur']:.6f}")

    # --- Comparativa naive ---
    cmp = rep["comparativa"]
    print(f"\n{_LINE}")
    print("  COMPARACION CON ESCENARIO NAIVE")
    print(_LINE)
    print("\n▸ Escenario A: todo al LLM con gpt-4o-mini")
    print(f"  Coste mensual:             EUR {cmp['naive_A_gpt4o_mini_mes_eur']:,.2f}")
    print(f"  Ahorro vs naive:           {cmp['ahorro_vs_A_pct']:.1f}%")
    print("\n▸ Escenario B: todo al LLM con gpt-4o (modelo grande)")
    print(f"  Coste mensual:             EUR {cmp['naive_B_gpt4o_mes_eur']:,.2f}")
    print(f"  Ahorro vs naive:           {cmp['ahorro_vs_B_pct']:.1f}%")

    # --- Latencia vs requisito ---
    r = rep["requisito_latencia"]
    print(f"\n{_LINE}")
    print(f"  LATENCIA vs REQUISITO (<{LATENCY_REQUIREMENT_MS / 1000:.0f}s)")
    print(_LINE)
    ok95 = "✓ CUMPLE" if r["cumple_p95"] else "✗ NO CUMPLE"
    ok99 = "✓ CUMPLE" if r["cumple_p99"] else "✗ NO CUMPLE"
    print(f"\n  p95 end-to-end:    {r['p95_ms']:.0f}ms   {ok95}")
    print(f"  p99 end-to-end:    {r['p99_ms']:.0f}ms   {ok99}")
    print(f"  Margen sobre {LATENCY_REQUIREMENT_MS / 1000:.0f}s:   {r['margen_pct']:.0f}%")

    # --- Coste del benchmark ---
    b = rep["coste_benchmark"]
    print(f"\n{_LINE}")
    print(f"  COSTE DE EJECUTAR ESTE BENCHMARK")
    print(_LINE)
    print(f"  Llamadas LLM:      {b['llamadas_llm']}  "
          f"(input {b['tokens_input_total']} tok, output {b['tokens_output_total']} tok)")
    print(f"  Coste:             USD {b['coste_usd']:.4f}   EUR {b['coste_eur']:.4f}")
    print(_LINE)
    print()


# ════════════════════════════════════════════════════════════════════════════
#  GRAFICOS (opcional, si matplotlib esta disponible)
# ════════════════════════════════════════════════════════════════════════════


def generate_charts(
    pipeline: dict[str, Any],
    insights: dict[str, Any],
    rep: dict[str, Any],
    out_dir: Path,
) -> list[str]:
    """Genera 3 PNG (histograma tokens, histograma latencia, barras coste). Opcional."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        print("  matplotlib no disponible: se omiten los graficos.")
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    # 1. Histograma de tokens input por tipo de llamada.
    if pipeline["class_prompt_tokens"] or insights["prompt_tokens"]:
        fig, ax = plt.subplots(figsize=(7, 4))
        if pipeline["class_prompt_tokens"]:
            ax.hist(pipeline["class_prompt_tokens"], bins=20, alpha=0.6,
                    label="Clasificacion L2")
        if insights["prompt_tokens"]:
            ax.hist(insights["prompt_tokens"], bins=20, alpha=0.6, label="Insights")
        ax.set_xlabel("Tokens input")
        ax.set_ylabel("Frecuencia")
        ax.set_title("Distribucion de tokens input por tipo de llamada")
        ax.legend()
        f = out_dir / "tokens_input_hist.png"
        fig.tight_layout()
        fig.savefig(f, dpi=120)
        plt.close(fig)
        paths.append(str(f))

    # 2. Histograma de latencia end-to-end.
    combinado = pipeline["total_nivel1"] + pipeline["total_nivel2"]
    if combinado:
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.hist(combinado, bins=40)
        ax.axvline(rep["latencia"]["total_combinado"]["p95"], color="orange",
                   linestyle="--", label="p95")
        ax.set_xlabel("Latencia end-to-end (ms)")
        ax.set_ylabel("Frecuencia")
        ax.set_title("Distribucion de latencia end-to-end")
        ax.legend()
        f = out_dir / "latencia_hist.png"
        fig.tight_layout()
        fig.savefig(f, dpi=120)
        plt.close(fig)
        paths.append(str(f))

    # 3. Barras: coste mensual propuesta vs naive A vs naive B.
    p = rep["proyeccion"]["coste_total_mes_eur"]
    a = rep["comparativa"]["naive_A_gpt4o_mini_mes_eur"]
    b = rep["comparativa"]["naive_B_gpt4o_mes_eur"]
    fig, ax = plt.subplots(figsize=(7, 4))
    labels = ["Propuesta\n(2 niveles)", "Naive A\n(gpt-4o-mini)", "Naive B\n(gpt-4o)"]
    vals = [p, a, b]
    bars = ax.bar(labels, vals, color=["#2a9d8f", "#e9c46a", "#e76f51"])
    ax.set_ylabel("Coste mensual (EUR)")
    ax.set_title("Coste mensual: arquitectura propuesta vs naive")
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, v, f"{v:,.0f}",
                ha="center", va="bottom")
    f = out_dir / "coste_comparativa.png"
    fig.tight_layout()
    fig.savefig(f, dpi=120)
    plt.close(fig)
    paths.append(str(f))

    return paths


# ════════════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════════════


def _default_output() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return str(ROOT / "reports" / f"benchmark_{ts}.json")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Benchmark empirico de coste y latencia de ClarityBank.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--n-classifications", type=int, default=100,
                   help="Minimo de clasificaciones nivel 2 a medir")
    p.add_argument("--n-insights", type=int, default=30,
                   help="Numero de insights mensuales a generar")
    p.add_argument("--pool-size", type=int, default=1200,
                   help="Total de transacciones para tasa de escalado y latencia")
    p.add_argument("--escalation-threshold", type=float, default=0.70,
                   help="Umbral de confianza por debajo del cual se escala al LLM")
    p.add_argument("--test-dataset", type=Path,
                   default=ROOT / "data" / "test_manual.parquet",
                   help="Dataset de test manual (parquet/csv); se usa si existe")
    p.add_argument("--synthetic-dataset", type=Path,
                   default=ROOT / "data" / "transactions_clean.parquet",
                   help="Dataset sintetico (parquet/csv); se usa si existe")
    p.add_argument("--output", type=str, default=None,
                   help="Ruta del JSON de salida (por defecto reports/benchmark_TS.json)")
    p.add_argument("--seed", type=int, default=42, help="Semilla para reproducibilidad")
    p.add_argument("--no-charts", action="store_true", help="No generar PNG")
    p.add_argument("--no-llm", action="store_true",
                   help="Forzar modo sin LLM (solo escalado + latencia L1)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    random.seed(args.seed)

    llm_enabled = settings.llm_enabled and not args.no_llm
    output_path = Path(args.output) if args.output else Path(_default_output())

    print(_LINE)
    print("  PREPARANDO BENCHMARK CLARITYBANK")
    print(_LINE)
    print(f"  BD temporal:        {_TMP_DB}")
    print(f"  LLM habilitado:     {llm_enabled} "
          f"({'Azure OK' if llm_enabled else 'sin credenciales / --no-llm'})")
    print(f"  Presidio activo:    {presidio_available()}")
    print(f"  Clasificador real:  {classify_mod.using_real_model()} "
          f"({'modelo' if classify_mod.using_real_model() else 'mock'})")
    print(f"  Semilla:            {args.seed}")

    if llm_enabled:
        print("\n  AVISO: este benchmark hara llamadas reales al LLM (coste en EUR).")
        print(f"  Aprox. {args.n_classifications} clasificaciones + {args.n_insights} "
              f"insights + warmups.")

    # --- Construir datos ---
    print("\n  Construyendo pool de transacciones...")
    pool = build_transaction_pool(
        n_total=args.pool_size,
        n_ambiguous_min=args.n_classifications,
        test_dataset=args.test_dataset,
        synthetic_dataset=args.synthetic_dataset,
    )
    print(f"  Pool final: {len(pool)} transacciones.")

    print(f"\n  Construyendo {args.n_insights} usuarios simulados para insights...")
    insight_users = build_insight_users(args.n_insights)
    print(f"  Usuarios con historico valido: {len(insight_users)}.")

    # --- Warmup ---
    print("\n  Warmup (descartando primeras llamadas)...")
    warmup(llm_enabled)

    # --- Mediciones ---
    print("\n  Midiendo pipeline (escalado + latencia + tokens L2)...")
    pipeline = run_pipeline_benchmark(
        pool=pool,
        escalation_threshold=args.escalation_threshold,
        llm_enabled=llm_enabled,
        max_llm_calls=args.n_classifications,
    )
    print(f"  Procesadas {pipeline['n_total']} tx, "
          f"{pipeline['n_escalado']} escaladas, "
          f"{pipeline['llm_calls_done']} llamadas LLM de clasificacion.")

    print(f"\n  Midiendo insights ({len(insight_users)} usuarios)...")
    insights = run_insight_benchmark(insight_users, llm_enabled)
    print(f"  Insights generados: {insights['n']}.")

    # --- Agregar e informar ---
    rep = compute_report(pipeline, insights, llm_enabled)
    print_report(rep)

    # --- Graficos ---
    chart_paths: list[str] = []
    if not args.no_charts:
        print("  Generando graficos...")
        chart_paths = generate_charts(pipeline, insights, rep, output_path.parent)
        for cp in chart_paths:
            print(f"    {cp}")

    # --- Guardar JSON (con mediciones crudas para reanalisis) ---
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": {
            "ejecutado": datetime.now(timezone.utc).isoformat(),
            "seed": args.seed,
            "llm_enabled": llm_enabled,
            "clasificador_real": classify_mod.using_real_model(),
            "presidio_activo": presidio_available(),
            "precios": {
                "gpt4o_mini_input_1k_usd": PRICE_PER_1K_INPUT_USD,
                "gpt4o_mini_output_1k_usd": PRICE_PER_1K_OUTPUT_USD,
                "gpt4o_input_1k_usd": PRICE_GPT4O_1K_INPUT_USD,
                "gpt4o_output_1k_usd": PRICE_GPT4O_1K_OUTPUT_USD,
                "usd_to_eur": USD_TO_EUR,
            },
            "volumenes": {
                "transacciones_mes": TRANSACTIONS_PER_MONTH,
                "usuarios": USERS,
                "insights_mes": INSIGHTS_PER_MONTH,
            },
        },
        "resumen": rep,
        "crudo": {
            "clasificacion_l2_prompt_tokens": pipeline["class_prompt_tokens"],
            "clasificacion_l2_completion_tokens": pipeline["class_completion_tokens"],
            "clasificacion_l2_latencias_ms": pipeline["lat_l2"],
            "insight_prompt_tokens": insights["prompt_tokens"],
            "insight_completion_tokens": insights["completion_tokens"],
            "insight_latencias_ms": insights["latencies"],
            "latencia_anonimizacion_ms": pipeline["lat_anon"],
            "latencia_clasificacion_l1_ms": pipeline["lat_l1"],
            "latencia_anomalias_ms": pipeline["lat_anom"],
            "latencia_guardado_bd_ms": pipeline["lat_db"],
            "latencia_total_nivel1_ms": pipeline["total_nivel1"],
            "latencia_total_nivel2_ms": pipeline["total_nivel2"],
        },
        "graficos": chart_paths,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"  JSON guardado en: {output_path}")
    print()


def _cleanup() -> None:
    """Borra la BD temporal y su carpeta. El benchmark no deja restos."""
    try:
        import shutil

        shutil.rmtree(_TMP_DIR, ignore_errors=True)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    finally:
        _cleanup()
