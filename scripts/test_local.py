#!/usr/bin/env python3
"""
Prueba local del pipeline MapReduce sin necesitar EMR.
Simula las fases Map → Sort → Combine → Sort → Reduce.

Uso:
  python3 scripts/test_local.py
  python3 scripts/test_local.py titles.txt data/index.txt
"""
import os
import sys
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(script, stdin_data, env=None):
    result = subprocess.run(
        [sys.executable, script],
        input=stdin_data,
        capture_output=True,
        env={**os.environ, **(env or {})}
    )
    if result.returncode != 0:
        print(f"ERROR en {script}:\n{result.stderr.decode()}")
        sys.exit(1)
    return result.stdout


def main():
    input_file = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'titles.txt')
    output_file = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'data', 'index.txt')

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    mapper   = os.path.join(ROOT, 'src', 'mapper.py')
    combiner = os.path.join(ROOT, 'src', 'combiner.py')
    reducer  = os.path.join(ROOT, 'src', 'reducer.py')

    print(f"Input : {input_file}")
    print(f"Output: {output_file}")
    print()

    with open(input_file, 'rb') as f:
        raw = f.read()

    # Map
    print("[1/4] Mapper...")
    mapped = run(mapper, raw, env={'map_input_file': input_file})
    print(f"      {len(mapped.splitlines()):,} registros emitidos")

    # Sort (shuffle simulado)
    print("[2/4] Shuffle (sort)...")
    sorted_map = b'\n'.join(sorted(mapped.splitlines()))

    # Combine
    print("[3/4] Combiner...")
    combined = run(combiner, sorted_map)
    sorted_combined = b'\n'.join(sorted(combined.splitlines()))
    print(f"      {len(sorted_combined.splitlines()):,} registros tras combiner")

    # Reduce
    print("[4/4] Reducer...")
    result = run(reducer, sorted_combined)

    with open(output_file, 'wb') as f:
        f.write(result)

    lines = result.splitlines()
    print(f"      {len(lines):,} palabras únicas en el índice")
    print()
    print("Muestra del índice (5 entradas):")
    for line in lines[:5]:
        decoded = line.decode('utf-8')
        word, docs = decoded.split('\t', 1)
        print(f"  {word:20s} → {docs[:80]}...")
    print()
    print("Para buscar:")
    print(f"  python3 search/search.py --local {output_file} \"adventures island\"")


if __name__ == '__main__':
    main()
