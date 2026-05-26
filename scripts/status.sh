#!/bin/bash
# =============================================================================
# status.sh — Muestra el estado de todos los recursos del proyecto en AWS
# Uso: bash scripts/status.sh [bucket] [region]
# =============================================================================

BUCKET="${1:-mi-indice-gutenberg}"
REGION="${2:-us-east-1}"

SEP="──────────────────────────────────────────────────"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   Estado del proyecto — Índice Invertido EMR     ║"
echo "╚══════════════════════════════════════════════════╝"
echo "  Bucket : s3://$BUCKET"
echo "  Región : $REGION"
echo ""

# ── S3: Resumen general ───────────────────────────────────────────────────────
echo "[ S3 ] Resumen del bucket"
echo "$SEP"

if ! aws s3 ls "s3://$BUCKET" >/dev/null 2>&1; then
  echo "  ✗ Bucket no existe o sin acceso."
else
  # Carpetas y tamaños
  for FOLDER in input scripts output logs; do
    INFO=$(aws s3 ls "s3://$BUCKET/$FOLDER/" --recursive --human-readable --summarize 2>/dev/null | grep "Total")
    COUNT=$(aws s3 ls "s3://$BUCKET/$FOLDER/" --recursive 2>/dev/null | wc -l | tr -d ' ')
    if [ "$COUNT" -gt "0" ]; then
      SIZE=$(echo "$INFO" | awk '{print $3, $4}')
      echo "  s3://$BUCKET/$FOLDER/  →  $COUNT archivos  ($SIZE)"
    else
      echo "  s3://$BUCKET/$FOLDER/  →  vacío o no existe"
    fi
  done

  # doc_map.txt
  if aws s3 ls "s3://$BUCKET/doc_map.txt" >/dev/null 2>&1; then
    echo "  s3://$BUCKET/doc_map.txt  →  existe ✓"
  else
    echo "  s3://$BUCKET/doc_map.txt  →  no existe"
  fi
fi

# ── S3: Output (índice generado) ──────────────────────────────────────────────
echo ""
echo "[ S3 ] Output del job MapReduce"
echo "$SEP"

OUTPUT_COUNT=$(aws s3 ls "s3://$BUCKET/output/" --recursive 2>/dev/null | grep -v "_SUCCESS" | wc -l | tr -d ' ')
if [ "$OUTPUT_COUNT" -gt "0" ]; then
  echo "  Estado : DISPONIBLE ✓"
  aws s3 ls "s3://$BUCKET/output/" --recursive --human-readable 2>/dev/null | awk '{print "  " $0}'
  echo ""
  echo "  Muestra del índice (5 líneas):"
  PART_KEY=$(aws s3 ls "s3://$BUCKET/output/" --recursive 2>/dev/null | grep "part-" | head -1 | awk '{print $4}')
  if [ -n "$PART_KEY" ]; then
    aws s3 cp "s3://$BUCKET/$PART_KEY" - 2>/dev/null | head -5 | while IFS=$'\t' read -r word docs; do
      echo "    $word  →  ${docs:0:80}..."
    done
  fi
else
  echo "  Estado : SIN OUTPUT (job no completado o no iniciado)"
fi

# ── EMR: Clústeres activos ────────────────────────────────────────────────────
echo ""
echo "[ EMR ] Clústeres activos"
echo "$SEP"

CLUSTERS=$(aws emr list-clusters --region "$REGION" --active \
  --query 'Clusters[*].[Id,Name,Status.State,Status.Timeline.CreationDateTime]' \
  --output text 2>/dev/null)

if [ -z "$CLUSTERS" ]; then
  echo "  No hay clústeres activos."
else
  echo "  ID                    NOMBRE                        ESTADO"
  echo "$CLUSTERS" | while read -r ID NAME STATE CREATED; do
    printf "  %-22s %-30s %s\n" "$ID" "$NAME" "$STATE"
  done

  # Steps del primer clúster
  FIRST_CLUSTER=$(echo "$CLUSTERS" | head -1 | awk '{print $1}')
  echo ""
  echo "  Steps recientes del clúster $FIRST_CLUSTER:"
  aws emr list-steps --cluster-id "$FIRST_CLUSTER" --region "$REGION" \
    --query 'Steps[0:3].[Id,Name,Status.State]' \
    --output text 2>/dev/null | while read -r SID SNAME SSTATE; do
    printf "    %-26s %-20s %s\n" "$SID" "$SNAME" "$SSTATE"
  done
fi

# ── EMR: Historial reciente ───────────────────────────────────────────────────
echo ""
echo "[ EMR ] Último clúster terminado"
echo "$SEP"

LAST=$(aws emr list-clusters --region "$REGION" --terminated \
  --query 'Clusters[0].[Id,Name,Status.State,Status.Timeline.EndDateTime]' \
  --output text 2>/dev/null)

if [ -n "$LAST" ]; then
  ID=$(echo "$LAST" | awk '{print $1}')
  NAME=$(echo "$LAST" | awk '{print $2}')
  STATE=$(echo "$LAST" | awk '{print $3}')
  echo "  $ID  ($NAME)  →  $STATE"
else
  echo "  Sin historial."
fi

# ── Comandos útiles ───────────────────────────────────────────────────────────
echo ""
echo "[ Comandos útiles ]"
echo "$SEP"
echo "  Buscar en el índice (si output existe):"
echo "    python3 search/search.py --s3 $BUCKET output/ \"twenty years after\""
echo ""
echo "  Terminar clúster activo:"
if [ -n "$FIRST_CLUSTER" ]; then
  echo "    aws emr terminate-clusters --cluster-ids $FIRST_CLUSTER"
else
  echo "    aws emr terminate-clusters --cluster-ids <cluster-id>"
fi
echo ""
echo "  Limpiar todo en AWS:"
echo "    bash scripts/cleanup.sh $BUCKET $REGION"
echo ""
