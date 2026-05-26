"""Simulacion end-to-end en proceso (sin servidor).

Ejercita todo el pipeline contra SQLite usando la capa de servicio:
  genera historico -> procesa transacciones -> stats -> insight mensual.

Sirve para verificar que todo esta conectado de un vistazo:
    python scripts/e2e_demo.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

# Permitir ejecutar el script directamente (anade la raiz al path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.db import init_db                      # noqa: E402
from api.db import queries                      # noqa: E402
from api.service import process_transaction     # noqa: E402
from core.insights import generate_insight      # noqa: E402

USER = "user_e2e"
SAMPLES = [
    ("PAGO TARJETA MERCADONA SL MADRID", -43.27),
    ("NETFLIX SUSCRIPCION", -12.99),
    ("REPSOL GASOLINERA", -58.40),
    ("ABONO NOMINA EMPRESA SL", 1850.00),
    ("GLOVO PEDIDO COMIDA", -18.50),
    ("AMAZON COMPRA ONLINE", -34.90),
    # contacto con PII para comprobar anonimizacion (IBAN + email + telefono)
    ("TRANSFERENCIA A ES9121000418450200051332 juan@mail.com 612345678", -200.00),
    # anomalia: gasto enorme en compras
    ("AMAZON COMPRA ONLINE", -1450.00),
]


def main() -> None:
    init_db()
    print(f"== Procesando {len(SAMPLES)} transacciones para {USER} ==")
    for desc, amt in SAMPLES:
        row = process_transaction(USER, desc, amt)
        flag = "  <-- ANOMALIA" if row["is_anomaly"] else ""
        print(f"[{row['category']:<14} L{row['classification_level']} "
              f"{row['confidence']:.0%}] {amt:>9.2f}  {row['description_anonymized']}{flag}")

    print("\n== Stats ==")
    stats = queries.get_user_stats(USER)
    print(f"  transacciones={stats['n_transactions']} gastos={stats['total_gastos']} "
          f"ingresos={stats['total_ingresos']} anomalias={stats['n_anomalies']}")

    month = datetime.now(timezone.utc).strftime("%Y-%m")
    txs = queries.get_transactions_by_month(USER, month)
    text, source = generate_insight(month, txs)
    print(f"\n== Insight {month} (fuente={source}) ==\n{text}")


if __name__ == "__main__":
    main()
