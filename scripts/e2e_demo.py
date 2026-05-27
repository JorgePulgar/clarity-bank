"""Demo end-to-end real de ClarityBank.

Arranca la API en subprocess, ejercita el pipeline completo via HTTP y
muestra metricas finales. Logging narrativo para presentacion oral.

Uso:
    python scripts/e2e_demo.py
"""
from __future__ import annotations

import csv
import io
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEMO_USER = "demo-presentation"
API_PORT = 8765
API_BASE = f"http://127.0.0.1:{API_PORT}"
HEALTHCHECK_TIMEOUT = 30  # segundos maximos esperando a que arranque la API

# 5 transacciones de demo, cada una representa un escenario distinto del pipeline.
DEMO_TRANSACTIONS: list[tuple[str, str, float]] = [
    # (etiqueta, descripcion, importe)
    ("CLARA",        "MERCADONA SUPERMERCADOS MADRID",       -43.27),
    ("AMBIGUA",      "REINTEGRO CONCEPTOS VARIOS CUENTA",    150.00),
    ("ESCALADA LLM", "CUOTA ASOCIACION CULTURAL MADRID",     -80.00),
    ("ANOMALA",      "AMAZON COMPRA ONLINE",                -1450.00),
    ("NORMAL",       "NETFLIX SUSCRIPCION MENSUAL",          -12.99),
]


# ---------------------------------------------------------------------------
# Utilidades de presentacion
# ---------------------------------------------------------------------------

def _sep(title: str = "", index: str = "") -> None:
    """Imprime un separador de seccion con titulo opcional."""
    print(f"\n{'='*62}")
    if title:
        prefix = f"[{index}] " if index else "  "
        print(f"  {prefix}{title}")
        print("=" * 62)


def _tick() -> float:
    """Devuelve timestamp actual en segundos (para medir duracion)."""
    return time.monotonic()


# ---------------------------------------------------------------------------
# Pasos del demo
# ---------------------------------------------------------------------------

def _cleanup_demo_user() -> None:
    """Elimina datos previos del usuario demo para que cada ejecucion sea reproducible."""
    from api.db import init_db
    from api.db.database import get_connection

    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM transactions WHERE user_id = ?", (DEMO_USER,))
        conn.execute("DELETE FROM insight_calls WHERE user_id = ?", (DEMO_USER,))
        conn.execute("DELETE FROM users WHERE id = ?", (DEMO_USER,))
    print(f"  Usuario '{DEMO_USER}' reiniciado (datos previos eliminados).")


def _start_api() -> subprocess.Popen:
    """Arranca uvicorn como subprocess en el puerto configurado."""
    _sep("Arrancando API", "1/5")
    cmd = [
        sys.executable, "-m", "uvicorn",
        "api.main:app",
        "--host", "127.0.0.1",
        "--port", str(API_PORT),
        "--log-level", "warning",
    ]
    print(f"  CMD: {' '.join(cmd)}")
    return subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def _wait_for_api(proc: subprocess.Popen) -> dict:
    """Polling sobre /health hasta que la API responde o se agota el timeout.

    Returns:
        dict con el payload de /health (classifier, anonymization, insights).
    """
    t0 = _tick()
    print(f"  Esperando en {API_BASE}/health ", end="", flush=True)
    deadline = time.time() + HEALTHCHECK_TIMEOUT
    while time.time() < deadline:
        if proc.poll() is not None:
            stderr = (proc.stderr.read() or b"").decode()
            print(f"\n  ERROR: proceso termino con codigo {proc.returncode}")
            if stderr:
                print(f"  STDERR:\n{stderr[:800]}")
            sys.exit(1)
        try:
            resp = requests.get(f"{API_BASE}/health", timeout=2)
            if resp.status_code == 200:
                elapsed = _tick() - t0
                print(f" OK  ({elapsed:.1f} s)")
                health = resp.json()
                print(f"  Clasificador:    {health['classifier']}")
                print(f"  Anonimizacion:   {health['anonymization']}")
                print(f"  Insights:        {health['insights']}")
                return health
        except requests.ConnectionError:
            pass
        print(".", end="", flush=True)
        time.sleep(1)

    print("\n  ERROR: timeout esperando la API")
    proc.terminate()
    sys.exit(1)


def _import_history() -> int:
    """Genera historico simulado (6 meses) e importa via POST /transactions/import.

    Returns:
        Numero de transacciones procesadas correctamente.
    """
    _sep("Cargando historico (6 meses, ~143 transacciones)", "2/5")
    from scripts.generate_history import generate  # namespace package (Python 3.3+)

    random.seed(42)
    rows = generate(
        user=DEMO_USER,
        months=6,
        per_month=20,
        salary=2000.0,
        ciudad="MADRID",
        n_suscripciones=3,
    )
    print(f"  Generadas {len(rows)} transacciones. Importando...", end="", flush=True)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["user_id", "description", "amount", "date"])
    writer.writeheader()
    writer.writerows(rows)

    t0 = _tick()
    resp = requests.post(
        f"{API_BASE}/transactions/import",
        files={"file": ("history.csv", buf.getvalue().encode("utf-8"), "text/csv")},
        timeout=180,
    )
    resp.raise_for_status()
    result = resp.json()
    elapsed = _tick() - t0

    print(f" OK  ({elapsed:.1f} s)")
    print(
        f"  Recibidas: {result['received']}  "
        f"Procesadas: {result['processed']}  "
        f"Anomalias historicas: {result['anomalies']}"
    )
    if result["errors"]:
        print(f"  Errores (max 3): {result['errors'][:3]}")
    return result["processed"]


def _process_demo_transactions() -> list[dict]:
    """Envia las 5 transacciones de demo por POST /transactions y muestra el resultado.

    Returns:
        Lista de dicts con las respuestas de la API.
    """
    _sep("Transacciones de demo", "3/5")
    results: list[dict] = []

    for label, desc, amount in DEMO_TRANSACTIONS:
        resp = requests.post(
            f"{API_BASE}/transactions",
            json={"user_id": DEMO_USER, "description": desc, "amount": amount},
            timeout=30,
        )
        resp.raise_for_status()
        tx = resp.json()

        anomaly_flag = "  <-- ANOMALIA" if tx["is_anomaly"] else ""
        print(
            f"  [{label:<12}] {tx['category']:<16} L{tx['classification_level']} "
            f"{tx['confidence']:.0%}  {amount:>10.2f} EUR{anomaly_flag}"
        )
        if tx["description_anonymized"] != desc:
            print(f"               anonimizado: {tx['description_anonymized']}")
        if tx["anomaly_reason"]:
            print(f"               razon:       {tx['anomaly_reason']}")
        results.append(tx)

    return results


def _generate_insight(month: str) -> dict:
    """Llama a POST /insights/generate y muestra el texto generado.

    Args:
        month: mes en formato YYYY-MM.

    Returns:
        dict con la respuesta del endpoint.
    """
    _sep(f"Insight mensual ({month})", "4/5")
    t0 = _tick()
    resp = requests.post(
        f"{API_BASE}/insights/generate",
        json={"user_id": DEMO_USER, "month": month},
        timeout=60,
    )
    resp.raise_for_status()
    elapsed = _tick() - t0
    insight = resp.json()

    print(
        f"  Fuente: {insight['source']}  "
        f"Transacciones: {insight['n_transactions']}  "
        f"({elapsed:.1f} s)"
    )
    if insight.get("cost_eur_estimate") is not None:
        print(f"  Coste LLM: {insight['cost_eur_estimate']:.6f} EUR")
    print()
    print(insight["text"])
    return insight


def _print_summary(health: dict, n_imported: int, demo_results: list[dict]) -> None:
    """Recupera stats de la API y muestra el resumen de metricas de la demo."""
    _sep("Metricas finales", "5/5")

    stats_resp = requests.get(f"{API_BASE}/users/{DEMO_USER}/stats", timeout=10)
    cost_resp = requests.get(f"{API_BASE}/users/{DEMO_USER}/cost-stats", timeout=10)
    stats_resp.raise_for_status()
    cost_resp.raise_for_status()
    stats = stats_resp.json()
    costs = cost_resp.json()

    n_tx = stats["n_transactions"]
    pct_llm = costs["n_llm_calls"] / max(n_tx, 1) * 100

    print("  Componentes activos:")
    print(f"    Clasificador:   {health['classifier']}")
    print(f"    Anonimizacion:  {health['anonymization']}")
    print(f"    Insights:       {health['insights']}")

    print()
    print(f"  Transacciones totales:  {n_tx}")
    print(f"    Historico importado:  {n_imported}")
    print(f"    Demo (5 nuevas):      {len(demo_results)}")
    print(f"  Total gastos:   {stats['total_gastos']:.2f} EUR")
    print(f"  Total ingresos: {stats['total_ingresos']:.2f} EUR")
    print(f"  Anomalias:      {stats['n_anomalies']}")

    print()
    print(f"  Llamadas LLM:        {costs['n_llm_calls']} / {n_tx} ({pct_llm:.1f}%)")
    print(f"  Insights generados:  {costs['n_insights']}")
    print(f"  Coste total:         {costs['total_cost_eur']:.6f} EUR")

    print()
    print("  Top 5 categorias por volumen:")
    for cat in stats["by_category"][:5]:
        bar = "#" * min(30, max(1, int(abs(cat["total"]) / 150)))
        print(f"    {cat['category']:<18} {cat['n']:>3} tx  {cat['total']:>10.2f} EUR  {bar}")


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def main() -> None:
    """Orquesta el flujo completo de la demo end-to-end."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    _sep(f"ClarityBank - Demo end-to-end  |  {now}")

    _cleanup_demo_user()

    proc = _start_api()
    try:
        health = _wait_for_api(proc)
        n_imported = _import_history()
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        demo_results = _process_demo_transactions()
        _generate_insight(month)
        _print_summary(health, n_imported, demo_results)

        _sep("Demo completada correctamente")
        print(f"  API docs:  {API_BASE}/docs")
        print()

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
