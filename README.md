# Índice Invertido con Hadoop MapReduce en Amazon EMR

Sistema de recuperación de información distribuido que construye un índice invertido sobre 39,608 títulos de libros del Proyecto Gutenberg, ejecutado sobre un clúster Hadoop en Amazon EMR.

---

## Arquitectura

```
titles.txt (39,608 títulos)
       │
       ▼
build_corpus.py
       │  genera un único corpus.txt: doc_NNNNN.txt TAB título
       ▼
data/corpus.txt                    data/doc_map.txt
doc_00001.txt  Pride and Prejudice  doc_00001.txt → Pride and Prejudice
doc_00002.txt  Frankenstein         doc_00002.txt → Frankenstein
...                                 ...
       │
       ▼  (1 archivo → Hadoop lo divide en bloques de 128MB)
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

---

## Estructura del proyecto

```
invert_index_emr/
├── titles.txt                ← corpus: 39,608 títulos de Project Gutenberg
├── src/
│   ├── mapper.py             ← fase Map: lee doc_id TAB contenido → (palabra, doc, 1)
│   ├── combiner.py           ← pre-agrega localmente antes del shuffle
│   └── reducer.py            ← fase Reduce: construye el índice final
├── search/
│   └── search.py             ← búsqueda AND con ranking por frecuencia
├── scripts/
│   ├── build_corpus.py       ← genera data/corpus.txt (escalable a 5GB+)
│   ├── upload_s3.sh          ← sube corpus y scripts a S3
│   ├── manual_step.sh        ← crea cluster EMR y lanza el job
│   ├── setup.sh              ← todo en uno (corpus + S3 + EMR)
│   ├── status.sh             ← estado de S3, clústeres y output
│   ├── clean_local.sh        ← limpia archivos locales generados
│   └── cleanup.sh            ← elimina todos los recursos de AWS
└── requirements.txt
```

---

## Requisitos

- Cuenta de AWS con permisos para EMR, S3 e IAM
- AWS CLI configurado (en **AWS Cloud Shell** ya está listo, boto3 incluido)
- Python 3.7+

---

## Instalación

```bash
git clone <url-del-repo>
cd invert_index_emr
wc -l titles.txt    # debe mostrar 39608
```

---

## Procedimiento completo

### Paso 1 — Generar el corpus

Convierte `titles.txt` en un único `corpus.txt` donde cada línea es `doc_NNNNN.txt\ttítulo`.
Usa `--target-mb` para escalar el corpus replicando los títulos.

```bash
# Corpus base (~1.8MB) — guarda en disco local
python3 scripts/build_corpus.py

# Corpus de 500MB — guarda en disco local
python3 scripts/build_corpus.py --target-mb 500

# Corpus de 5GB — stream directo a S3 (Cloud Shell no tiene espacio suficiente)
python3 scripts/build_corpus.py --target-mb 5000 --s3 mi-indice-gutenberg

# Muestra rápida de 1000 títulos
python3 scripts/build_corpus.py --sample 1000
```

> **Nota:** Cloud Shell tiene ~1GB de disco. Para corpus de 5GB usa `--s3` para subir directo sin pasar por disco local.

Salida esperada (modo local):

```
Títulos base  : 39,608
Total docs    : 39,608
Corpus        : data/corpus.txt

✓ corpus.txt  :  39,608 docs  /  1.8 MB
```

Salida esperada (modo `--s3`):

```
Títulos base  : 39,608
Repeticiones  : 2,126x  (para alcanzar ~5,000MB)
Total docs    : 84,206,608
Modo          : stream directo a S3 (sin disco local)

  0.45 GB subidos...
  1.23 GB subidos...
  ...
✓ corpus.txt  →  s3://mi-indice-gutenberg/input/corpus.txt  (5.00 GB)
✓ doc_map.txt →  s3://mi-indice-gutenberg/doc_map.txt
```

---

### Paso 2 — Prueba local (sin AWS)

Valida el pipeline antes de gastar en EMR:

```bash
python3 scripts/test_local.py
```

```
Corpus : data/corpus.txt  (1.8 MB)

[1/4] Mapper...      192,450 registros emitidos
[2/4] Shuffle...
[3/4] Combiner...    187,279 registros tras combiner
[4/4] Reducer...     24,306 palabras únicas en el índice
```

---

### Paso 3 — Búsquedas de prueba (local)

```bash
python3 search/search.py --local data/index.txt "adventures island"
python3 search/search.py --local data/index.txt "twenty years after"
python3 search/search.py --local data/index.txt "war peace"
```

```
Búsqueda: "twenty years after"
───────────────────────────────────────────────────────
Palabras buscadas : ['twenty', 'years', 'after']
Resultados        : 2

   1. doc_00289.txt  "The Vicomte de Bragelonne; Or, Ten Years Later..."  (score: 4)
   2. doc_00003.txt  "Twenty years after"  (score: 3)
```

---

### Paso 4 — Subir a S3

**Corpus local** (base o 500MB):
```bash
bash scripts/upload_s3.sh
```

**Corpus 5GB** — el flag `--s3` limpia el input anterior y sube directo. Solo falta subir los scripts:
```bash
aws s3 cp src/mapper.py   s3://mi-indice-gutenberg/scripts/mapper.py
aws s3 cp src/combiner.py s3://mi-indice-gutenberg/scripts/combiner.py
aws s3 cp src/reducer.py  s3://mi-indice-gutenberg/scripts/reducer.py
```

---

### Paso 5 — Lanzar en EMR

Elige el número de cores según el tamaño del corpus:

```bash
# Corpus base (~1.8MB) — 1 core
bash scripts/manual_step.sh

# Corpus de 500MB — 2 cores
bash scripts/manual_step.sh --cores 2

# Corpus de 5GB — 3 cores
bash scripts/manual_step.sh --cores 3
```

**Tiempos estimados:**

| Tamaño corpus | Cores | Generación local | Subida S3 | Job EMR |
|---|---|---|---|---|
| 1.8 MB (base) | 1 | segundos | segundos | ~5 min |
| 500 MB | 2 | ~1 min | ~1-2 min | ~10 min |
| 5 GB | 3 | ~3-5 min | ~3-5 min | ~20 min |

Al terminar:

```
╔══════════════════════════════════════════════════╗
║   JOB COMPLETADO                                 ║
╚══════════════════════════════════════════════════╝

  Buscar en el índice:
    python3 search/search.py --s3 mi-indice-gutenberg output/ "twenty years after"

  Terminar cluster (evitar cobros):
    aws emr terminate-clusters --cluster-ids j-XXXXXXXXXXXXX
```

**Terminar todos los clústeres activos de una vez:**

```bash
aws emr terminate-clusters --cluster-ids $(aws emr list-clusters --active \
  --query 'Clusters[*].Id' --output text)
```

---

### Paso 6 — Búsqueda desde S3

```bash
python3 search/search.py --s3 mi-indice-gutenberg output/ "twenty years after"
python3 search/search.py --s3 mi-indice-gutenberg output/ "adventures island"
python3 search/search.py --s3 mi-indice-gutenberg output/ "war peace"
python3 search/search.py --s3 mi-indice-gutenberg output/ "pride prejudice"
```

---

## Verificar estado

```bash
bash scripts/status.sh
```

Muestra estado del bucket S3, output del job, clústeres activos y comandos útiles.

---

## Limpieza

**Solo archivos locales** (corpus, índice):
```bash
bash scripts/clean_local.sh
```

**Todo en AWS** (clúster + bucket S3):
```bash
bash scripts/cleanup.sh
```

---

## Formato del índice generado

```
palabra   [["doc_00001.txt", frecuencia], ["doc_00003.txt", frecuencia], ...]
```

Ejemplo:

```
war        [["doc_00089.txt", 2], ["doc_00412.txt", 1]]
adventure  [["doc_00148.txt", 1], ["doc_00266.txt", 1]]
```

Los documentos están ordenados por frecuencia descendente (mayor relevancia primero).
