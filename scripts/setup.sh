#!/bin/bash
# =============================================================================
# setup.sh — Configura S3, crea clúster EMR y ejecuta el índice invertido
#
# Uso:
#   bash scripts/setup.sh <nombre-bucket-s3> [región]
#
# Ejemplo:
#   bash scripts/setup.sh mi-inverted-index-2024 us-east-1
#
# Pre-requisitos:
#   - AWS CLI instalado y configurado (ya listo en Cloud Shell)
#   - Este script se ejecuta desde la raíz del repositorio
# =============================================================================
set -euo pipefail

# ── Argumentos ────────────────────────────────────────────────────────────────
BUCKET="${1:-}"
REGION="${2:-${AWS_DEFAULT_REGION:-us-east-1}}"
RELEASE="emr-7.0.0"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -z "$BUCKET" ]]; then
  echo "Uso: bash scripts/setup.sh <nombre-bucket> [región]"
  echo "Ej:  bash scripts/setup.sh mi-indice-2024 us-east-1"
  exit 1
fi

# ── Validar AWS ───────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   Índice Invertido — Hadoop MapReduce en EMR     ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "  Bucket : s3://$BUCKET"
echo "  Región : $REGION"
echo "  Release: $RELEASE"
echo ""

aws sts get-caller-identity --query 'Account' --output text > /dev/null || {
  echo "ERROR: AWS no configurado. En Cloud Shell ya debería estar listo."
  exit 1
}

# ── PASO 1: Crear bucket S3 ───────────────────────────────────────────────────
echo "[ 1/5 ] Configurando bucket S3..."
if aws s3 ls "s3://$BUCKET" 2>/dev/null; then
  echo "        Ya existe, continuando."
else
  if [[ "$REGION" == "us-east-1" ]]; then
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION"
  else
    aws s3api create-bucket \
      --bucket "$BUCKET" \
      --region "$REGION" \
      --create-bucket-configuration LocationConstraint="$REGION"
  fi
  echo "        Bucket creado: s3://$BUCKET"
fi

# ── PASO 2: Subir archivos a S3 ───────────────────────────────────────────────
echo ""
echo "[ 2/5 ] Subiendo datos y scripts a S3..."

# Verificar que los documentos existen
if [ ! -d "$ROOT_DIR/data/documents" ]; then
  echo "        ERROR: no existe data/documents/"
  echo "        Ejecuta primero: python3 scripts/split_titles.py"
  exit 1
fi

# Subir documentos individuales
DOC_COUNT=$(find "$ROOT_DIR/data/documents" -name "*.txt" | wc -l | tr -d ' ')
echo "        Subiendo $DOC_COUNT documentos a S3 (puede tardar unos minutos)..."
aws s3 sync "$ROOT_DIR/data/documents/" "s3://$BUCKET/input/" --quiet
echo "        ✓ $DOC_COUNT docs  →  s3://$BUCKET/input/"

# Subir mapeo filename → título (para la búsqueda)
aws s3 cp "$ROOT_DIR/data/doc_map.txt" "s3://$BUCKET/doc_map.txt"
echo "        ✓ doc_map.txt  →  s3://$BUCKET/"

# Subir scripts MapReduce
aws s3 cp "$ROOT_DIR/src/mapper.py"   "s3://$BUCKET/scripts/mapper.py"
aws s3 cp "$ROOT_DIR/src/combiner.py" "s3://$BUCKET/scripts/combiner.py"
aws s3 cp "$ROOT_DIR/src/reducer.py"  "s3://$BUCKET/scripts/reducer.py"
echo "        ✓ mapper / combiner / reducer  →  s3://$BUCKET/scripts/"

# Limpiar output previo
aws s3 rm "s3://$BUCKET/output/" --recursive 2>/dev/null || true

# ── PASO 3: Roles EMR ─────────────────────────────────────────────────────────
echo ""
echo "[ 3/5 ] Verificando roles IAM de EMR..."
if ! aws iam get-role --role-name EMR_DefaultRole >/dev/null 2>&1; then
  echo "        Creando roles por defecto..."
  aws emr create-default-roles
  echo "        ✓ Roles creados."
else
  echo "        ✓ Roles ya existen."
fi

# ── PASO 4: Crear clúster EMR ─────────────────────────────────────────────────
echo ""
echo "[ 4/5 ] Creando clúster EMR (puede tardar 5-10 min)..."

CLUSTER_ID=$(aws emr create-cluster \
  --name "InvertedIndex-Gutenberg" \
  --release-label "$RELEASE" \
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

echo "        Cluster ID: $CLUSTER_ID"
echo "        Esperando estado WAITING..."

aws emr wait cluster-running \
  --cluster-id "$CLUSTER_ID" \
  --region "$REGION"

echo "        ✓ Clúster listo."

# ── PASO 5: Ejecutar job MapReduce ────────────────────────────────────────────
echo ""
echo "[ 5/5 ] Ejecutando job Hadoop Streaming..."

STEP_JSON="[{
  \"Type\": \"STREAMING\",
  \"Name\": \"InvertedIndex\",
  \"ActionOnFailure\": \"CONTINUE\",
  \"HadoopJarStep\": {
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
  }
}]"

STEP_ID=$(aws emr add-steps \
  --cluster-id "$CLUSTER_ID" \
  --region "$REGION" \
  --steps "$STEP_JSON" \
  --query 'StepIds[0]' \
  --output text)

echo "        Step ID: $STEP_ID"
echo "        Esperando que el job finalice..."

aws emr wait step-complete \
  --cluster-id "$CLUSTER_ID" \
  --step-id "$STEP_ID" \
  --region "$REGION"

STATUS=$(aws emr describe-step \
  --cluster-id "$CLUSTER_ID" \
  --step-id "$STEP_ID" \
  --region "$REGION" \
  --query 'Step.Status.State' \
  --output text)

# ── Resultado ─────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════╗"
if [[ "$STATUS" == "COMPLETED" ]]; then
  echo "║   JOB COMPLETADO EXITOSAMENTE                    ║"
  echo "╚══════════════════════════════════════════════════╝"
  echo ""
  echo "  Índice en : s3://$BUCKET/output/"
  echo "  Logs en   : s3://$BUCKET/logs/"
  echo ""
  echo "  ── Buscar en el índice ──────────────────────────"
  echo "  python3 search/search.py --s3 $BUCKET output/ \"adventures island\""
  echo "  python3 search/search.py --s3 $BUCKET output/ \"war peace\""
  echo "  python3 search/search.py --s3 $BUCKET output/ \"pride prejudice\""
  echo ""
  echo "  ── Terminar el clúster (evitar costos) ──────────"
  echo "  aws emr terminate-clusters --cluster-ids $CLUSTER_ID"
else
  echo "║   JOB FALLÓ — Estado: $STATUS"
  echo "╚══════════════════════════════════════════════════╝"
  echo ""
  echo "  Revisa los logs en:"
  echo "  s3://$BUCKET/logs/$CLUSTER_ID/steps/$STEP_ID/"
  exit 1
fi

# Guardar IDs para referencia
echo ""
echo "  CLUSTER_ID=$CLUSTER_ID" > "$ROOT_DIR/.emr_state"
echo "  BUCKET=$BUCKET"         >> "$ROOT_DIR/.emr_state"
echo "  REGION=$REGION"         >> "$ROOT_DIR/.emr_state"
echo "  (IDs guardados en .emr_state)"
