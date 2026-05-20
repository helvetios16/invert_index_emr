#!/bin/bash
# =============================================================================
# clean_local.sh — Elimina todo lo generado por split_titles.py y test_local.py
# Deja el proyecto como justo después de git clone.
# =============================================================================
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Limpiando archivos locales generados..."
echo ""

if [ -d "$ROOT_DIR/data" ]; then
  DOC_COUNT=$(find "$ROOT_DIR/data/documents" -name "*.txt" 2>/dev/null | wc -l | tr -d ' ')
  echo "  Eliminando data/ ($DOC_COUNT archivos doc_*.txt + índice + mapeo)..."
  rm -rf "$ROOT_DIR/data"
  echo "  ✓ data/ eliminado"
else
  echo "  data/ no existe, nada que limpiar."
fi

echo ""
echo "El proyecto quedó como después de 'git clone'."
echo ""
echo "Para volver a generar:"
echo "  python3 scripts/split_titles.py   ← dividir títulos en docs"
echo "  python3 scripts/test_local.py     ← construir el índice"
