#!/bin/bash
# =============================================================================
# run_on_cluster.sh — Lanza el índice invertido (MapReduce) en un cluster EMR
#                     YA EXISTENTE (p. ej. el mismo de cartograph) para comparar
#                     Hive vs MapReduce en hardware idéntico.
#
# Uso:
#   bash scripts/run_on_cluster.sh                       # autodetecta el cluster activo
#   bash scripts/run_on_cluster.sh --cluster-id j-XXXX   # cluster explícito
#   bash scripts/run_on_cluster.sh --bucket <b> --region <r>
# =============================================================================
set -euo pipefail

BUCKET="mi-indice-gutenberg"
REGION="us-east-1"
CLUSTER_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cluster-id) CLUSTER_ID="$2"; shift 2 ;;
    --bucket)     BUCKET="$2";     shift 2 ;;
    --region)     REGION="$2";     shift 2 ;;
    *) shift ;;
  esac
done

# ── Autodetectar el cluster activo si no se pasó ──────────────────────────────
if [[ -z "$CLUSTER_ID" ]]; then
  CLUSTER_ID=$(aws emr list-clusters --active --region "$REGION" \
    --query 'Clusters[].Id' --output text)
  CNT=$(echo $CLUSTER_ID | wc -w)
  if [[ "$CNT" -eq 0 ]]; then
    echo "ERROR: no hay clusters activos. Pasa --cluster-id j-XXXX"
    exit 1
  elif [[ "$CNT" -gt 1 ]]; then
    echo "Hay varios clusters activos; especifica con --cluster-id:"
    aws emr list-clusters --active --region "$REGION" --query 'Clusters[].[Id,Name]' --output text
    exit 1
  fi
fi

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   Índice Invertido (MapReduce) en cluster vivo   ║"
echo "╚══════════════════════════════════════════════════╝"
echo "  Cluster : $CLUSTER_ID"
echo "  Bucket  : s3://$BUCKET"
echo ""

# ── Verificar scripts MR en S3 ────────────────────────────────────────────────
for f in mapper.py combiner.py reducer.py; do
  if ! aws s3 ls "s3://$BUCKET/scripts/$f" >/dev/null 2>&1; then
    echo "ERROR: falta s3://$BUCKET/scripts/$f"
    echo "Súbelo: aws s3 cp src/$f s3://$BUCKET/scripts/$f"
    exit 1
  fi
done

# ── Limpiar output previo ─────────────────────────────────────────────────────
echo "Limpiando s3://$BUCKET/output/ previo..."
aws s3 rm "s3://$BUCKET/output/" --recursive 2>/dev/null || true

# ── Lanzar el step ────────────────────────────────────────────────────────────
echo "Lanzando MapReduce..."
STEP_ID=$(aws emr add-steps --cluster-id "$CLUSTER_ID" --region "$REGION" \
  --steps "[{\"Type\":\"CUSTOM_JAR\",\"Name\":\"InvertedIndex-MR\",\"ActionOnFailure\":\"CONTINUE\",\"Jar\":\"command-runner.jar\",\"Args\":[\"hadoop-streaming\",\"-files\",\"s3://$BUCKET/scripts/mapper.py,s3://$BUCKET/scripts/combiner.py,s3://$BUCKET/scripts/reducer.py\",\"-mapper\",\"mapper.py\",\"-combiner\",\"combiner.py\",\"-reducer\",\"reducer.py\",\"-input\",\"s3://$BUCKET/input/\",\"-output\",\"s3://$BUCKET/output/\"]}]" \
  --query 'StepIds[0]' --output text)
echo "  Step ID : $STEP_ID"
echo ""

# ── Esperar con timer (sondea cada 15s) ──────────────────────────────────────
start=$SECONDS
while true; do
  state=$(aws emr describe-step --cluster-id "$CLUSTER_ID" --step-id "$STEP_ID" \
            --region "$REGION" --query 'Step.Status.State' --output text 2>/dev/null || echo "?")
  el=$((SECONDS - start))
  printf "\r  [%02d:%02d] step: %-12s" $((el / 60)) $((el % 60)) "$state"
  case "$state" in
    COMPLETED) printf "\n"; break ;;
    FAILED|CANCELLED|INTERRUPTED)
      printf "\n"
      echo "  Step $state. Ver logs:"
      echo "  aws s3 cp s3://$BUCKET/logs/$CLUSTER_ID/steps/$STEP_ID/stderr.gz - | gunzip -c"
      exit 1 ;;
  esac
  sleep 15
done

# ── Tiempo del job ────────────────────────────────────────────────────────────
# Preferimos el timeline del step (preciso, excluye la cola). Si por lo que sea
# 'date -d' no estuviera disponible, caemos al tiempo medido por el bucle.
elapsed_loop=$((SECONDS - start))
to_epoch() {
  local t="$1"
  # epoch (float) → parte entera
  if [[ "$t" =~ ^[0-9.]+$ ]]; then echo "${t%.*}"; return; fi
  # ISO8601 → quitar la fracción de segundos (.123000) para máxima compatibilidad
  t=$(echo "$t" | sed -E 's/\.[0-9]+//')
  date -d "$t" +%s
}
S=""; E=""
read S E < <(aws emr describe-step --cluster-id "$CLUSTER_ID" --step-id "$STEP_ID" \
  --region "$REGION" --query 'Step.Status.Timeline.[StartDateTime,EndDateTime]' --output text) || true
SE=$(to_epoch "$S" 2>/dev/null || echo "")
EE=$(to_epoch "$E" 2>/dev/null || echo "")
if [[ -n "$SE" && -n "$EE" ]]; then
  DUR=$((EE - SE))
else
  DUR="$elapsed_loop"   # fallback
fi

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   MapReduce COMPLETADO                           ║"
echo "╚══════════════════════════════════════════════════╝"
echo "  Tiempo del job : ${DUR} segundos"
echo "  Índice en      : s3://$BUCKET/output/"
echo ""
echo "  Ver una palabra en el índice:"
echo "    aws s3 cp s3://$BUCKET/output/ ./mr_output/ --recursive --exclude \"*_SUCCESS\""
echo "    grep -P '^adventure\\t' mr_output/part-*"
