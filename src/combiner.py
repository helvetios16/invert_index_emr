#!/usr/bin/env python3
"""
Combiner: pre-agrega localmente antes del shuffle para reducir datos en red.
Mismo formato entrada/salida: palabra TAB título TAB count
"""
import sys
from collections import defaultdict


def main():
    current_word = None
    doc_counts = defaultdict(int)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parts = line.split('\t')
        if len(parts) != 3:
            continue
        word, doc, count = parts[0], parts[1], parts[2]

        if word != current_word:
            if current_word is not None:
                for d, c in doc_counts.items():
                    sys.stdout.write(f"{current_word}\t{d}\t{c}\n")
            current_word = word
            doc_counts = defaultdict(int)

        doc_counts[doc] += int(count)

    if current_word:
        for d, c in doc_counts.items():
            sys.stdout.write(f"{current_word}\t{d}\t{c}\n")


if __name__ == '__main__':
    main()
