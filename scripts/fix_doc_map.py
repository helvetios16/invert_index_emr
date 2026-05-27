#!/usr/bin/env python3
"""
fix_doc_map.py — Re-sube doc_map.txt con los IDs correctos a S3.
No toca el corpus ni el índice EMR. Solo corrige el mapeo doc→título.

Uso:
  python3 scripts/fix_doc_map.py
  python3 scripts/fix_doc_map.py --bucket otro-bucket
"""
import sys
import os
import math
import boto3

ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUCKET = "mi-indice-gutenberg"

args = sys.argv[1:]
i = 0
while i < len(args):
    if args[i] == '--bucket':
        BUCKET = args[i + 1]; i += 2
    else:
        i += 1

s3 = boto3.client('s3')

# ── 1. Leer títulos ───────────────────────────────────────────────────────────
with open(os.path.join(ROOT, 'titles.txt'), 'r', encoding='utf-8') as f:
    titles = [l.strip() for l in f if l.strip()]
print(f"Títulos base  : {len(titles):,}")

# ── 2. Calcular digits (mismo algoritmo que build_corpus.py) ──────────────────
single_bytes = sum(len(f"doc_00000.txt\t{t}\n".encode('utf-8')) for t in titles)
base_repeats = max(1, math.ceil(50 * 1024 * 1024 / single_bytes))
total        = len(titles) * base_repeats
digits       = len(str(total))
print(f"base_repeats  : {base_repeats}  (chunk ~50 MB)")
print(f"Total en base : {total:,}")
print(f"Dígitos       : {digits}  →  doc_{1:0{digits}d}.txt  ..  doc_{total:0{digits}d}.txt")

# ── 3. Verificar contra el corpus real en S3 ──────────────────────────────────
print(f"\nVerificando corpus en s3://{BUCKET}/input/corpus.txt ...")
try:
    resp       = s3.get_object(Bucket=BUCKET, Key='input/corpus.txt', Range='bytes=0-300')
    first_line = resp['Body'].read().decode('utf-8').split('\n')[0]
    corpus_doc = first_line.split('\t')[0]          # ej. "doc_000001.txt"
    corpus_digits = len(corpus_doc.replace('doc_', '').replace('.txt', ''))
    print(f"  Primera línea: {corpus_doc!r}")
    if corpus_digits != digits:
        print(f"  ⚠  El corpus tiene {corpus_digits} dígitos, recalculamos base_repeats...")
        digits = corpus_digits
        # Ajustar base_repeats para que coincida el número de dígitos
        while len(str(len(titles) * base_repeats)) != digits:
            base_repeats += 1
        total = len(titles) * base_repeats
        print(f"  base_repeats ajustado: {base_repeats}, total: {total:,}")
    else:
        print(f"  ✓ Dígitos coinciden ({digits})")
except Exception as e:
    print(f"  No se pudo leer corpus: {e}")
    print(f"  Continuando con cálculo local ({digits} dígitos)")

# ── 4. Prueba: primeras 3 y últimas 3 entradas ────────────────────────────────
print("\nMuestra de entradas que generará doc_map.txt:")
for pos in [1, 2, 3, total - 2, total - 1, total]:
    title = titles[(pos - 1) % len(titles)]
    doc   = f"doc_{pos:0{digits}d}.txt"
    print(f"  {doc}  →  {title[:55]}")

# ── 5. Prueba con un ID real del índice ───────────────────────────────────────
print("\nPrueba con doc IDs reales del índice:")
for test_pos in [255694, 274256, 234648]:
    if test_pos <= total:
        title = titles[(test_pos - 1) % len(titles)]
        doc   = f"doc_{test_pos:0{digits}d}.txt"
        print(f"  {doc}  →  {title[:55]}")
    else:
        print(f"  doc_{test_pos:0{digits}d} fuera de rango (max {total:,})")

# ── 6. Generar y subir ────────────────────────────────────────────────────────
print(f"\nGenerando {total:,} entradas...", end=' ', flush=True)
lines   = []
doc_num = 1
for _ in range(base_repeats):
    for title in titles:
        lines.append(f"doc_{doc_num:0{digits}d}.txt\t{title}\n")
        doc_num += 1

content = ''.join(lines).encode('utf-8')
size_mb = len(content) / 1024 / 1024
print(f"✓  ({size_mb:.1f} MB)")

print(f"Subiendo a s3://{BUCKET}/doc_map.txt...", end=' ', flush=True)
s3.put_object(Bucket=BUCKET, Key='doc_map.txt', Body=content)
print("✓")

print(f"\n✓ Listo. Ahora busca de nuevo:")
print(f'  python3 search/search.py --s3 {BUCKET} output/ "red book"')
print(f'  python3 search/search.py --s3 {BUCKET} output/ "twenty years after"')
