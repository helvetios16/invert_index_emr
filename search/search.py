#!/usr/bin/env python3
"""
Motor de búsqueda sobre el índice invertido generado por MapReduce.

Uso:
  python3 search.py --local <archivo_indice> <consulta>
  python3 search.py --s3    <bucket> <prefijo_output> <consulta>

Ejemplos:
  python3 search.py --local data/index.txt "adventures island"
  python3 search.py --s3 mi-bucket output/ "war peace"
"""
import sys
import re
import json
from collections import defaultdict

STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'is', 'it', 'this', 'that', 'was', 'are', 'be', 'as',
    'by', 'from', 'not', 'have', 'had', 'has', 'he', 'she', 'they', 'we',
    'you', 'i', 'do', 'did', 'so', 'if', 'up', 'out', 'no', 'its', 'my',
    'me', 'him', 'her', 'his', 'our', 'your', 'their', 'been', 'were',
}

TOKEN_RE = re.compile(r'\b[a-z]{2,}\b')


def tokenize(query):
    return [w for w in TOKEN_RE.findall(query.lower()) if w not in STOPWORDS]


# ── Carga del índice ────────────────────────────────────────────────────────────

def load_index_local(filepath):
    index = {}
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if '\t' not in line:
                continue
            word, docs_json = line.split('\t', 1)
            try:
                index[word] = {title: cnt for title, cnt in json.loads(docs_json)}
            except (json.JSONDecodeError, ValueError):
                pass
    return index


def load_index_s3(bucket, prefix):
    import boto3
    s3 = boto3.client('s3')
    index = {}

    paginator = s3.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get('Contents', []):
            key = obj['Key']
            if key.endswith('_SUCCESS') or key.endswith('/'):
                continue
            response = s3.get_object(Bucket=bucket, Key=key)
            for raw in response['Body'].iter_lines():
                line = raw.decode('utf-8').strip()
                if '\t' not in line:
                    continue
                word, docs_json = line.split('\t', 1)
                try:
                    docs = {t: c for t, c in json.loads(docs_json)}
                    if word in index:
                        for t, c in docs.items():
                            index[word][t] = index[word].get(t, 0) + c
                    else:
                        index[word] = docs
                except (json.JSONDecodeError, ValueError):
                    pass
    return index


# ── Motor de búsqueda ───────────────────────────────────────────────────────────

def search(index, query, top_n=10):
    """
    Búsqueda AND: retorna documentos que contienen TODAS las palabras.
    Ranking: suma de frecuencias de las palabras query en cada documento.
    """
    words = tokenize(query)
    if not words:
        return [], []

    # Intersección de conjuntos (AND)
    matching = None
    found = []
    for word in words:
        if word not in index:
            return [], words          # palabra inexistente → sin resultados AND
        docs_set = set(index[word].keys())
        matching = docs_set if matching is None else matching & docs_set
        found.append(word)

    if not matching:
        return [], found

    # Score = suma de tf por cada palabra buscada
    scores = defaultdict(int)
    for word in found:
        for doc, tf in index[word].items():
            if doc in matching:
                scores[doc] += tf

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return ranked[:top_n], found


# ── CLI ─────────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ('--local', '--s3'):
        print(__doc__)
        sys.exit(1)

    mode = sys.argv[1]

    if mode == '--local':
        if len(sys.argv) < 4:
            print("Faltan argumentos: --local <archivo> <consulta>")
            sys.exit(1)
        index_file = sys.argv[2]
        query = ' '.join(sys.argv[3:])
        print(f"Cargando índice desde {index_file}...")
        index = load_index_local(index_file)

    else:  # --s3
        if len(sys.argv) < 5:
            print("Faltan argumentos: --s3 <bucket> <prefijo> <consulta>")
            sys.exit(1)
        bucket, prefix = sys.argv[2], sys.argv[3]
        query = ' '.join(sys.argv[4:])
        print(f"Cargando índice desde s3://{bucket}/{prefix} ...")
        index = load_index_s3(bucket, prefix)

    print(f"Índice: {len(index):,} palabras únicas\n")
    print(f'Búsqueda: "{query}"')
    print("─" * 50)

    results, words = search(index, query)

    if not results:
        print(f"Sin resultados para: {words}")
        sys.exit(0)

    print(f"Palabras: {words}")
    print(f"Top {len(results)} resultado(s):\n")
    for rank, (title, score) in enumerate(results, 1):
        print(f"  {rank:2}. {title}  (score: {score})")


if __name__ == '__main__':
    main()
