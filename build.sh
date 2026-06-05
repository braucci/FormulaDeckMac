#!/usr/bin/env bash
# =============================================================================
# build.sh — Build standalone di FormulaDeck.app tramite py2app.
#
# Esegue, in ordine:
#   1. crea un virtualenv pulito (.venv)
#   2. installa le dipendenze
#   3. scarica e impacchetta KaTeX dentro preview/vendor/katex (renderer offline)
#   4. elimina build/ e dist/ precedenti
#   5. esegue py2app in modalità standalone (NIENTE flag -A / alias)
#
# Uso:   ./build.sh
# =============================================================================
set -euo pipefail

KATEX_VERSION="0.17.0"
VENDOR_DIR="preview/vendor/katex"

echo "==> [1/5] Creazione virtualenv pulito (.venv)"
rm -rf .venv
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null

echo "==> [2/5] Installazione dipendenze"
pip install -r requirements.txt

echo "==> [3/5] Impacchettamento KaTeX ${KATEX_VERSION} (renderer offline)"
if [ -f "${VENDOR_DIR}/katex.min.js" ]; then
  echo "    KaTeX già presente in ${VENDOR_DIR}, salto il download."
else
  mkdir -p "${VENDOR_DIR}"
  TMP="$(mktemp -d)"
  # Sorgente stabile: registry npm (nessun redirect cross-origin).
  curl -sL "https://registry.npmjs.org/katex/-/katex-${KATEX_VERSION}.tgz" \
       -o "${TMP}/katex.tgz"
  tar -xzf "${TMP}/katex.tgz" -C "${TMP}"
  cp "${TMP}/package/dist/katex.min.css" "${VENDOR_DIR}/"
  cp "${TMP}/package/dist/katex.min.js"  "${VENDOR_DIR}/"
  mkdir -p "${VENDOR_DIR}/fonts"
  cp "${TMP}/package/dist/fonts/"*.woff2 "${VENDOR_DIR}/fonts/"
  rm -rf "${TMP}"
  echo "    KaTeX impacchettato in ${VENDOR_DIR}"
fi

echo "==> [4/5] Pulizia build/ e dist/ precedenti"
rm -rf build dist

echo "==> [5/5] Build standalone con py2app"
python setup.py py2app

echo
echo "============================================================"
echo " Build completata."
echo " Bundle prodotto:  dist/FormulaDeck.app"
echo
echo " Per provarlo subito:"
echo "     open dist/FormulaDeck.app"
echo
echo " Per diagnosticare un eventuale crash all'avvio (traceback):"
echo "     ./dist/FormulaDeck.app/Contents/MacOS/FormulaDeck"
echo
echo " Per installarlo: trascina FormulaDeck.app in /Applications."
echo "============================================================"
