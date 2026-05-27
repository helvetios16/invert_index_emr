  # 1. Limpiar clusters activos si hay alguno
  aws emr terminate-clusters --cluster-ids $(aws emr list-clusters --active \
    --query 'Clusters[*].Id' --output text) 2>/dev/null || true

  # 2. Generar corpus 5GB y subir directo a S3 (server-side copy, ~30-60 s)
  python3 scripts/build_corpus.py --target-mb 5000 --s3 mi-indice-gutenberg

  # 3. Subir scripts MapReduce
  aws s3 cp src/mapper.py   s3://mi-indice-gutenberg/scripts/mapper.py
  aws s3 cp src/combiner.py s3://mi-indice-gutenberg/scripts/combiner.py
  aws s3 cp src/reducer.py  s3://mi-indice-gutenberg/scripts/reducer.py

  # 4. Lanzar cluster con 3 cores y correr el job
  bash scripts/manual_step.sh --cores 3

  # 5. Cuando termine, buscar
  python3 search/search.py --s3 mi-indice-gutenberg output/ "twenty years after"

  # 6. Terminar cluster
  aws emr terminate-clusters --cluster-ids <cluster-id-del-paso-4>

  Tiempos estimados:

  ┌──────────────────────────────┬────────────┐
  │             Paso             │   Tiempo   │
  ├──────────────────────────────┼────────────┤
  │ Paso 2 — generar + subir 5GB │ ~1 min     │
  ├──────────────────────────────┼────────────┤
  │ Paso 4 — cluster arranca     │ ~5-10 min  │
  ├──────────────────────────────┼────────────┤
  │ Paso 4 — job MapReduce       │ ~20-30 min │
  ├──────────────────────────────┼────────────┤
  │ Total                        │ ~25-40 min │
  └──────────────────────────────┴────────────┘

  Verificar que el corpus quedó en S3:
  aws s3 ls s3://mi-indice-gutenberg/input/corpus.txt --human-readable
