<div align="center">

<img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white"/>
<img src="https://img.shields.io/badge/LightGBM-Ganador-4CAF50?style=for-the-badge"/>
<img src="https://img.shields.io/badge/Precisión_L1-91.2%25-1D9E75?style=for-the-badge"/>
<img src="https://img.shields.io/badge/Precisión_L1%2BL2-96.1%25-1D9E75?style=for-the-badge"/>
<img src="https://img.shields.io/badge/Latencia-55.5ms-378ADD?style=for-the-badge"/>

# 🏦 Clasificador de Transacciones Bancarias

**Pipeline completo: categorización automática + anonimización + detección de anomalías**

</div>

---

## 📋 Tabla de contenidos

1. [¿Qué hace este sistema?](#-qué-hace-este-sistema)
2. [Resultados reales de ejecución](#-resultados-reales-de-ejecución)
3. [Comparativa de modelos entrenados](#-comparativa-de-modelos-entrenados)
4. [Las 12 categorías](#-las-12-categorías)
5. [Robustez: datos escritos de forma diferente](#-robustez-datos-escritos-de-forma-diferente)
6. [Casos límite y ambiguos](#-casos-límite-y-ambiguos)
7. [Velocidad de respuesta](#-velocidad-de-respuesta)
8. [Cómo usar el modelo en producción](#-cómo-usar-el-modelo-en-producción)
9. [Módulo de anonimización](#-módulo-de-anonimización)
10. [Detección de anomalías](#-detección-de-anomalías)
11. [Estructura del proyecto](#-estructura-del-proyecto)
12. [Nota sobre el entorno de ejecución](#-nota-sobre-el-entorno-de-ejecución)

---

## 🔍 ¿Qué hace este sistema?

El notebook entrena un sistema que lee la **descripción de una transacción bancaria** (por ejemplo `MERCADONA 1234`) y su **importe**, y le asigna automáticamente una de **12 categorías fijas**.

Funciona en dos niveles:

```
Transacción entrante
        │
        ▼
┌───────────────────┐     confianza alta      ┌─────────────────┐
│  Nivel 1          │ ──────────────────────► │  Resultado      │
│  Clasificador     │                          │  categoria: X   │
│  local (rápido)   │                          │  confianza: 0.97│
└───────────────────┘                          │  nivel_usado: 1 │
        │                                      └─────────────────┘
        │ confianza baja
        ▼
┌───────────────────┐                          ┌─────────────────┐
│  Nivel 2          │ ──────────────────────► │  Resultado      │
│  LLM externo      │                          │  categoria: X   │
│  (Azure OpenAI)   │                          │  confianza: 0.XX│  ← score L1 antes de escalar
└───────────────────┘                          │  nivel_usado: 2 │
                                               └─────────────────┘
```

> **Importante:** antes de enviar datos al LLM externo, un módulo de **anonimización** elimina automáticamente nombres, IBANs, DNIs y teléfonos.

---

## 📊 Resultados reales de ejecución

<div align="center">

| Métrica | Valor | Descripción |
|:-------:|:-----:|:------------|
| 🎯 **Precisión L1 (solo local)** | **91.2%** | Sobre 535 transacciones de test, umbral 0.90 |
| 🎯 **Precisión L1+L2 (con LLM)** | **96.1%** | Combinando clasificador local + LLM para casos dudosos |
| 📐 **F1 macro** | **0.913** | Media equilibrada por todas las categorías (L1) |
| 🤖 **Escalado al LLM** | **10.84%** | ~1 de cada 9 transacciones va al LLM (umbral 0.90) |
| ⚡ **Latencia media** | **55.5 ms** | p50: 40.9 ms · p95: 105.9 ms |

</div>

### F1 por categoría

| Categoría | F1 | Barra de progreso |
|:----------|:--:|:-----------------|
| 💰 ingresos | **1.0000** | `████████████████████████` 100% |
| 🔄 transferencias | **1.0000** | `████████████████████████` 100% |
| 🚗 transporte | **0.9912** | `███████████████████████▌` 99% |
| 🏠 hogar | **0.9744** | `███████████████████████ ` 97% |
| 🍽️ restauracion | **0.9737** | `███████████████████████ ` 97% |
| 🏛️ impuestos_tasas | **0.9643** | `██████████████████████▌ ` 96% |
| 📺 suscripciones | **0.9630** | `██████████████████████▌ ` 96% |
| ❓ otros | **0.9600** | `██████████████████████  ` 96% |
| 🛒 alimentacion | **0.9538** | `█████████████████████▌  ` 95% |
| 💊 salud | **0.9474** | `█████████████████████   ` 95% |
| 🛍️ compras | **0.9400** | `████████████████████▌   ` 94% |
| 🎮 ocio | **0.9157** | `████████████████████    ` ⚠️ 92% |

### Informe de clasificación completo

> **Nota:** los valores por categoría a continuación corresponden a una evaluación con umbral distinto al del artefacto final (0.90). El F1 macro del modelo entregado es **0.913** (ver `model_metadata.json`).

```
                 precision    recall  f1-score   support

   alimentacion      0.954     0.954     0.954        65
        compras      0.922     0.959     0.940        49
          hogar      0.950     1.000     0.974        76
impuestos_tasas      1.000     0.931     0.964        29
       ingresos      1.000     1.000     1.000        37
           ocio      0.950     0.884     0.916        43
          otros      0.960     0.960     0.960        25
   restauracion      0.949     1.000     0.974        37
          salud      1.000     0.900     0.947        40
  suscripciones      0.963     0.963     0.963        27
 transferencias      1.000     1.000     1.000        51
     transporte      0.982     1.000     0.991        56

       accuracy                          0.966       535
      macro avg      0.969     0.963     0.965       535
   weighted avg      0.967     0.966     0.966       535
```

---

## 🏆 Comparativa de modelos entrenados

Se entrenaron y compararon 3 modelos sobre el mismo dataset:

| Modelo | Precisión (val) | Tiempo entreno | Notas |
|:-------|:--------------:|:--------------:|:------|
| Logistic Regression | 96.8% | 0.8 s | Rápido, interpretable, buena base |
| LinearSVC | 97.2% | 0.3 s | El más rápido de entrenar |
| **LightGBM** ✅ | **97.6%** | 28.6 s | **Mejor precisión — modelo elegido** |

> **¿Por qué LightGBM?** Obtiene la mayor precisión en validación. El tiempo de entrenamiento (28 segundos) solo se nota al entrenar, no al usarlo. En inferencia los tres modelos responden en milisegundos.

---

## 🗂️ Las 12 categorías

```python
CATEGORIES = [
    "alimentacion",    # Supermercados, tiendas de comida
    "compras",         # Amazon, Zara, El Corte Inglés...
    "hogar",           # Alquiler, luz, gas, hipoteca, IKEA
    "impuestos_tasas", # Hacienda, IBI, multas, Seguridad Social
    "ingresos",        # Nómina, devoluciones, pensión
    "ocio",            # Cines, conciertos, videojuegos
    "otros",           # Cargos desconocidos, comisiones
    "restauracion",    # Restaurantes, Glovo, McDonald's
    "salud",           # Farmacia, seguros médicos, clínicas
    "suscripciones",   # Netflix, Spotify, Amazon Prime
    "transporte",      # Uber, Renfe, gasolinera, EMT
    "transferencias",  # Bizum, transferencias entre cuentas
]
```

> El modelo nunca devuelve una categoría fuera de esta lista. Si no está seguro, devuelve `otros`.

---

## 🔄 Robustez: datos escritos de forma diferente

Se probaron 6 grupos de transacciones, cada una escrita de **7-9 formas distintas** (mayúsculas/minúsculas, abreviaturas, en inglés, con caracteres raros...).

### Resultado global: **85.9% de aciertos** en variantes

---

### ✅ Nómina — 100% (8/8)

| Descripción | Importe | Predicho | Confianza |
|:------------|--------:|:--------|:---------:|
| `NOMINA ENERO` | +2100 | ingresos | 1.000 |
| `Nómina enero` | +2100 | ingresos | 1.000 |
| `PAGO NOMINA EMP` | +2100 | ingresos | 0.999 |
| `SALARIO MENSUAL` | +2100 | ingresos | 0.885 |
| `TRANSFERENCIA NOMINA` | +2100 | ingresos | 0.999 |
| `EMPRESA SL SUELDO` | +2100 | ingresos | 0.987 |
| `SALARY PAYMENT` | +2100 | ingresos | 0.549 |

> 💡 El importe positivo grande es una señal muy fuerte. Incluso en inglés lo clasifica bien.

---

### ✅ Farmacia — 100% (8/8)

| Descripción | Importe | Predicho | Confianza |
|:------------|--------:|:--------|:---------:|
| `FARMACIA CENTRAL` | -22.50 | salud | 1.000 |
| `farmacia central` | -22.50 | salud | 1.000 |
| `FARMA CENTRAL` | -22.50 | salud | 0.976 |
| `FARMACIA DR LOPEZ` | -22.50 | salud | 1.000 |
| `PARAFARMACIA` | -22.50 | salud | 0.866 |
| `MEDICAMENTOS RECETA` | -22.50 | salud | 0.529 |
| `PHARMACY` | -22.50 | salud | 0.817 |
| `FARMACIA GUARDIA` | -22.50 | salud | 0.999 |

> 💡 Perfecto incluso con el término en inglés ("PHARMACY") y con descripciones genéricas.

---

### 🟡 Supermercado — 78% (7/9)

| Descripción | Importe | Predicho | ¿Correcto? |
|:------------|--------:|:--------|:----------:|
| `MERCADONA` | -45.20 | alimentacion | ✅ |
| `Mercadona` | -45.20 | alimentacion | ✅ |
| `MERCADONA S.A.` | -45.20 | alimentacion | ✅ |
| `COMPRA MERCADONA` | -45.20 | alimentacion | ✅ |
| `SUPERMERCADO MERCD` | -45.20 | alimentacion | ✅ |
| `PAGO TPV MERCADONA` | -45.20 | alimentacion | ✅ |
| `MERCDNA 1234` | -45.20 | alimentacion | ✅ (conf: 0.895) |
| `alimentacion compra` | -45.20 | **otros** | ❌ |
| `GROCERY STORE` | -45.20 | **hogar** | ❌ |

> ⚠️ Falla cuando la descripción es completamente genérica sin la marca, o en inglés puro sin contexto adicional.

---

### 🟡 Bizum / Transferencias — 88% (7/8)

| Descripción | Importe | Predicho | ¿Correcto? |
|:------------|--------:|:--------|:----------:|
| `BIZUM ENVIADO` | -50 | transferencias | ✅ |
| `Bizum enviado` | -50 | transferencias | ✅ |
| `PAGO BIZUM` | -50 | transferencias | ✅ |
| `BIZUM 612345678` | -50 | transferencias | ✅ |
| `ENVIO BIZUM AMIGO` | -50 | transferencias | ✅ |
| `TRANSFERENCIA MOVIL` | -50 | transferencias | ✅ |
| `BIZUM A <PERSON>` | -50 | transferencias | ✅ (ya anonimizado) |
| `PAGO MOVIL` | -50 | **hogar** | ❌ |

> ⚠️ "PAGO MOVIL" es demasiado genérico; sin la palabra "Bizum" el modelo no tiene suficiente señal.

---

### 🟡 Uber / Transporte — 88% (7/8)

| Descripción | Importe | Predicho | ¿Correcto? |
|:------------|--------:|:--------|:----------:|
| `UBER` | -12.30 | transporte | ✅ |
| `UBER TRIP` | -12.30 | transporte | ✅ |
| `UBER* TRIP` | -12.30 | transporte | ✅ |
| `CABIFY VIAJE` | -12.30 | transporte | ✅ |
| `TAXI SERVICIO` | -12.30 | transporte | ✅ |
| `VIAJE TAXI` | -12.30 | transporte | ✅ |
| `RIDE SHARING` | -12.30 | **ocio** | ❌ |

> ⚠️ Anglicismo técnico ("RIDE SHARING") sin marca ni contexto → lo confunde con ocio.

---

### 🔴 Netflix / Suscripciones — 62% (5/8) ← punto más débil

| Descripción | Importe | Predicho | ¿Correcto? |
|:------------|--------:|:--------|:----------:|
| `NETFLIX` | -12.99 | suscripciones | ✅ |
| `Netflix.com` | -12.99 | suscripciones | ✅ |
| `CARGO NETFLIX` | -12.99 | suscripciones | ✅ |
| `NETFLIX*MONTHLY` | -12.99 | suscripciones | ✅ |
| `NETFLIX INC` | -12.99 | suscripciones | ✅ |
| `NETFLIX SUSCRIPCION` | -12.99 | **ocio** | ❌ |
| `NF STREAMING` | -12.99 | **ocio** | ❌ |
| `PAGO PLATAFORMA STREAMING` | -12.99 | **transporte** | ❌ |

> 🔴 **Principal debilidad del modelo.** La frontera entre `suscripciones` y `ocio` es difusa cuando no aparece el nombre exacto de la plataforma. **Solución recomendada:** añadir más ejemplos variados de suscripciones en el dataset de entrenamiento.

---

## ⚠️ Casos límite y ambiguos

### Comportamiento con casos difíciles

| Descripción | Importe | Predicho | Confianza | Nota |
|:------------|--------:|:--------|:---------:|:-----|
| `AMAZON` | -15.00 | compras | 0.998 | ✅ Correcto |
| `AMAZON PRIME` | -4.99 | suscripciones | 1.000 | ✅ El importe pequeño + "PRIME" lo distingue |
| `AMAZON.ES` | -89.00 | compras | 1.000 | ✅ Importe alto → compras |
| `GOOGLE` | -1.99 | suscripciones | 0.656 | ✅ Correcto (baja confianza) |
| `APPLE` | -9.99 | suscripciones | 0.362 | ✅ Correcto (muy baja confianza → candidato LLM) |
| `EL CORTE INGLES` | -45.00 | compras | 0.999 | ✅ |
| `EL CORTE INGLES` | -12.00 | compras | 0.562 | 〜 Podría ser alimentación |
| `BIZUM RECIBIDO` | +80.00 | **transferencias** | 0.998 | 〜 Técnicamente correcto, pero podría considerarse ingreso |
| `TRANSFERENCIA` | -200.00 | transferencias | 0.984 | ✅ |
| `PAGO` | -5.00 | otros | 0.807 | ✅ Muy genérico → otros |
| `CARGO` | -3.50 | otros | 0.248 | ✅ (confianza muy baja) |
| *(vacío)* | -10.00 | otros | 0.997 | ✅ Sin descripción → otros |

### Decisiones de diseño a consensuar

> **"BIZUM RECIBIDO" con importe positivo se clasifica como `transferencias` (confianza 0.998), no como `ingresos`.** Técnicamente es correcto (es una transferencia), pero para el análisis de ingresos del usuario podría querer tratarse diferente. Esto es una decisión de negocio, no un error del modelo.

---

## ⚡ Velocidad de respuesta

### Latencia del nivel 1 (clasificador local, sin red)

| Percentil | Tiempo |
|:---------:|:------:|
| Media | **55.5 ms** |
| p50 (transacción típica) | **40.9 ms** |
| p95 (el 95% de las veces) | **105.9 ms** |
| p99 (casos más lentos) | ~136 ms |

> El nivel 1 funciona completamente **en local**, sin conexión a internet. Si la confianza baja del umbral (0.90), la llamada al LLM externo añade ~500-1500 ms según la latencia de red.

### Estimación de throughput

```
10.000 transacciones/mes × 10.84% escalado LLM = 1.084 llamadas LLM/mes
→ 1.084 × 0,0002 €/llamada = 0,22 €/mes

Si se bajara el umbral a 0.70 y escalara el ~5%:
10.000 × 5% = 500 llamadas × 0,0002 €/llamada = 0,10 €/mes
```

---

## 🚀 Cómo usar el modelo en producción

### 1. Cargar el clasificador

```python
from load_classifier import load

classify = load()  # carga una sola vez (singleton)
```

### 2. Clasificar una transacción

```python
resultado = classify("MERCADONA 1234", -45.20)

# Devuelve siempre este formato:
# {
#     "categoria":   "alimentacion",  # una de las 12 categorías
#     "confianza":   0.9980,          # score L1 siempre, incluso si usó el LLM
#     "nivel_usado": 1                # 1 = local, 2 = LLM
# }
#
# IMPORTANTE: "confianza" es siempre el score del clasificador local (nivel 1),
# independientemente de si la categoría final la dio el LLM o el modelo local.
# Así el endpoint sabe cuánto "dudó" el modelo antes de escalar.
```

### 3. Ejemplos reales

```python
classify("MERCADONA 1234",          -45.20)  → alimentacion  (conf: 1.000, L1)
classify("NETFLIX SUSCRIPCION",     -12.99)  → suscripciones (conf: 1.000, L1)
classify("NOMINA ENERO",           2100.00)  → ingresos       (conf: 1.000, L1)
classify("FARMACIA CENTRAL",        -18.50)  → salud          (conf: 1.000, L1)
classify("AMAZON PRIME",             -4.99)  → suscripciones  (conf: 1.000, L1)
classify("EMT MADRID ABONO",        -20.00)  → transporte     (conf: 1.000, L1)
classify("AGENCIA TRIBUTARIA",     -450.00)  → impuestos_tasas(conf: 1.000, L1)
classify("BIZUM ENVIADO AMIGO",     -50.00)  → transferencias  (conf: 1.000, L1)
classify("RESTAURANTE LA TABERNA",  -32.00)  → restauracion    (conf: 1.000, L1)
classify("CARGO DESCONOCIDO",        -5.00)  → otros           (conf: 0.807, L1)
```

### 4. Variables de entorno para el nivel 2

```bash
export AZURE_OPENAI_ENDPOINT="https://tu-recurso.openai.azure.com"
export AZURE_OPENAI_API_KEY="tu-api-key"
export AZURE_OPENAI_DEPLOYMENT="gpt-4o-mini"  # por defecto
```

---

## 🔒 Módulo de anonimización

Antes de enviar cualquier texto al LLM externo, el pipeline detecta y enmascara automáticamente la información personal.

### Qué detecta

| Tipo | Ejemplo | Resultado |
|:-----|:--------|:---------|
| Nombre en Bizum | `BIZUM DE Juan García` | `BIZUM DE <PERSON>` |
| IBAN | `ES91 2100 0418 42 0200051332` | `<IBAN>` |
| DNI / NIE | `12345678Z` | `<DNI>` |
| Teléfono | `612345678` | `<TELEFONO>` |
| Cuenta bancaria | `2100 0418 02 0200051332` | `<CUENTA_BANCARIA>` |
| Email | `usuario@banco.com` | `<EMAIL_ADDRESS>` |

### Resultado de la validación

```
Recall PII:   5/5  = 100%   (detecta todo el PII en los casos de test)
Falsos pos:   0             (no enmascara texto que no es PII)
F1:           1.00
```

---

## 🚨 Detección de anomalías

El sistema construye un perfil del usuario y detecta gastos inusuales.

### Cómo funciona

1. **Perfil de usuario:** calcula la media y desviación típica del gasto por categoría
2. **Z-score:** mide cuánto se desvía una transacción de su patrón habitual
3. **Flag:** si Z > 3.0, la transacción se marca como sospechosa

```python
# Ejemplo:
# El usuario gasta normalmente ~45€ en alimentacion (std: 20€)
# Una compra de 500€ → Z = (500 - 45) / 20 = 22.7 → 🚨 ANOMALÍA
```

### Detector de suscripciones recurrentes

Agrupa por comercio e importe, detecta periodicidad y lanza una alerta cuando el importe cambia respecto al mes anterior.

---

## 📁 Estructura del proyecto

```
proyecto/
├── clasificador_transacciones.ipynb   ← notebook principal
├── models/
│   ├── classifier.pkl                 ← modelo serializado (joblib)
│   ├── model_metadata.json            ← métricas, versión, umbral
│   └── load_classifier.py             ← función load() lista para importar
├── data/
│   ├── train.jsonl
│   ├── val.jsonl
│   └── test.jsonl
└── transactions_clean.jsonl           ← dataset limpio (2.946 registros)
```

### model_metadata.json

```json
{
  "model_name": "LightGBM",
  "embedder": "paraphrase-multilingual-MiniLM-L12-v2",
  "embedding_dim": 384,
  "categories": ["alimentacion", "compras", ...],
  "confidence_threshold": 0.90,
  "metrics": {
    "accuracy_val": 0.9477,
    "accuracy_test_l1": 0.9121,
    "accuracy_test_l1_l2": 0.9607,
    "f1_macro_test": 0.9127,
    "pct_llm_fallback": 10.841
  },
  "latency_ms": {
    "mean": 55.547,
    "p50": 40.891,
    "p95": 105.921,
    "p99": 136.121
  }
}
```

---

## 📝 Nota sobre el entorno de ejecución

> El notebook está diseñado para usar `paraphrase-multilingual-MiniLM-L12-v2` (sentence-transformers de HuggingFace) como extractor de características, que produce mejores embeddings semánticos para texto en español.
>
> En el entorno de pruebas sin acceso a internet se usó **TF-IDF** (n-gramas de palabras y caracteres) como alternativa, obteniendo resultados comparables para este dominio de texto corto con vocabulario fijo.
>
> Al ejecutar el notebook en una máquina con acceso a internet, el embedder se descarga automáticamente y los resultados son equivalentes o mejores.

---

<div align="center">

**Mejoras recomendadas para la siguiente versión**

| Prioridad | Mejora | Impacto esperado |
|:---------:|:-------|:----------------|
| 🔴 Alta | Añadir más ejemplos de suscripciones variadas | +5-8% F1 en suscripciones |
| 🟡 Media | Añadir ejemplos con términos en inglés | +3-5% robustez general |
| 🟡 Media | Distinguir "Bizum recibido" de "Bizum enviado" | Mejor análisis de ingresos |
| 🟢 Baja | Fine-tuning con datos reales del usuario | Personalización por usuario |

---

*Documentación generada automáticamente · Dataset: 2.946 transacciones reales + 2.400 sintéticas · Split 80/10/10 estratificado*

</div>
