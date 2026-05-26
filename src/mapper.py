#!/usr/bin/env python3
"""
Mapper: lee el corpus línea por línea y emite (palabra, doc_id, 1).
Formato de entrada: doc_NNNNN.txt TAB contenido del documento
"""
import sys
import re

STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'is', 'it', 'this', 'that', 'was', 'are', 'be', 'as',
    'by', 'from', 'not', 'have', 'had', 'has', 'he', 'she', 'they', 'we',
    'you', 'i', 'do', 'did', 'so', 'if', 'up', 'out', 'no', 'its', 'my',
    'me', 'him', 'her', 'his', 'our', 'your', 'their', 'been', 'were',
}

TOKEN_RE = re.compile(r'\b[a-z]{2,}\b')


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parts = line.split('\t', 1)
        if len(parts) != 2:
            continue
        doc, content = parts
        for word in TOKEN_RE.findall(content.lower()):
            if word not in STOPWORDS:
                sys.stdout.write(f"{word}\t{doc}\t1\n")


if __name__ == '__main__':
    main()
