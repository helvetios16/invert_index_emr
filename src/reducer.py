#!/usr/bin/env python3
"""
Reducer: agrupa por palabra y emite el índice invertido final.
Salida: palabra TAB [["título1", count], ["título2", count], ...]
Los títulos se ordenan por frecuencia descendente (ranking base).
"""
import sys
import json
from collections import defaultdict


def emit(word, doc_counts):
    sorted_docs = sorted(doc_counts.items(), key=lambda x: x[1], reverse=True)
    sys.stdout.write(f"{word}\t{json.dumps(sorted_docs, ensure_ascii=False)}\n")


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
                emit(current_word, doc_counts)
            current_word = word
            doc_counts = defaultdict(int)

        doc_counts[doc] += int(count)

    if current_word:
        emit(current_word, doc_counts)


if __name__ == '__main__':
    main()
