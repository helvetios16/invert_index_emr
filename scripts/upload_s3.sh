#!/bin/bash
# =============================================================================
# upload_s3.sh — Sube el corpus y scripts a S3 después de build_corpus.py
#
# Uso:
#   bash scripts/upload_s3.sh <bucket> [región]
#
# Ejemplo:
#   bash scripts/upload_s3.sh mi-indice-gutenberg us-east-1
# =============================================================================
set -euo pipefail

BUCKET="${1:-mi-indice-gutenberg}"
REGION="${2:-us-east-1}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   Subiendo corpus y scripts a S3                 ║"
echo "╚══════════════════════════════════════════════════╝"
echo "  Bucket : s3://$BUCKET"
echo ""

# Verificar que el corpus existe
if [ ! -f "$ROOT_DIR/data/corpus.txt" ]; then
  echo "ERROR: no existe data/corpus.txt"
  echo "Ejecuta primero: python3 scripts/build_corpus.py"
  exit 1
fi

SIZE=$(du -sh "$ROOT_DIR/data/corpus.txt" | cut -f1)
DOCS=$(wc -l < "$ROOT_DIR/data/corpus.txt" | tr -d ' ')
echo "  corpus.txt : $DOCS documentos  ($SIZE)"
echo ""

# Limpiar input anterior
echo "[ 1/3 ] Limpiando input anterior en S3..."
aws s3 rm "s3://$BUCKET/input/" --recursive 2>/dev/null || true
echo "        ✓ Listo"

# Subir corpus y mapeo
echo ""
echo "[ 2/3 ] Subiendo corpus y mapeo..."
aws s3 cp "$ROOT_DIR/data/corpus.txt"  "s3://$BUCKET/input/corpus.txt"
echo "        ✓ corpus.txt  →  s3://$BUCKET/input/"
aws s3 cp "$ROOT_DIR/data/doc_map.txt" "s3://$BUCKET/doc_map.txt"
echo "        ✓ doc_map.txt →  s3://$BUCKET/"

# Subir scripts MapReduce
echo ""
echo "[ 3/3 ] Subiendo scripts MapReduce..."
aws s3 cp "$ROOT_DIR/src/mapper.py"   "s3://$BUCKET/scripts/mapper.py"
aws s3 cp "$ROOT_DIR/src/combiner.py" "s3://$BUCKET/scripts/combiner.py"
aws s3 cp "$ROOT_DIR/src/reducer.py"  "s3://$BUCKET/scripts/reducer.py"
echo "        ✓ mapper / combiner / reducer →  s3://$BUCKET/scripts/"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   Subida completada                              ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "  Siguiente paso:"
echo "    bash manual_step.txt"
