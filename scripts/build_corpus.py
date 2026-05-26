#!/usr/bin/env python3
"""
Genera data/corpus.txt: UN solo archivo con todos los documentos.
Formato por línea:  doc_NNNNN.txt TAB título del libro

Ventaja frente a 39k archivos individuales:
  - Subida a S3 en segundos (1 archivo vs 39,608)
  - Hadoop lo divide en bloques de 128MB automáticamente
  - Escalable a cualquier tamaño con --target-mb

Uso:
  python3 scripts/build_corpus.py                   ← todos los títulos (~1.8MB)
  python3 scripts/build_corpus.py --sample 1000     ← muestra rápida
  python3 scripts/build_corpus.py --target-mb 500   ← replicar hasta 500MB
  python3 scripts/build_corpus.py --target-mb 5000  ← replicar hasta ~5GB
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    sample    = None
    target_mb = None

    if '--sample' in sys.argv:
        sample = int(sys.argv[sys.argv.index('--sample') + 1])
    if '--target-mb' in sys.argv:
        target_mb = int(sys.argv[sys.argv.index('--target-mb') + 1])

    titles_file = os.path.join(ROOT, 'titles.txt')
    corpus_file = os.path.join(ROOT, 'data', 'corpus.txt')
    map_file    = os.path.join(ROOT, 'data', 'doc_map.txt')

    os.makedirs(os.path.join(ROOT, 'data'), exist_ok=True)

    with open(titles_file, 'r', encoding='utf-8') as f:
        titles = [line.strip() for line in f if line.strip()]

    if sample:
        titles = titles[:sample]

    # Calcular cuántas repeticiones para alcanzar el tamaño objetivo
    if target_mb:
        base_bytes = sum(len(f"doc_00000.txt\t{t}\n".encode('utf-8')) for t in titles)
        target_bytes = target_mb * 1024 * 1024
        repeats = max(1, -(-target_bytes // base_bytes))  # ceil division
        print(f"Títulos base  : {len(titles):,}")
        print(f"Repeticiones  : {repeats:,}x  (para alcanzar ~{target_mb:,}MB)")
    else:
        repeats = 1
        print(f"Títulos base  : {len(titles):,}")

    total  = len(titles) * repeats
    digits = len(str(total))

    print(f"Total docs    : {total:,}")
    print(f"Corpus        : {corpus_file}")
    print(f"Mapeo         : {map_file}")
    print()

    doc_num = 1
    with open(corpus_file, 'w', encoding='utf-8') as cf, \
         open(map_file,    'w', encoding='utf-8') as mf:

        for rep in range(repeats):
            for title in titles:
                doc_id = f"doc_{doc_num:0{digits}d}.txt"
                line   = f"{doc_id}\t{title}\n"
                cf.write(line)
                mf.write(line)
                doc_num += 1

            if repeats > 1 and (rep + 1) % max(1, repeats // 20) == 0:
                size_mb = os.path.getsize(corpus_file) / 1024 / 1024
                pct     = (rep + 1) / repeats * 100
                print(f"  {pct:5.1f}%  →  {size_mb:,.1f} MB generados...", end='\r')

    size_mb = os.path.getsize(corpus_file) / 1024 / 1024
    print(f"\n✓ corpus.txt  :  {total:,} docs  /  {size_mb:,.1f} MB")
    print()
    print("Siguiente paso:")
    print("  python3 scripts/test_local.py     ← prueba local")
    print("  bash scripts/setup.sh <bucket>    ← deploy en EMR")


if __name__ == '__main__':
    main()
