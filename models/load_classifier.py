"""
load_classifier.py
Importar y usar:
    from load_classifier import load
    classify = load()
    result = classify("MERCADONA COMPRA", -45.20)
"""
import json, time
from pathlib import Path
import numpy as np
import joblib
from sentence_transformers import SentenceTransformer

MODELS_DIR = Path(__file__).parent
_CACHE: dict = {}

CATEGORIES = [
    "alimentacion", "compras", "hogar", "impuestos_tasas",
    "ingresos", "ocio", "otros", "restauracion",
    "salud", "suscripciones", "transporte", "transferencias",
]

def load():
    """Carga el clasificador (singleton) y devuelve classify."""
    if "classify" in _CACHE:
        return _CACHE["classify"]
    artifact  = joblib.load(MODELS_DIR / "classifier.pkl")
    model     = artifact["model"]
    le        = artifact["label_encoder"]
    threshold = 0.70
    embedder  = SentenceTransformer(artifact["embedder_name"])

    def classify(description: str, amount: float) -> dict:
        """
        Clasifica una transaccion bancaria anonimizada.
        Returns: {categoria, confianza, nivel_usado}
        """
        emb  = embedder.encode([description], normalize_embeddings=True)
        feat = np.hstack([emb, np.clip([[amount / 3000.0]], -1, 1)])
        proba    = model.predict_proba(feat)[0]
        pred_idx = int(np.argmax(proba))
        conf     = float(proba[pred_idx])
        cat      = le.inverse_transform([pred_idx])[0]
        if conf >= threshold:
            return {"categoria": cat, "confianza": round(conf, 4), "nivel_usado": 1}
        try:
            cat_llm = _call_llm(description, amount)
            return {"categoria": cat_llm, "confianza": 0.0, "nivel_usado": 2}
        except Exception:
            return {"categoria": cat, "confianza": round(conf, 4), "nivel_usado": 1}

    _CACHE["classify"] = classify
    return classify


def _call_llm(description: str, amount: float) -> str:
    import os
    cats = ", ".join(CATEGORIES)
    prompt = (f"Clasifica esta transaccion en UNA categoria: {cats}\n"
              f'Descripcion: "{description}", Importe: {amount}\n'
              "Responde SOLO con el nombre de la categoria.")
    ep  = os.getenv("AZURE_OPENAI_ENDPOINT")
    key = os.getenv("AZURE_OPENAI_API_KEY")  # corregido: proyecto usa AZURE_OPENAI_API_KEY
    dep = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
    if ep and key:
        import openai
        client = openai.AzureOpenAI(azure_endpoint=ep, api_key=key, api_version='2024-02-01')
        resp = client.chat.completions.create(
            model=dep,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20, temperature=0.0,
        )
        cat = resp.choices[0].message.content.strip().lower()
        return cat if cat in CATEGORIES else 'otros'
    return 'otros'


if __name__ == "__main__":
    classify = load()
    for desc, amt in [
        ("MERCADONA 1234", -45.20), ("NETFLIX SUSCRIPCION", -12.99),
        ("NOMINA ENERO", 2100.0),  ("FARMACIA CENTRAL", -18.50),
    ]:
        t0 = time.perf_counter()
        r  = classify(desc, amt)
        ms = (time.perf_counter() - t0) * 1000
        print(f"{desc:<30} {amt:>8.2f}  {r}  ({ms:.1f} ms)")
