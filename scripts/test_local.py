#!/usr/bin/env python3
"""
Prueba local del pipeline MapReduce sin necesitar EMR.
Simula Map → Shuffle → Combine → Reduce procesando los archivos de data/documents/.

Requiere ejecutar primero:
  python3 scripts/split_titles.py

Uso:
  python3 scripts/test_local.py
  python3 scripts/test_local.py data/documents data/index.txt
"""
import os
import sys
import re
import json
from collections import defaultdict
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'is', 'it', 'this', 'that', 'was', 'are', 'be', 'as',
    'by', 'from', 'not', 'have', 'had', 'has', 'he', 'she', 'they', 'we',
    'you', 'i', 'do', 'did', 'so', 'if', 'up', 'out', 'no', 'its', 'my',
    'me', 'him', 'her', 'his', 'our', 'your', 'their', 'been', 'were',
}
TOKEN_RE = re.compile(r'\b[a-z]{2,}\b')


def mapper_phase(docs_dir):
    records = []
    files = sorted(Path(docs_dir).glob('*.txt'))
    total = len(files)
    print(f"      {total:,} documentos encontrados")

    for i, filepath in enumerate(files, 1):
        doc = filepath.name
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                for word in TOKEN_RE.findall(line.lower()):
                    if word not in STOPWORDS:
                        records.append((word, doc, 1))
        if i % 10000 == 0 or i == total:
            print(f"      {i:>{len(str(total))}}/{total} archivos mapeados...")

    return records


def combiner_phase(records):
    counts = defaultdict(int)
    for word, doc, count in records:
        counts[(word, doc)] += count
    return [(w, d, c) for (w, d), c in counts.items()]


def reducer_phase(records, output_file):
    index = defaultdict(lambda: defaultdict(int))
    for word, doc, count in records:
        index[word][doc] += count

    with open(output_file, 'w', encoding='utf-8') as f:
        for word in sorted(index.keys()):
            sorted_docs = sorted(index[word].items(), key=lambda x: x[1], reverse=True)
            f.write(f"{word}\t{json.dumps(sorted_docs, ensure_ascii=False)}\n")

    return len(index)


def main():
    docs_dir    = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'data', 'documents')
    output_file = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'data', 'index.txt')
    map_file    = os.path.join(ROOT, 'data', 'doc_map.txt')

    if not os.path.isdir(docs_dir):
        print(f"Error: no existe {docs_dir}")
        print("Ejecuta primero:  python3 scripts/split_titles.py")
        sys.exit(1)

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    print(f"Input : {docs_dir}/")
    print(f"Output: {output_file}")
    print()

    print("[1/4] Mapper...")
    records = mapper_phase(docs_dir)
    print(f"      {len(records):,} registros emitidos")

    print("[2/4] Shuffle (sort)...")
    records.sort()

    print("[3/4] Combiner...")
    records = combiner_phase(records)
    records.sort()
    print(f"      {len(records):,} registros tras combiner")

    print("[4/4] Reducer...")
    word_count = reducer_phase(records, output_file)
    print(f"      {word_count:,} palabras únicas en el índice")

    # Cargar mapeo para mostrar muestra legible
    doc_map = {}
    if os.path.exists(map_file):
        with open(map_file, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('\t', 1)
                if len(parts) == 2:
                    doc_map[parts[0]] = parts[1]

    print()
    print("Muestra del índice (3 entradas):")
    with open(output_file, 'r', encoding='utf-8') as f:
        for _ in range(3):
            line = f.readline().strip()
            if not line:
                break
            word, docs_json = line.split('\t', 1)
            docs = json.loads(docs_json)[:2]
            docs_str = ', '.join(
                f'{d}  "{doc_map.get(d, "?")}"' for d, _ in docs
            )
            print(f"  {word:15s} →  {docs_str}")

    print()
    print("Para buscar:")
    print(f"  python3 search/search.py --local {output_file} \"adventures island\"")
    print(f"  python3 search/search.py --local {output_file} \"twenty years after\"")


if __name__ == '__main__':
    main()
