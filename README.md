# Índice Invertido con Hadoop MapReduce en Amazon EMR

Sistema de recuperación de información distribuido que construye un índice invertido sobre 39,608 títulos de libros del Proyecto Gutenberg, ejecutado sobre un clúster Hadoop en Amazon EMR.

---

## Arquitectura

```
titles.txt (39,608 títulos)
       │
       ▼
split_titles.py
       │  genera doc_00001.txt, doc_00002.txt, ...
       ▼
  data/documents/          data/doc_map.txt
  doc_00001.txt ──┐        doc_00001.txt → Pride and Prejudice
  doc_00002.txt ──┤        doc_00002.txt → Frankenstein
  ...             │        ...
                  ▼
  ┌─────────┐   word → doc_NNNNN.txt → 1
  │ Mapper  │ ──────────────────────────►
  └─────────┘
       │  shuffle & sort
       ▼
  ┌──────────┐  pre-agrega por nodo
  │ Combiner │ ──────────────────────────►
  └──────────┘
       │
       ▼
  ┌─────────┐   word → [["doc_00001.txt", N], ["doc_00003.txt", M], ...]
  │ Reducer │ ──────────────────────────►
  └─────────┘
       │
       ▼
  s3://bucket/output/   ←── índice final
       │
       ▼
  search.py  →  doc_00001.txt  "Pride and Prejudice"  (score: 2)
```

Cada archivo `doc_NNNNN.txt` es un documento con un título de libro. El índice mapea cada palabra a los documentos donde aparece, con su frecuencia como base del ranking.

---

## Estructura del proyecto

```
invert_index_emr/
├── titles.txt              ← corpus: 39,608 títulos de Project Gutenberg
├── src/
│   ├── mapper.py           ← fase Map: (palabra, doc_NNNNN.txt, 1)
│   ├── combiner.py         ← pre-agrega localmente antes del shuffle
│   └── reducer.py          ← fase Reduce: construye el índice final
├── search/
│   └── search.py           ← búsqueda AND con ranking por frecuencia
├── scripts/
│   ├── split_titles.py     ← divide titles.txt en archivos individuales
│   ├── setup.sh            ← configura S3 + EMR + lanza el job
│   ├── clean_local.sh      ← limpia archivos generados localmente
│   ├── cleanup.sh          ← elimina todos los recursos de AWS
│   └── test_local.py       ← simula MapReduce localmente
└── requirements.txt
```

---

## Requisitos

- Cuenta de AWS con permisos para EMR, S3 e IAM
- AWS CLI configurado (en **AWS Cloud Shell** ya está listo)
- Python 3.7+
- `pip install boto3` (solo para búsqueda desde S3)

---

## Instalación

```bash
git clone <url-del-repo>
cd invert_index_emr
```

Verificar el dataset:

```bash
wc -l titles.txt     # → 39608
head -5 titles.txt
```

---

## Paso 1 — Dividir títulos en documentos

Cada título se convierte en un archivo independiente (`doc_00001.txt`, `doc_00002.txt`, ...).

```bash
# Todos los títulos (39,608 archivos)
python3 scripts/split_titles.py

# O una muestra para pruebas rápidas
python3 scripts/split_titles.py --sample 500
```

Salida esperada:

```
Dividiendo 39608 títulos en archivos individuales...
Destino : data/documents/
Mapeo   : data/doc_map.txt

   5000/39608  (13%)
  10000/39608  (25%)
  ...
  39608/39608  (100%)

✓ 39608 archivos creados en data/documents/
```

Esto genera:
- `data/documents/doc_00001.txt` → contiene `Pride and Prejudice`
- `data/documents/doc_00002.txt` → contiene `Frankenstein; Or, The Modern Prometheus`
- `data/doc_map.txt` → mapeo `filename → título` (usado por el buscador)

---

## Paso 2 — Prueba local (sin AWS)

Simula el pipeline completo MapReduce en tu máquina antes de gastar en EMR.

```bash
python3 scripts/test_local.py
```

Salida esperada:

```
Input : data/documents/
Output: data/index.txt

[1/4] Mapper...
      39608 documentos encontrados
      39608/39608 archivos mapeados...
      192,450 registros emitidos
[2/4] Shuffle (sort)...
[3/4] Combiner...
      187,279 registros tras combiner
[4/4] Reducer...
      24,306 palabras únicas en el índice

Muestra del índice (3 entradas):
  abbey      →  doc_00028.txt  "Northanger Abbey"
  adventures →  doc_00148.txt  "The Swiss Family Robinson; or Adventures..."
  war        →  doc_00089.txt  "The Art of War"
```

---

## Paso 3 — Búsquedas de prueba

### Búsqueda local (tras test_local.py)

```bash
python3 search/search.py --local data/index.txt "<consulta>"
```

### Búsqueda desde S3 (tras ejecutar EMR)

```bash
python3 search/search.py --s3 <bucket> output/ "<consulta>"
```

---

### Ejemplos

**Una sola palabra:**

```bash
python3 search/search.py --local data/index.txt "adventures"
```
```
Búsqueda: "adventures"
───────────────────────────────────────────────────────
Palabras buscadas : ['adventures']
Resultados        : 5

   1. doc_00148.txt  "The Swiss Family Robinson; or Adventures in a Desert Island"  (score: 1)
   2. doc_00266.txt  "The Female Quixote; or, The Adventures of Arabella"  (score: 1)
   3. doc_00317.txt  "Wonderful Adventures of Mrs. Seacole in Many Lands"  (score: 1)
   ...
```

---

**Múltiples palabras (AND):**

```bash
python3 search/search.py --local data/index.txt "twenty years after"
```
```
Búsqueda: "twenty years after"
───────────────────────────────────────────────────────
Palabras buscadas : ['twenty', 'years', 'after']
Resultados        : 2

   1. doc_00289.txt  "The Vicomte de Bragelonne; Or, Ten Years Later: Being the completion of Twenty Years After"  (score: 4)
   2. doc_00003.txt  "Twenty years after"  (score: 3)
```

> El score más alto en el primer resultado se debe a que la palabra `years` aparece dos veces en ese título ("Ten **Years** Later" + "Twenty **Years** After"), lo que refleja mayor relevancia.

---

**Más consultas de prueba:**

```bash
python3 search/search.py --local data/index.txt "war peace"
python3 search/search.py --local data/index.txt "great expectations"
python3 search/search.py --local data/index.txt "mystery detective"
python3 search/search.py --local data/index.txt "adventures island"
python3 search/search.py --local data/index.txt "pride prejudice"
```

---

## Paso 4 — Despliegue en Amazon EMR

> Requiere haber ejecutado `split_titles.py` primero.

```bash
bash scripts/setup.sh <nombre-bucket> <región>
```

Ejemplo:

```bash
bash scripts/setup.sh mi-indice-gutenberg us-east-1
```

El script realiza automáticamente:

| Paso | Acción |
|------|--------|
| 1 | Crea el bucket S3 |
| 2 | Sube los 39,608 docs + `doc_map.txt` + scripts MapReduce |
| 3 | Verifica/crea los roles IAM de EMR |
| 4 | Crea clúster: 1 master + 1 core (`m4.large`) |
| 5 | Lanza el job Hadoop Streaming y espera el resultado |

**Tiempo estimado:** 8-12 minutos · **Costo estimado:** < $0.05 USD

Al terminar muestra:

```
╔══════════════════════════════════════════════════╗
║   JOB COMPLETADO EXITOSAMENTE                    ║
╚══════════════════════════════════════════════════╝

  Índice en : s3://mi-indice-gutenberg/output/

  python3 search/search.py --s3 mi-indice-gutenberg output/ "war peace"
```

---

## Limpieza

### Limpiar archivos locales (documentos e índice)

Elimina lo generado por `split_titles.py` y `test_local.py`:

```bash
bash scripts/clean_local.sh
```

### Limpiar recursos de AWS

Elimina el clúster EMR, el bucket S3 y todos sus archivos:

```bash
bash scripts/cleanup.sh
```

Ambos scripts dejan el proyecto exactamente como después de `git clone`.

---

## Formato del índice generado

Cada línea del output de Hadoop tiene el formato:

```
palabra   [["doc_00001.txt", frecuencia], ["doc_00003.txt", frecuencia], ...]
```

Ejemplo:

```
war        [["doc_00089.txt", 2], ["doc_00412.txt", 1], ["doc_00531.txt", 1]]
adventure  [["doc_00148.txt", 1], ["doc_00266.txt", 1]]
```

Los documentos están ordenados por frecuencia descendente (mayor relevancia primero).
