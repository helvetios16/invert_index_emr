#!/usr/bin/env python3
"""
Mapper: por cada línea (título de libro), emite (palabra, título, 1).
Cada título es tratado como un documento independiente.
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
        title = line.strip()
        if not title:
            continue
        for word in TOKEN_RE.findall(title.lower()):
            if word not in STOPWORDS:
                sys.stdout.write(f"{word}\t{title}\t1\n")


if __name__ == '__main__':
    main()
