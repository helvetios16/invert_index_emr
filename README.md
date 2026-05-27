# Índice Invertido con Hadoop MapReduce en Amazon EMR

Sistema de recuperación de información distribuido que construye un índice invertido sobre 39,608 títulos de libros del Proyecto Gutenberg, ejecutado sobre un clúster Hadoop en Amazon EMR.

---

## Arquitectura

```
titles.txt (39,608 títulos)
       │
       ▼
build_corpus.py
       │  genera un único corpus.txt con formato: doc_NNNNN.txt TAB título
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
├── titles.txt               ← corpus: 39,608 títulos de Project Gutenberg
├── src/
│   ├── mapper.py            ← fase Map: lee doc_id TAB contenido → (palabra, doc, 1)
│   ├── combiner.py          ← pre-agrega localmente antes del shuffle
│   └── reducer.py           ← fase Reduce: construye el índice final
├── search/
│   └── search.py            ← búsqueda AND con ranking por frecuencia
├── scripts/
│   ├── build_corpus.py      ← genera data/corpus.txt (1 archivo, escalable)
│   ├── setup.sh             ← configura S3 + EMR + lanza el job (todo en uno)
│   ├── clean_local.sh       ← limpia archivos generados localmente
│   ├── cleanup.sh           ← elimina todos los recursos de AWS
│   ├── status.sh            ← muestra estado de S3, EMR y clústeres
│   └── test_local.py        ← simula MapReduce localmente sin AWS
├── manual_step.txt          ← crea cluster y lanza job (cuando S3 ya está listo)
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

Convierte `titles.txt` en un único archivo `corpus.txt` donde cada línea es `doc_NNNNN.txt\ttítulo`.

```bash
# Corpus base con todos los títulos (~1.8MB)
python3 scripts/build_corpus.py

# Corpus de 500MB (para demo de escala)
python3 scripts/build_corpus.py --target-mb 500

# Corpus de ~5GB
python3 scripts/build_corpus.py --target-mb 5000

# Muestra rápida de 1000 títulos
python3 scripts/build_corpus.py --sample 1000
```

Salida esperada:

```
Títulos base  : 39608
Total docs    : 39608
Corpus        : data/corpus.txt
Mapeo         : data/doc_map.txt

✓ corpus.txt  :  39,608 docs  /  1.8 MB
```

---

### Paso 2 — Prueba local (sin AWS)

Valida el pipeline completo en tu máquina antes de gastar en EMR.

```bash
python3 scripts/test_local.py
```

Salida esperada:

```
Corpus : data/corpus.txt  (1.8 MB)
Output : data/index.txt

[1/4] Mapper...
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

### Paso 3 — Búsquedas de prueba (local)

```bash
python3 search/search.py --local data/index.txt "<consulta>"
```

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
```

**Múltiples palabras (AND):**

```bash
python3 search/search.py --local data/index.txt "twenty years after"
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

Solo necesario la **primera vez** o cuando cambies el corpus:

```bash
# Limpiar input anterior si existe
aws s3 rm s3://mi-indice-gutenberg/input/ --recursive

# Subir corpus (1 archivo, tarda segundos)
aws s3 cp data/corpus.txt   s3://mi-indice-gutenberg/input/corpus.txt
aws s3 cp data/doc_map.txt  s3://mi-indice-gutenberg/doc_map.txt

# Subir scripts MapReduce
aws s3 cp src/mapper.py     s3://mi-indice-gutenberg/scripts/mapper.py
aws s3 cp src/combiner.py   s3://mi-indice-gutenberg/scripts/combiner.py
aws s3 cp src/reducer.py    s3://mi-indice-gutenberg/scripts/reducer.py
```

---

### Paso 5 — Lanzar en EMR

```bash
bash manual_step.txt
```

El script crea el clúster, espera que esté listo, lanza el job y muestra el resultado.

**Configuración del clúster:**
- 1 master `m4.large` + 1 core `m4.large`
- Costo: ~$0.20/hr · Job tarda ~5-15 min según tamaño del corpus

**Tiempos estimados:**

| Tamaño corpus | Subida a S3 | Job EMR |
|---|---|---|
| 1.8 MB (base) | segundos | ~5 min |
| 500 MB | ~1-2 min | ~10 min |
| 5 GB | ~3-5 min | ~20-30 min |

Al terminar:

```
Job finalizo con estado: COMPLETED

Para buscar:
  python3 search/search.py --s3 mi-indice-gutenberg output/ "twenty years after"

Para terminar el cluster (evitar cobros):
  aws emr terminate-clusters --cluster-ids j-XXXXXXXXXXXXX
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

## Verificar estado del proyecto

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

**Todo en AWS** (clúster + bucket S3 completo):
```bash
bash scripts/cleanup.sh
```

Ambos dejan el proyecto como después de `git clone`.

---

## Formato del índice generado

Cada línea del output de Hadoop:

```
palabra   [["doc_00001.txt", frecuencia], ["doc_00003.txt", frecuencia], ...]
```

Ejemplo:

```
war        [["doc_00089.txt", 2], ["doc_00412.txt", 1], ["doc_00531.txt", 1]]
adventure  [["doc_00148.txt", 1], ["doc_00266.txt", 1]]
```

Los documentos están ordenados por frecuencia descendente (mayor relevancia primero).
