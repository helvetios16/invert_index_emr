#!/usr/bin/env python3
"""
Motor de búsqueda sobre el índice invertido generado por MapReduce.
Muestra: filename  "Título del libro"  (score: N)

Uso:
  python3 search.py --local <index.txt> <consulta>
  python3 search.py --s3    <bucket> <prefijo_output> <consulta>

Ejemplos:
  python3 search.py --local data/index.txt "adventures island"
  python3 search.py --s3 mi-bucket output/ "war peace"
"""
import sys
import re
import json
import os
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


# ── Carga del mapeo doc → título ────────────────────────────────────────────────

def load_doc_map_local(map_file):
    if not os.path.exists(map_file):
        return {}
    doc_map = {}
    with open(map_file, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('\t', 1)
            if len(parts) == 2:
                doc_map[parts[0]] = parts[1]
    return doc_map


def load_doc_map_s3(s3_client, bucket):
    doc_map = {}
    try:
        response = s3_client.get_object(Bucket=bucket, Key='doc_map.txt')
        for raw in response['Body'].iter_lines():
            parts = raw.decode('utf-8').strip().split('\t', 1)
            if len(parts) == 2:
                doc_map[parts[0]] = parts[1]
    except Exception:
        pass
    return doc_map


# ── Carga del índice ─────────────────────────────────────────────────────────────

def load_index_local(filepath):
    index = {}
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if '\t' not in line:
                continue
            word, docs_json = line.split('\t', 1)
            try:
                index[word] = {doc: cnt for doc, cnt in json.loads(docs_json)}
            except (json.JSONDecodeError, ValueError):
                pass
    return index


def load_index_s3(s3_client, bucket, prefix):
    index = {}
    paginator = s3_client.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get('Contents', []):
            key = obj['Key']
            if key.endswith('_SUCCESS') or key.endswith('/'):
                continue
            response = s3_client.get_object(Bucket=bucket, Key=key)
            for raw in response['Body'].iter_lines():
                line = raw.decode('utf-8').strip()
                if '\t' not in line:
                    continue
                word, docs_json = line.split('\t', 1)
                try:
                    docs = {d: c for d, c in json.loads(docs_json)}
                    if word in index:
                        for d, c in docs.items():
                            index[word][d] = index[word].get(d, 0) + c
                    else:
                        index[word] = docs
                except (json.JSONDecodeError, ValueError):
                    pass
    return index


# ── Motor de búsqueda ────────────────────────────────────────────────────────────

def search(index, query, top_n=10):
    """AND search: retorna docs que contienen TODAS las palabras, rankeados por tf."""
    words = tokenize(query)
    if not words:
        return [], []

    matching = None
    found = []
    for word in words:
        if word not in index:
            return [], words
        docs_set = set(index[word].keys())
        matching = docs_set if matching is None else matching & docs_set
        found.append(word)

    if not matching:
        return [], found

    scores = defaultdict(int)
    for word in found:
        for doc, tf in index[word].items():
            if doc in matching:
                scores[doc] += tf

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return ranked[:top_n], found


# ── CLI ──────────────────────────────────────────────────────────────────────────

def print_results(results, words, doc_map):
    if not results:
        print(f"Sin resultados para: {words}")
        return

    print(f"Palabras buscadas : {words}")
    print(f"Resultados        : {len(results)}\n")
    for rank, (doc, score) in enumerate(results, 1):
        title = doc_map.get(doc, '')
        title_str = f'  "{title}"' if title else ''
        print(f"  {rank:2}. {doc}{title_str}  (score: {score})")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ('--local', '--s3'):
        print(__doc__)
        sys.exit(1)

    mode = sys.argv[1]

    if mode == '--local':
        if len(sys.argv) < 4:
            print("Faltan argumentos: --local <index.txt> <consulta>")
            sys.exit(1)
        index_file = sys.argv[2]
        query      = ' '.join(sys.argv[3:])
        map_file   = os.path.join(os.path.dirname(index_file), 'doc_map.txt')

        print(f"Cargando índice desde {index_file}...")
        index   = load_index_local(index_file)
        doc_map = load_doc_map_local(map_file)

    else:  # --s3
        if len(sys.argv) < 5:
            print("Faltan argumentos: --s3 <bucket> <prefijo> <consulta>")
            sys.exit(1)
        import boto3
        bucket = sys.argv[2]
        prefix = sys.argv[3]
        query  = ' '.join(sys.argv[4:])

        print(f"Cargando índice desde s3://{bucket}/{prefix} ...")
        s3      = boto3.client('s3')
        index   = load_index_s3(s3, bucket, prefix)
        doc_map = load_doc_map_s3(s3, bucket)

    print(f"Índice: {len(index):,} palabras únicas\n")
    print(f'Búsqueda: "{query}"')
    print("─" * 55)

    results, words = search(index, query)
    print_results(results, words, doc_map)


if __name__ == '__main__':
    main()
