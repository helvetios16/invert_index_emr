#!/bin/bash
# =============================================================================
# cleanup.sh — Elimina todo lo creado en AWS y localmente.
# Deja el proyecto como si solo se hubiera hecho git clone.
#
# Uso:
#   bash scripts/cleanup.sh <nombre-bucket> [región]
#   bash scripts/cleanup.sh                          ← lee .emr_state automático
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_FILE="$ROOT_DIR/.emr_state"

# ── Leer parámetros (argumento o .emr_state) ──────────────────────────────────
if [[ -n "${1:-}" ]]; then
  BUCKET="$1"
  REGION="${2:-${AWS_DEFAULT_REGION:-us-east-1}}"
  CLUSTER_ID=""
elif [[ -f "$STATE_FILE" ]]; then
  source "$STATE_FILE"
  echo "  Leído desde .emr_state:"
  echo "    BUCKET=$BUCKET"
  echo "    REGION=$REGION"
  echo "    CLUSTER_ID=${CLUSTER_ID:-no guardado}"
else
  echo "Uso: bash scripts/cleanup.sh <bucket> [región]"
  echo "     (o ejecuta setup.sh primero para generar .emr_state)"
  exit 1
fi

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   Limpieza — Eliminar recursos de AWS            ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "  Se eliminará:"
echo "    • Clúster EMR : ${CLUSTER_ID:-buscar activos en la cuenta}"
echo "    • Bucket S3   : s3://$BUCKET (todos sus archivos)"
echo "    • Archivos locales: data/"
echo ""
read -r -p "  ¿Continuar? [s/N] " confirm
[[ "$confirm" =~ ^[sS]$ ]] || { echo "Cancelado."; exit 0; }
echo ""

# ── PASO 1: Terminar clúster EMR ──────────────────────────────────────────────
echo "[ 1/3 ] Terminando clúster(es) EMR..."

if [[ -n "$CLUSTER_ID" ]]; then
  # Usar el ID guardado
  STATUS=$(aws emr describe-cluster \
    --cluster-id "$CLUSTER_ID" \
    --region "$REGION" \
    --query 'Cluster.Status.State' \
    --output text 2>/dev/null || echo "NOT_FOUND")

  if [[ "$STATUS" == "TERMINATED" || "$STATUS" == "TERMINATED_WITH_ERRORS" || "$STATUS" == "NOT_FOUND" ]]; then
    echo "        Clúster $CLUSTER_ID ya estaba terminado ($STATUS)."
  else
    aws emr terminate-clusters \
      --cluster-ids "$CLUSTER_ID" \
      --region "$REGION"
    echo "        ✓ Clúster $CLUSTER_ID terminado (estaba: $STATUS)."
  fi
else
  # Buscar clústeres activos llamados InvertedIndex-Gutenberg
  ACTIVE=$(aws emr list-clusters \
    --region "$REGION" \
    --active \
    --query "Clusters[?Name=='InvertedIndex-Gutenberg'].Id" \
    --output text 2>/dev/null || echo "")

  if [[ -n "$ACTIVE" ]]; then
    aws emr terminate-clusters --cluster-ids $ACTIVE --region "$REGION"
    echo "        ✓ Clústeres terminados: $ACTIVE"
  else
    echo "        No se encontraron clústeres activos."
  fi
fi

# ── PASO 2: Vaciar y eliminar bucket S3 ───────────────────────────────────────
echo ""
echo "[ 2/3 ] Eliminando bucket S3: s3://$BUCKET ..."

if aws s3 ls "s3://$BUCKET" 2>/dev/null; then
  # Vaciar (incluyendo versiones si hay versionado)
  aws s3 rm "s3://$BUCKET" --recursive
  # Eliminar el bucket
  aws s3api delete-bucket --bucket "$BUCKET" --region "$REGION"
  echo "        ✓ Bucket eliminado."
else
  echo "        Bucket no existe o ya fue eliminado."
fi

# ── PASO 3: Limpiar archivos locales ──────────────────────────────────────────
echo ""
echo "[ 3/3 ] Limpiando archivos locales..."

rm -rf "$ROOT_DIR/data"
rm -f  "$ROOT_DIR/.emr_state"
echo "        ✓ data/ y .emr_state eliminados."

# ── Resultado ─────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   Limpieza completada                            ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "  El proyecto quedó como después de 'git clone'."
echo "  Para volver a ejecutar:"
echo "    bash scripts/setup.sh <nuevo-bucket> $REGION"
