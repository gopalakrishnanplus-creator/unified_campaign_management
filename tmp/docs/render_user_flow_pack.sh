#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

OUTPUT_DIR="output/doc/user-flow-decks"
QA_DIR="$OUTPUT_DIR/qa-pdf"

mkdir -p "$QA_DIR"

if ! command -v soffice >/dev/null 2>&1; then
  echo "soffice is required for PDF QA rendering but was not found." >&2
  exit 1
fi

find "$QA_DIR" -type f -name '*.pdf' -delete

soffice --headless --convert-to pdf --outdir "$QA_DIR" "$OUTPUT_DIR"/*.pptx >/dev/null

echo "Rendered PDF QA previews to $QA_DIR"
