"""Genera un historico simulado de transacciones para la demo.

Salida: CSV en data/history_<user>.csv con cabeceras user_id, description, amount, date.
Se puede importar luego por POST /transactions/import o desde el dashboard.

Uso:
    python scripts/generate_history.py --user user_demo --months 3 --per-month 40
"""
from __future__ import annotations

import argparse
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (descripcion plantilla, rango_importe, peso). Importes negativos = gasto.
COMERCIOS = [
    ("PAGO TARJETA MERCADONA SL MADRID", (-90, -15), 8),
    ("CARREFOUR EXPRESS COMPRA", (-60, -10), 5),
    ("LIDL SUPERMERCADOS", (-50, -8), 4),
    ("MCDONALDS RESTAURANTE", (-25, -7), 3),
    ("GLOVO PEDIDO COMIDA", (-35, -12), 3),
    ("BAR LA ESQUINA", (-30, -6), 4),
    ("UBER TRIP", (-20, -5), 3),
    ("RENFE CERCANIAS BILLETE", (-15, -2), 3),
    ("REPSOL GASOLINERA", (-70, -30), 2),
    ("NETFLIX SUSCRIPCION", (-13, -13), 1),
    ("SPOTIFY PREMIUM", (-11, -11), 1),
    ("AMAZON COMPRA ONLINE", (-120, -10), 4),
    ("ZARA TIENDA", (-90, -20), 2),
    ("IBERDROLA FACTURA LUZ", (-95, -45), 1),
    ("MOVISTAR FACTURA FIBRA", (-55, -40), 1),
    ("FARMACIA CENTRAL", (-40, -5), 2),
    ("BIZUM A AMIGO", (-50, -5), 2),
    ("TRANSFERENCIA ALQUILER PISO", (-850, -650), 1),
    ("AEAT IMPUESTO IRPF", (-300, -50), 1),
]
NOMINA = ("ABONO NOMINA EMPRESA SL", (1600, 2200))


def _rand_amount(rng: tuple[float, float]) -> float:
    lo, hi = rng
    return round(random.uniform(lo, hi), 2)


def generate(user: str, months: int, per_month: int) -> list[dict]:
    poblacion = [c for c in COMERCIOS for _ in range(c[2])]
    rows: list[dict] = []
    hoy = datetime.utcnow().replace(day=1)

    for m in range(months):
        # mes objetivo (hacia atras desde el mes actual)
        base = (hoy - timedelta(days=31 * m)).replace(day=1)
        # nomina al inicio del mes
        desc, rng = NOMINA
        rows.append(_row(user, desc, _rand_amount(rng), base + timedelta(days=1)))
        # gastos repartidos
        for _ in range(per_month):
            desc, rng, _w = random.choice(poblacion)
            dia = random.randint(1, 27)
            rows.append(_row(user, desc, _rand_amount(rng), base + timedelta(days=dia)))

    # una anomalia clara: compra muy grande
    rows.append(_row(user, "AMAZON COMPRA ONLINE", -1450.00, hoy + timedelta(days=2)))
    return rows


def _row(user: str, desc: str, amount: float, dt: datetime) -> dict:
    return {
        "user_id": user,
        "description": desc,
        "amount": amount,
        "date": dt.isoformat(),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Genera historico simulado (CSV).")
    p.add_argument("--user", default="user_demo")
    p.add_argument("--months", type=int, default=3)
    p.add_argument("--per-month", type=int, default=40)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    random.seed(args.seed)
    rows = generate(args.user, args.months, args.per_month)

    out = ROOT / "data" / f"history_{args.user}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["user_id", "description", "amount", "date"])
        w.writeheader()
        w.writerows(rows)

    print(f"Generadas {len(rows)} transacciones -> {out}")


if __name__ == "__main__":
    main()
