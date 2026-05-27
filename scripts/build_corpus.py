#!/usr/bin/env python3
"""
Genera el corpus del índice invertido.
Formato por línea:  doc_NNNNN.txt TAB título del libro

Uso:
  # Corpus local (~1.8MB, cabe en Cloud Shell)
  python3 scripts/build_corpus.py
  python3 scripts/build_corpus.py --sample 1000
  python3 scripts/build_corpus.py --target-mb 500

  # Corpus grande directo a S3 (sin usar disco local)
  python3 scripts/build_corpus.py --target-mb 5000 --s3 mi-indice-gutenberg
"""
import os
import sys
import io

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def generate_lines(titles, repeats):
    total  = len(titles) * repeats
    digits = len(str(total))
    doc_num = 1
    for _ in range(repeats):
        for title in titles:
            yield f"doc_{doc_num:0{digits}d}.txt\t{title}\n", doc_num
            doc_num += 1


def write_local(titles, repeats, corpus_file, map_file):
    total  = len(titles) * repeats
    digits = len(str(total))

    os.makedirs(os.path.dirname(corpus_file), exist_ok=True)

    with open(corpus_file, 'w', encoding='utf-8') as cf, \
         open(map_file,    'w', encoding='utf-8') as mf:

        doc_num = 1
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
                print(f"  {pct:5.1f}%  →  {size_mb:,.1f} MB...", end='\r')

    size_mb = os.path.getsize(corpus_file) / 1024 / 1024
    print(f"\n✓ corpus.txt  :  {total:,} docs  /  {size_mb:,.1f} MB")


def stream_to_s3(titles, repeats, bucket):
    import boto3

    s3        = boto3.client('s3')
    total     = len(titles) * repeats
    digits    = len(str(total))
    chunk     = 16 * 1024 * 1024  # 16MB por parte (mínimo S3: 5MB)
    parts     = []
    buf       = b''
    part_num  = 1
    uploaded  = 0

    # Limpiar input anterior
    print(f"  Limpiando s3://{bucket}/input/ ...")
    paginator = s3.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket, Prefix='input/'):
        objects = [{'Key': o['Key']} for o in page.get('Contents', [])]
        if objects:
            s3.delete_objects(Bucket=bucket, Delete={'Objects': objects})

    corpus_key = 'input/corpus.txt'
    mpu = s3.create_multipart_upload(Bucket=bucket, Key=corpus_key,
                                     ContentType='text/plain')
    upload_id = mpu['UploadId']

    print(f"  Subiendo directo a s3://{bucket}/{corpus_key} ...")

    try:
        doc_num = 1
        for rep in range(repeats):
            for title in titles:
                doc_id = f"doc_{doc_num:0{digits}d}.txt"
                buf   += f"{doc_id}\t{title}\n".encode('utf-8')
                doc_num += 1

                if len(buf) >= chunk:
                    part = s3.upload_part(Body=buf, Bucket=bucket, Key=corpus_key,
                                          PartNumber=part_num, UploadId=upload_id)
                    parts.append({'PartNumber': part_num, 'ETag': part['ETag']})
                    uploaded += len(buf)
                    buf       = b''
                    part_num += 1
                    print(f"  {uploaded / 1024**3:.2f} GB subidos...", end='\r')

        # Último fragmento
        if buf:
            part = s3.upload_part(Body=buf, Bucket=bucket, Key=corpus_key,
                                  PartNumber=part_num, UploadId=upload_id)
            parts.append({'PartNumber': part_num, 'ETag': part['ETag']})
            uploaded += len(buf)

        s3.complete_multipart_upload(Bucket=bucket, Key=corpus_key,
                                     UploadId=upload_id,
                                     MultipartUpload={'Parts': parts})
        print(f"\n✓ corpus.txt  →  s3://{bucket}/{corpus_key}  "
              f"({uploaded / 1024**3:.2f} GB)")

    except Exception as e:
        s3.abort_multipart_upload(Bucket=bucket, Key=corpus_key, UploadId=upload_id)
        raise e


def upload_map_to_s3(titles, bucket):
    """Sube solo los títulos base (sin replicar) como doc_map.txt."""
    import boto3
    s3      = boto3.client('s3')
    digits  = len(str(len(titles)))
    content = ''.join(
        f"doc_{i:0{digits}d}.txt\t{t}\n" for i, t in enumerate(titles, 1)
    ).encode('utf-8')
    s3.put_object(Bucket=bucket, Key='doc_map.txt', Body=content)
    print(f"✓ doc_map.txt →  s3://{bucket}/doc_map.txt  ({len(titles):,} entradas)")


def main():
    sample    = None
    target_mb = None
    s3_bucket = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--sample':
            sample = int(args[i + 1]); i += 2
        elif args[i] == '--target-mb':
            target_mb = int(args[i + 1]); i += 2
        elif args[i] == '--s3':
            s3_bucket = args[i + 1]; i += 2
        else:
            i += 1

    titles_file = os.path.join(ROOT, 'titles.txt')
    corpus_file = os.path.join(ROOT, 'data', 'corpus.txt')
    map_file    = os.path.join(ROOT, 'data', 'doc_map.txt')

    with open(titles_file, 'r', encoding='utf-8') as f:
        titles = [line.strip() for line in f if line.strip()]

    if sample:
        titles = titles[:sample]

    if target_mb:
        base_bytes = sum(len(f"doc_00000.txt\t{t}\n".encode('utf-8')) for t in titles)
        repeats    = max(1, -(-target_mb * 1024 * 1024 // base_bytes))
    else:
        repeats = 1

    total = len(titles) * repeats

    print(f"Títulos base  : {len(titles):,}")
    if repeats > 1:
        print(f"Repeticiones  : {repeats:,}x  (para alcanzar ~{target_mb:,}MB)")
    print(f"Total docs    : {total:,}")

    if s3_bucket:
        print(f"Modo          : stream directo a S3 (sin disco local)")
        print()
        stream_to_s3(titles, repeats, s3_bucket)
        upload_map_to_s3(titles, s3_bucket)
        print()
        print("Siguiente paso — subir scripts MapReduce:")
        print(f"  aws s3 cp src/mapper.py   s3://{s3_bucket}/scripts/mapper.py")
        print(f"  aws s3 cp src/combiner.py s3://{s3_bucket}/scripts/combiner.py")
        print(f"  aws s3 cp src/reducer.py  s3://{s3_bucket}/scripts/reducer.py")
        print(f"  bash scripts/manual_step.sh --cores 3")
    else:
        print(f"Corpus        : {corpus_file}")
        print(f"Mapeo         : {map_file}")
        print()
        write_local(titles, repeats, corpus_file, map_file)
        print()
        print("Siguiente paso:")
        print("  python3 scripts/test_local.py     ← prueba local")
        print("  bash scripts/upload_s3.sh         ← subir a S3")


if __name__ == '__main__':
    main()
