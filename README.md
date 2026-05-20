# Índice Invertido con Hadoop MapReduce en Amazon EMR

Sistema de recuperación de información distribuido que construye un índice invertido sobre 39,608 títulos de libros del Proyecto Gutenberg, ejecutado sobre un clúster Hadoop en Amazon EMR.

---

## Arquitectura

```
titles.txt (39,608 títulos)
       │
       ▼
  ┌─────────┐     palabra → título → 1
  │ Mapper  │ ──────────────────────────►
  └─────────┘
       │  shuffle & sort
       ▼
  ┌──────────┐    pre-agrega localmente
  │ Combiner │ ──────────────────────────►
  └──────────┘
       │
       ▼
  ┌─────────┐     palabra → [título:N, título:M, ...]
  │ Reducer │ ──────────────────────────►
  └─────────┘
       │
       ▼
  s3://bucket/output/   ←── índice final
       │
       ▼
  search.py  →  resultados rankeados
```

Cada línea de `titles.txt` es un **documento**. El índice mapea cada palabra a los títulos donde aparece, con su frecuencia como base del ranking.

---

## Requisitos

- Cuenta de AWS con permisos para EMR, S3 e IAM
- AWS CLI configurado (en **AWS Cloud Shell** ya está listo)
- Python 3.7+
- `pip install boto3` (solo para búsqueda desde S3)

---

## Instalación

### 1. Clonar el repositorio

```bash
git clone <url-del-repo>
cd invert_index_emr
```

### 2. Verificar el dataset

```bash
wc -l titles.txt        # debe mostrar 39608
head -5 titles.txt      # muestra los primeros títulos
```

---

## Prueba local (sin AWS)

Antes de gastar en EMR, valida que el pipeline funciona localmente:

```bash
python3 scripts/test_local.py
```

Salida esperada:

```
Input : titles.txt
Output: data/index.txt

[1/4] Mapper...
      192,450 registros emitidos
[2/4] Shuffle (sort)...
[3/4] Combiner...
      187,279 registros tras combiner
[4/4] Reducer...
      24,306 palabras únicas en el índice
```

---

## Despliegue en Amazon EMR

### 1. Ejecutar el setup (un solo comando)

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
| 1 | Crea el bucket S3 y sube `titles.txt` y los scripts |
| 2 | Verifica/crea los roles IAM de EMR |
| 3 | Crea clúster: 1 master + 1 core (`m4.large`) |
| 4 | Lanza el job Hadoop Streaming |
| 5 | Muestra los comandos de búsqueda al terminar |

**Tiempo estimado:** 8-12 minutos (5-8 min para el clúster + 2-3 min para el job).  
**Costo estimado:** < $0.05 USD.

### 2. Salida esperada al finalizar

```
╔══════════════════════════════════════════════════╗
║   JOB COMPLETADO EXITOSAMENTE                    ║
╚══════════════════════════════════════════════════╝

  Índice en : s3://mi-indice-gutenberg/output/
  Logs en   : s3://mi-indice-gutenberg/logs/

  ── Buscar en el índice ──────────────────────────
  python3 search/search.py --s3 mi-indice-gutenberg output/ "adventures island"
```

---

## Búsquedas de prueba

### Búsqueda desde S3 (tras ejecutar EMR)

```bash
python3 search/search.py --s3 <bucket> output/ "<consulta>"
```

### Búsqueda local (tras prueba local)

```bash
python3 search/search.py --local data/index.txt "<consulta>"
```

---

### Ejemplos

**Una palabra:**

```bash
python3 search/search.py --local data/index.txt "adventures"
```
```
Búsqueda: "adventures"
──────────────────────────────────────────────
Palabras: ['adventures']
Top 10 resultado(s):

   1. Adventures of Huckleberry Finn  (score: 1)
   2. The Adventures of Tom Sawyer    (score: 1)
   3. Adventures of Sherlock Holmes   (score: 1)
   ...
```

---

**Múltiples palabras (AND):**

```bash
python3 search/search.py --local data/index.txt "adventures island"
```
```
Búsqueda: "adventures island"
──────────────────────────────────────────────
Palabras: ['adventures', 'island']
Top 10 resultado(s):

   1. Fire Island: Being the Adventures of Uncertain Naturalists...  (score: 2)
   2. Sky Island: Being the Further Exciting Adventures of Trot...   (score: 2)
   3. The Swiss Family Robinson; or Adventures in a Desert Island     (score: 2)
   ...
```

---

**Título conocido:**

```bash
python3 search/search.py --local data/index.txt "great expectations"
```
```
Búsqueda: "great expectations"
──────────────────────────────────────────────
Palabras: ['great', 'expectations']
Top 1 resultado(s):

   1. Great Expectations  (score: 2)
```

---

**Más ejemplos:**

```bash
python3 search/search.py --local data/index.txt "war peace"
python3 search/search.py --local data/index.txt "pride prejudice"
python3 search/search.py --local data/index.txt "mystery detective"
python3 search/search.py --local data/index.txt "science nature"
```

---

## Limpieza

Elimina todos los recursos de AWS y archivos locales generados:

```bash
bash scripts/cleanup.sh
```

Deja el proyecto exactamente como después de `git clone`.

---

## Estructura del proyecto

```
invert_index_emr/
├── titles.txt              ← corpus: 39,608 títulos de Project Gutenberg
├── src/
│   ├── mapper.py           ← fase Map: emite (palabra, título, 1)
│   ├── combiner.py         ← optimización: pre-agrega antes del shuffle
│   └── reducer.py          ← fase Reduce: construye el índice final
├── search/
│   └── search.py           ← búsqueda AND con ranking por frecuencia
├── scripts/
│   ├── setup.sh            ← configura S3 + EMR + lanza el job
│   ├── cleanup.sh          ← elimina todos los recursos creados
│   └── test_local.py       ← simula MapReduce localmente
└── requirements.txt
```

---

## Formato del índice generado

Cada línea del output tiene el formato:

```
palabra   [["título1", frecuencia], ["título2", frecuencia], ...]
```

Ejemplo:

```
adventures  [["The Adventures of Tom Sawyer", 1], ["Adventures of Huckleberry Finn", 1], ...]
war         [["War and Peace", 1], ["The Art of War", 1], ...]
```

Los documentos están ordenados por frecuencia descendente dentro de cada entrada.
