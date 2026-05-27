"""Genera un historico simulado de transacciones para la demo.

Salida: CSV en data/history_<user>.csv con cabeceras user_id, description, amount, date.
Se puede importar por POST /transactions/import o desde el dashboard.

Uso:
    python scripts/generate_history.py --user-id demo-user
    python scripts/generate_history.py --user-id u1 --months 6 --salary 2800 --city BARCELONA
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _comercios(ciudad: str) -> list[tuple[str, tuple[float, float], int]]:
    """Devuelve la lista de comercios parametrizada por ciudad."""
    return [
        (f"PAGO TARJETA MERCADONA SL {ciudad}", (-90.0, -15.0), 8),
        (f"CARREFOUR EXPRESS {ciudad}", (-60.0, -10.0), 5),
        ("LIDL SUPERMERCADOS", (-50.0, -8.0), 4),
        ("MCDONALDS RESTAURANTE", (-25.0, -7.0), 3),
        ("GLOVO PEDIDO COMIDA", (-35.0, -12.0), 3),
        (f"BAR LA ESQUINA {ciudad}", (-30.0, -6.0), 4),
        ("UBER TRIP", (-20.0, -5.0), 3),
        ("RENFE CERCANIAS BILLETE", (-15.0, -2.0), 3),
        ("REPSOL GASOLINERA", (-70.0, -30.0), 2),
        ("AMAZON COMPRA ONLINE", (-120.0, -10.0), 4),
        (f"ZARA TIENDA {ciudad}", (-90.0, -20.0), 2),
        ("IBERDROLA FACTURA LUZ", (-95.0, -45.0), 1),
        ("MOVISTAR FACTURA FIBRA", (-55.0, -40.0), 1),
        ("FARMACIA CENTRAL", (-40.0, -5.0), 2),
        (f"TRANSFERENCIA ALQUILER PISO {ciudad}", (-850.0, -650.0), 1),
        ("AEAT IMPUESTO IRPF", (-300.0, -50.0), 1),
    ]


SUSCRIPCIONES_DISPONIBLES = [
    ("NETFLIX SUSCRIPCION", -13.99),
    ("SPOTIFY PREMIUM", -10.99),
    ("AMAZON PRIME", -4.99),
    ("HBO MAX SUSCRIPCION", -8.99),
    ("APPLE ICLOUD ALMACENAMIENTO", -0.99),
]


def _rand_amount(rng: tuple[float, float]) -> float:
    lo, hi = rng
    return round(random.uniform(lo, hi), 2)


def _row(user: str, desc: str, amount: float, dt: datetime) -> dict:
    return {
        "user_id": user,
        "description": desc,
        "amount": amount,
        "date": dt.isoformat(),
    }


def generate(
    user: str,
    months: int,
    per_month: int,
    salary: float,
    ciudad: str,
    n_suscripciones: int,
) -> list[dict]:
    """Genera rows de transacciones con outliers intencionados."""
    comercios = _comercios(ciudad)
    poblacion = [c for c in comercios for _ in range(c[2])]
    suscripciones = SUSCRIPCIONES_DISPONIBLES[:n_suscripciones]
    rows: list[dict] = []
    hoy = datetime.now(UTC).replace(day=1)

    for m in range(months):
        base = (hoy - timedelta(days=31 * m)).replace(day=1)

        # Nomina al inicio del mes
        rows.append(
            _row(
                user,
                f"ABONO NOMINA EMPRESA SL {ciudad}",
                salary,
                base + timedelta(days=1),
            )
        )

        # Suscripciones fijas el dia 5
        for desc, importe in suscripciones:
            rows.append(_row(user, desc, importe, base + timedelta(days=5)))

        # Gastos aleatorios
        for _ in range(per_month):
            desc, rng, _w = random.choice(poblacion)
            dia = random.randint(1, 27)
            rows.append(_row(user, desc, _rand_amount(rng), base + timedelta(days=dia)))

    # ---- Outliers intencionados (3-5 segun parametros) ----------------------

    # 1. Compra online muy grande (z-score alto en compras)
    rows.append(_row(user, "AMAZON COMPRA ONLINE", -1450.00, hoy + timedelta(days=2)))

    # 2. Restaurante factura de empresa (z-score alto en restauracion)
    rows.append(_row(user, "RESTAURANTE EL CELLER DE CAN ROCA", -380.00, hoy + timedelta(days=3)))

    # 3. Subida de precio en suscripcion (si hay suscripciones activas)
    if suscripciones:
        desc_sub, precio_orig = suscripciones[0]
        precio_nuevo = round(abs(precio_orig) * 1.40, 2)  # +40%
        rows.append(_row(user, desc_sub, -precio_nuevo, hoy + timedelta(days=5)))

    # 4. Gasto de alimentacion extremo
    rows.append(
        _row(
            user,
            f"PAGO TARJETA MERCADONA SL {ciudad}",
            -820.00,
            hoy + timedelta(days=6),
        )
    )

    # 5. Transferencia sospechosa (importe alto, fuera del patron alquiler)
    rows.append(_row(user, "TRANSFERENCIA BIZUM VARIOS", -950.00, hoy + timedelta(days=7)))

    return rows


def main() -> None:
    """CLI: parsea argumentos, genera el historico y lo guarda como CSV en data/."""
    p = argparse.ArgumentParser(description="Genera historico simulado (CSV) para demo.")
    p.add_argument("--user-id", default="demo-user", help="ID del usuario destino")
    p.add_argument("--months", type=int, default=6, help="Meses de historico a generar")
    p.add_argument(
        "--per-month",
        type=int,
        default=50,
        help="Transacciones por mes (sin nomina ni suscripciones)",
    )
    p.add_argument("--salary", type=float, default=2000.0, help="Importe de la nomina mensual")
    p.add_argument("--city", default="MADRID", help="Ciudad para nombres de comercios")
    p.add_argument(
        "--subscriptions",
        type=int,
        default=3,
        choices=range(0, 6),
        help="Numero de suscripciones (0-5)",
    )
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    random.seed(args.seed)
    rows = generate(
        user=args.user_id,
        months=args.months,
        per_month=args.per_month,
        salary=args.salary,
        ciudad=args.city.upper(),
        n_suscripciones=args.subscriptions,
    )

    out = ROOT / "data" / f"history_{args.user_id}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["user_id", "description", "amount", "date"])
        w.writeheader()
        w.writerows(rows)

    n_outliers = 5 if args.subscriptions > 0 else 4
    print(
        f"Generadas {len(rows)} transacciones ({args.months} meses, {n_outliers} outliers) -> {out}"
    )


if __name__ == "__main__":
    main()
