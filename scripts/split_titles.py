#!/usr/bin/env python3
"""
Divide titles.txt en archivos individuales: doc_00001.txt, doc_00002.txt, ...
Cada archivo contiene un único título de libro (un "documento").
También genera data/doc_map.txt con el mapeo  filename → título.

Uso:
  python3 scripts/split_titles.py              ← todos los títulos (39,608)
  python3 scripts/split_titles.py --sample 500 ← solo 500 (prueba rápida)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    sample = None
    if '--sample' in sys.argv:
        idx = sys.argv.index('--sample')
        sample = int(sys.argv[idx + 1])

    titles_file = os.path.join(ROOT, 'titles.txt')
    docs_dir    = os.path.join(ROOT, 'data', 'documents')
    map_file    = os.path.join(ROOT, 'data', 'doc_map.txt')

    os.makedirs(docs_dir, exist_ok=True)

    with open(titles_file, 'r', encoding='utf-8') as f:
        titles = [line.strip() for line in f if line.strip()]

    if sample:
        titles = titles[:sample]

    total  = len(titles)
    digits = len(str(total))

    print(f"Dividiendo {total:,} títulos en archivos individuales...")
    print(f"Destino : {docs_dir}/")
    print(f"Mapeo   : {map_file}")
    print()

    with open(map_file, 'w', encoding='utf-8') as mapf:
        for i, title in enumerate(titles, 1):
            filename = f"doc_{i:0{digits}d}.txt"
            filepath = os.path.join(docs_dir, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(title + '\n')

            mapf.write(f"{filename}\t{title}\n")

            if i % 5000 == 0 or i == total:
                pct = i / total * 100
                print(f"  {i:>{digits}}/{total}  ({pct:.0f}%)")

    print()
    print(f"✓ {total:,} archivos creados en data/documents/")
    print()
    print("Siguiente paso:")
    print("  python3 scripts/test_local.py    ← prueba el pipeline localmente")
    print("  bash scripts/setup.sh <bucket>   ← deploy en EMR")


if __name__ == '__main__':
    main()
