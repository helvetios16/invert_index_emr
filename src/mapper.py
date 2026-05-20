#!/usr/bin/env python3
"""
Mapper: lee el contenido de un documento y emite (palabra, nombre_archivo, 1).
El nombre del archivo (doc_00001.txt) se obtiene de la variable de entorno
que Hadoop Streaming expone por cada archivo de entrada.
"""
import sys
import os
import re

STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'is', 'it', 'this', 'that', 'was', 'are', 'be', 'as',
    'by', 'from', 'not', 'have', 'had', 'has', 'he', 'she', 'they', 'we',
    'you', 'i', 'do', 'did', 'so', 'if', 'up', 'out', 'no', 'its', 'my',
    'me', 'him', 'her', 'his', 'our', 'your', 'their', 'been', 'were',
}

TOKEN_RE = re.compile(r'\b[a-z]{2,}\b')


def get_doc_name():
    path = os.environ.get(
        'mapreduce_map_input_file',
        os.environ.get('map_input_file', 'unknown.txt')
    )
    return os.path.basename(path)


def main():
    doc = get_doc_name()
    for line in sys.stdin:
        for word in TOKEN_RE.findall(line.lower()):
            if word not in STOPWORDS:
                sys.stdout.write(f"{word}\t{doc}\t1\n")


if __name__ == '__main__':
    main()
