#!/usr/bin/env python3
"""
Genera el corpus del índice invertido.
Formato por línea:  doc_NNNNN.txt TAB título del libro

Uso:
  # Corpus local (~1.8MB)
  python3 scripts/build_corpus.py
  python3 scripts/build_corpus.py --sample 1000
  python3 scripts/build_corpus.py --target-mb 500

  # Corpus grande directo a S3 (server-side copy, ~30-60 s para 5GB)
  python3 scripts/build_corpus.py --target-mb 500  --s3 mi-indice-gutenberg
  python3 scripts/build_corpus.py --target-mb 5000 --s3 mi-indice-gutenberg
"""
import os
import sys
import io
import math

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── Corpus local ──────────────────────────────────────────────────────────────

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


# ── S3 server-side copy (rápido para ≥ 100 MB) ───────────────────────────────

def stream_to_s3_copy(titles, target_mb, bucket):
    """
    Genera el corpus en S3 sin enviar los datos repetidos por la red:
      1. Genera un chunk base de ~50 MB localmente y lo sube a S3  (único upload)
      2. Usa upload_part_copy para replicar el chunk server-side    (0 bytes por red)
    Tiempo típico: ~30-60 s para 5 GB (vs. ~40 h con el método línea-a-línea).
    """
    import boto3

    s3           = boto3.client('s3')
    target_bytes = target_mb * 1024 * 1024

    # Peso de un ciclo completo de títulos
    single_bytes = sum(len(f"doc_00000.txt\t{t}\n".encode('utf-8')) for t in titles)

    # Tamaño de cada parte: ~50 MB (mínimo S3 es 5 MB para todas menos la última)
    PART_MB      = 50
    PART_BYTES   = PART_MB * 1024 * 1024
    base_repeats = max(1, math.ceil(PART_BYTES / single_bytes))
    base_est     = single_bytes * base_repeats

    # Número de copias server-side
    num_copies = max(1, round(target_bytes / base_est))
    if num_copies > 9_999:            # límite S3: 10 000 partes
        base_repeats = math.ceil(target_bytes / (9_999 * single_bytes))
        base_est     = single_bytes * base_repeats
        num_copies   = math.ceil(target_bytes / base_est)

    print(f"  Estrategia  : S3 server-side copy")
    print(f"  Chunk base  : {base_repeats:,}x títulos  ≈ {base_est/1024/1024:.0f} MB")
    print(f"  Copias S3   : {num_copies} × ≈{base_est/1024/1024:.0f} MB"
          f"  →  ≈{base_est * num_copies / 1024**3:.2f} GB")
    print()

    # ── 1. Generar chunk base en memoria ──────────────────────────────────────
    print("  [1/4] Generando chunk base en memoria...", end=' ', flush=True)
    digits  = len(str(len(titles) * base_repeats))
    buf     = io.BytesIO()
    doc_num = 1
    for _ in range(base_repeats):
        for title in titles:
            buf.write(f"doc_{doc_num:0{digits}d}.txt\t{title}\n".encode('utf-8'))
            doc_num += 1
    base_data    = buf.getvalue()
    actual_base  = len(base_data)
    print(f"✓  ({actual_base / 1024 / 1024:.1f} MB)")

    # ── 2. Limpiar input anterior ──────────────────────────────────────────────
    corpus_key = 'input/corpus.txt'
    base_key   = 'input/corpus_base.txt'

    print("  [2/4] Limpiando input anterior en S3...", end=' ', flush=True)
    paginator = s3.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket, Prefix='input/'):
        objs = [{'Key': o['Key']} for o in page.get('Contents', [])]
        if objs:
            s3.delete_objects(Bucket=bucket, Delete={'Objects': objs})
    print("✓")

    # ── 3. Subir chunk base ────────────────────────────────────────────────────
    print(f"  [3/4] Subiendo chunk base ({actual_base / 1024 / 1024:.1f} MB)...",
          end=' ', flush=True)
    s3.put_object(Bucket=bucket, Key=base_key,
                  Body=base_data, ContentType='text/plain')
    print("✓")

    # ── 4. Multipart copy server-side ─────────────────────────────────────────
    print(f"  [4/4] Ensamblando corpus ({num_copies} copias, 0 datos por red)...")
    mpu       = s3.create_multipart_upload(Bucket=bucket, Key=corpus_key,
                                           ContentType='text/plain')
    upload_id = mpu['UploadId']

    try:
        parts = []
        for i in range(num_copies):
            part_num = i + 1
            resp = s3.upload_part_copy(
                Bucket=bucket, Key=corpus_key,
                PartNumber=part_num, UploadId=upload_id,
                CopySource={'Bucket': bucket, 'Key': base_key},
            )
            parts.append({'PartNumber': part_num,
                           'ETag': resp['CopyPartResult']['ETag']})
            if part_num % 10 == 0 or part_num == num_copies:
                done_gb = actual_base * part_num / 1024 ** 3
                print(f"        {part_num}/{num_copies} partes  ({done_gb:.2f} GB)...",
                      end='\r')

        s3.complete_multipart_upload(
            Bucket=bucket, Key=corpus_key, UploadId=upload_id,
            MultipartUpload={'Parts': parts},
        )
        total_gb = actual_base * num_copies / 1024 ** 3
        print(f"\n  ✓ corpus.txt  →  s3://{bucket}/{corpus_key}  ({total_gb:.2f} GB)")

    except Exception:
        s3.abort_multipart_upload(Bucket=bucket, Key=corpus_key, UploadId=upload_id)
        raise
    finally:
        s3.delete_object(Bucket=bucket, Key=base_key)

    return digits, base_repeats


# ── S3 streaming (fallback para corpus sin --target-mb) ───────────────────────

def stream_to_s3(titles, repeats, bucket):
    import boto3

    s3       = boto3.client('s3')
    total    = len(titles) * repeats
    digits   = len(str(total))
    chunk    = 16 * 1024 * 1024
    parts    = []
    buf      = b''
    part_num = 1
    uploaded = 0

    print(f"  Limpiando s3://{bucket}/input/ ...")
    paginator = s3.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket, Prefix='input/'):
        objects = [{'Key': o['Key']} for o in page.get('Contents', [])]
        if objects:
            s3.delete_objects(Bucket=bucket, Delete={'Objects': objects})

    corpus_key = 'input/corpus.txt'
    mpu        = s3.create_multipart_upload(Bucket=bucket, Key=corpus_key,
                                            ContentType='text/plain')
    upload_id  = mpu['UploadId']
    print(f"  Subiendo directo a s3://{bucket}/{corpus_key} ...")

    try:
        doc_num = 1
        for _ in range(repeats):
            for title in titles:
                buf += f"doc_{doc_num:0{digits}d}.txt\t{title}\n".encode('utf-8')
                doc_num += 1
                if len(buf) >= chunk:
                    part = s3.upload_part(Body=buf, Bucket=bucket, Key=corpus_key,
                                          PartNumber=part_num, UploadId=upload_id)
                    parts.append({'PartNumber': part_num, 'ETag': part['ETag']})
                    uploaded += len(buf)
                    buf       = b''
                    part_num += 1
                    print(f"  {uploaded / 1024**3:.2f} GB subidos...", end='\r')

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


# ── doc_map.txt ───────────────────────────────────────────────────────────────

def upload_map_to_s3(titles, bucket, digits=None, repeats=1):
    """
    Sube doc_map.txt a S3 con los mismos doc IDs que corpus.txt.
    Con repeats > 1 (server-side copy), genera las entradas para TODOS
    los docs del chunk base para que los IDs coincidan con el índice.
    """
    import boto3
    s3    = boto3.client('s3')
    total = len(titles) * repeats
    if digits is None:
        digits = len(str(len(titles)))

    lines   = []
    doc_num = 1
    for _ in range(repeats):
        for title in titles:
            lines.append(f"doc_{doc_num:0{digits}d}.txt\t{title}\n")
            doc_num += 1

    content  = ''.join(lines).encode('utf-8')
    size_mb  = len(content) / 1024 / 1024
    s3.put_object(Bucket=bucket, Key='doc_map.txt', Body=content)
    print(f"✓ doc_map.txt →  s3://{bucket}/doc_map.txt  ({total:,} entradas / {size_mb:.1f} MB)")


# ── main ──────────────────────────────────────────────────────────────────────

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
        if target_mb and target_mb >= 100:
            # Fast path: server-side copy, no data sent over the network repeatedly
            print(f"Modo          : S3 server-side copy (rápido, sin datos por red)")
            print()
            digits, base_repeats = stream_to_s3_copy(titles, target_mb, s3_bucket)
            upload_map_to_s3(titles, s3_bucket, digits=digits, repeats=base_repeats)
        else:
            # Small corpus: upload directly
            print(f"Modo          : stream directo a S3")
            print()
            stream_to_s3(titles, repeats, s3_bucket)
            upload_map_to_s3(titles, s3_bucket)
        print()
        print("Siguiente paso — subir scripts MapReduce:")
        print(f"  aws s3 cp src/mapper.py   s3://{s3_bucket}/scripts/mapper.py")
        print(f"  aws s3 cp src/combiner.py s3://{s3_bucket}/scripts/combiner.py")
        print(f"  aws s3 cp src/reducer.py  s3://{s3_bucket}/scripts/reducer.py")
        if target_mb and target_mb >= 3000:
            print(f"  bash scripts/manual_step.sh --cores 3")
        elif target_mb and target_mb >= 200:
            print(f"  bash scripts/manual_step.sh --cores 2")
        else:
            print(f"  bash scripts/manual_step.sh")
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
