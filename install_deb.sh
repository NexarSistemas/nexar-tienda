#!/usr/bin/env bash
# Instala el ultimo paquete .deb de Nexar Tienda resolviendo dependencias.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ $# -gt 0 ]]; then
  DEB_PATH="$1"
else
  DEB_PATH="$(find "${SCRIPT_DIR}" -maxdepth 1 -name 'nexar-tienda_*_amd64.deb' -type f -printf '%T@ %p\n' | sort -nr | awk 'NR == 1 {print $2}')"
fi

if [[ -z "${DEB_PATH:-}" || ! -f "${DEB_PATH}" ]]; then
  echo "No se encontro un paquete nexar-tienda_*_amd64.deb."
  echo "Uso: ./install_deb.sh ./nexar-tienda_VERSION_amd64.deb"
  exit 1
fi

echo "Instalando $(basename "${DEB_PATH}") con apt para resolver dependencias..."
TMP_DEB="/tmp/$(basename "${DEB_PATH}")"
cp "${DEB_PATH}" "${TMP_DEB}"
chmod 0644 "${TMP_DEB}"
sudo apt install -y "${TMP_DEB}"
rm -f "${TMP_DEB}"

echo ""
echo "Nexar Tienda instalado. Ejecutar con:"
echo "  nexartienda"
