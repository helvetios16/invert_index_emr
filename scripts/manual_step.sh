#!/bin/bash
# =============================================================================
# manual_step.sh — Crea cluster EMR y ejecuta el job de índice invertido
#
# PRE-REQUISITO: tener corpus.txt y scripts en S3.
# Si es la primera vez o cambiaste el corpus, ejecuta primero:
#   python3 scripts/build_corpus.py [--target-mb 500]
#   bash scripts/upload_s3.sh [bucket]
#
# Uso:
#   bash scripts/manual_step.sh                          <- usa defaults
#   bash scripts/manual_step.sh mi-bucket us-east-1     <- parámetros custom
# =============================================================================
set -euo pipefail

BUCKET="${1:-mi-indice-gutenberg}"
REGION="${2:-us-east-1}"

# ── 1. Crear cluster ──────────────────────────────────────────────────────────
echo "Creando cluster..."
CLUSTER_ID=$(aws emr create-cluster \
  --name "InvertedIndex-Gutenberg" \
  --release-label emr-7.0.0 \
  --applications Name=Hadoop \
  --instance-groups \
    "InstanceGroupType=MASTER,InstanceCount=1,InstanceType=m4.large" \
    "InstanceGroupType=CORE,InstanceCount=1,InstanceType=m4.large" \
  --use-default-roles \
  --region "$REGION" \
  --log-uri "s3://$BUCKET/logs/" \
  --no-auto-terminate \
  --enable-debugging \
  --query 'ClusterId' \
  --output text)

echo "Cluster ID: $CLUSTER_ID"
echo "Esperando que este listo (5-10 min)..."
aws emr wait cluster-running --cluster-id "$CLUSTER_ID" --region "$REGION"
echo "Cluster listo."

# ── 2. Limpiar output previo ──────────────────────────────────────────────────
aws s3 rm "s3://$BUCKET/output/" --recursive 2>/dev/null || true

# ── 3. Lanzar job MapReduce ───────────────────────────────────────────────────
echo "Lanzando job MapReduce..."
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

echo "Step ID: $STEP_ID"
echo "Esperando que el job termine..."
aws emr wait step-complete --cluster-id "$CLUSTER_ID" --step-id "$STEP_ID" --region "$REGION"

# ── 4. Resultado ──────────────────────────────────────────────────────────────
STATUS=$(aws emr describe-step \
  --cluster-id "$CLUSTER_ID" --step-id "$STEP_ID" --region "$REGION" \
  --query 'Step.Status.State' --output text)

echo ""
echo "Job finalizo con estado: $STATUS"
echo ""
echo "Para buscar:"
echo "  python3 search/search.py --s3 $BUCKET output/ \"twenty years after\""
echo "  python3 search/search.py --s3 $BUCKET output/ \"adventures island\""
echo ""
echo "Para terminar el cluster (evitar cobros):"
echo "  aws emr terminate-clusters --cluster-ids $CLUSTER_ID"
