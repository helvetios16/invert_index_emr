#!/bin/bash
# =============================================================================
# manual_step.sh — Crea cluster EMR y ejecuta el job de índice invertido
#
# PRE-REQUISITO: tener corpus.txt y scripts en S3.
# Si es la primera vez o cambiaste el corpus, ejecuta primero:
#   python3 scripts/build_corpus.py [--target-mb 500|5000]
#   bash scripts/upload_s3.sh [bucket]
#
# Uso:
#   bash scripts/manual_step.sh              <- 4 cores (default)
#   bash scripts/manual_step.sh --cores 2   <- 2 cores
#   bash scripts/manual_step.sh --cores 3   <- 3 cores
#
# Guía de cores según tamaño del corpus:
#   ~1.8MB  → 1 core  (~5 min)
#   ~500MB  → 2 cores (~10 min)
#   ~5GB    → 3-4 cores (~15-20 min)
# =============================================================================
set -euo pipefail

BUCKET="mi-indice-gutenberg"
REGION="us-east-1"
CORES=4

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cores) CORES="$2"; shift 2 ;;
    --bucket) BUCKET="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    *) shift ;;
  esac
done

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   Lanzando job en Amazon EMR                     ║"
echo "╚══════════════════════════════════════════════════╝"
echo "  Bucket : s3://$BUCKET"
echo "  Región : $REGION"
echo "  Cluster: 1 master + $CORES core(s)  (m4.large)"
echo ""

# ── Validaciones previas ──────────────────────────────────────────────────────
if ! [[ "$CORES" =~ ^[0-9]+$ ]] || [ "$CORES" -lt 1 ]; then
  echo "ERROR: --cores debe ser un número >= 1 (recibido: '$CORES')"
  exit 1
fi

echo "Verificando recursos en S3..."
for KEY in "input/corpus.txt" "scripts/mapper.py" "scripts/combiner.py" "scripts/reducer.py"; do
  if ! aws s3 ls "s3://$BUCKET/$KEY" >/dev/null 2>&1; then
    echo "ERROR: no existe s3://$BUCKET/$KEY"
    echo "Ejecuta primero: bash scripts/upload_s3.sh"
    exit 1
  fi
done
echo "✓ Todos los archivos encontrados en S3."
echo ""

# ── Trap: terminar cluster si se interrumpe ───────────────────────────────────
CLUSTER_ID=""
cleanup() {
  if [ -n "$CLUSTER_ID" ]; then
    echo ""
    echo "Interrupción detectada. Terminando cluster $CLUSTER_ID ..."
    aws emr terminate-clusters --cluster-ids "$CLUSTER_ID" --region "$REGION" 2>/dev/null || true
    echo "Cluster terminado."
  fi
  exit 1
}
trap cleanup INT TERM

# ── 1. Crear cluster ──────────────────────────────────────────────────────────
echo "[ 1/3 ] Creando cluster..."
CLUSTER_ID=$(aws emr create-cluster \
  --name "InvertedIndex-Gutenberg" \
  --release-label emr-7.0.0 \
  --applications Name=Hadoop \
  --instance-groups \
    "InstanceGroupType=MASTER,InstanceCount=1,InstanceType=m4.large" \
    "InstanceGroupType=CORE,InstanceCount=$CORES,InstanceType=m4.large" \
  --use-default-roles \
  --region "$REGION" \
  --log-uri "s3://$BUCKET/logs/" \
  --no-auto-terminate \
  --enable-debugging \
  --query 'ClusterId' \
  --output text)

echo "        Cluster ID: $CLUSTER_ID"
echo "        Esperando que este listo (5-10 min)..."
aws emr wait cluster-running --cluster-id "$CLUSTER_ID" --region "$REGION"
echo "        ✓ Cluster listo."

# ── 2. Limpiar output previo ──────────────────────────────────────────────────
aws s3 rm "s3://$BUCKET/output/" --recursive 2>/dev/null || true

# ── 3. Lanzar job MapReduce ───────────────────────────────────────────────────
echo ""
echo "[ 2/3 ] Lanzando job MapReduce..."
STEP_ID=$(aws emr add-steps \
  --cluster-id "$CLUSTER_ID" \
  --region "$REGION" \
  --steps "[{
    \"Type\": \"CUSTOM_JAR\",
    \"Name\": \"InvertedIndex\",
    \"ActionOnFailure\": \"CONTINUE\",
    \"Jar\": \"command-runner.jar\",
    \"Args\": [
      \"hadoop-streaming\",
      \"-files\", \"s3://$BUCKET/scripts/mapper.py,s3://$BUCKET/scripts/combiner.py,s3://$BUCKET/scripts/reducer.py\",
      \"-mapper\",   \"mapper.py\",
      \"-combiner\", \"combiner.py\",
      \"-reducer\",  \"reducer.py\",
      \"-input\",    \"s3://$BUCKET/input/\",
      \"-output\",   \"s3://$BUCKET/output/\"
    ]
  }]" \
  --query 'StepIds[0]' \
  --output text)

echo "        Step ID: $STEP_ID"
echo "        Esperando que el job termine..."
aws emr wait step-complete --cluster-id "$CLUSTER_ID" --step-id "$STEP_ID" --region "$REGION"

# ── 4. Resultado ──────────────────────────────────────────────────────────────
STATUS=$(aws emr describe-step \
  --cluster-id "$CLUSTER_ID" --step-id "$STEP_ID" --region "$REGION" \
  --query 'Step.Status.State' --output text)

echo ""
echo "[ 3/3 ] Resultado: $STATUS"
echo ""
echo "╔══════════════════════════════════════════════════╗"
if [[ "$STATUS" == "COMPLETED" ]]; then
echo "║   JOB COMPLETADO                                 ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "  Buscar en el índice:"
echo "    python3 search/search.py --s3 $BUCKET output/ \"twenty years after\""
echo "    python3 search/search.py --s3 $BUCKET output/ \"adventures island\""
echo "    python3 search/search.py --s3 $BUCKET output/ \"war peace\""
else
echo "║   JOB FALLÓ — Estado: $STATUS"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "  Ver logs:"
echo "    aws s3 cp s3://$BUCKET/logs/$CLUSTER_ID/steps/$STEP_ID/stderr.gz - | gunzip -c"
fi
echo ""
echo "  Terminar cluster (evitar cobros):"
echo "    aws emr terminate-clusters --cluster-ids $CLUSTER_ID"
