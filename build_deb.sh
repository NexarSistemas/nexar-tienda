#!/bin/bash
# ============================================================
# build_deb.sh — Genera el paquete .deb para Nexar Tienda
# ============================================================

set -e
VERSION=$(cat VERSION)
PACKAGE="nexar-tienda"
BUILD_DIR="build_deb/nexar-tienda_${VERSION}"

echo "Generando paquete .deb v${VERSION}..."

rm -rf build_deb
mkdir -p "${BUILD_DIR}/opt/nexar-tienda"
mkdir -p "${BUILD_DIR}/usr/local/bin"
mkdir -p "${BUILD_DIR}/DEBIAN"

# Copiar archivos core
cp -r templates static app.py database.py iniciar.py VERSION CHANGELOG.md requirements.txt "${BUILD_DIR}/opt/nexar-tienda/"

# Crear lanzador
cat > "${BUILD_DIR}/usr/local/bin/nexartienda" << EOF
#!/bin/bash
cd /opt/nexar-tienda
export NEXAR_SKIP_VENV=1
python3 iniciar.py
EOF
chmod +x "${BUILD_DIR}/usr/local/bin/nexartienda"

# Control file
cat > "${BUILD_DIR}/DEBIAN/control" << EOF
Package: ${PACKAGE}
Version: ${VERSION}
Architecture: all
Maintainer: Nexar Sistemas
Depends: python3, python3-pip
Description: Sistema integral de gestión para tiendas.
EOF

# Post-inst para dependencias pip
cat > "${BUILD_DIR}/DEBIAN/postinst" << EOF
#!/bin/bash
set -e

if [ -f /opt/nexar-tienda/requirements.txt ]; then
  python3 -m pip install --break-system-packages -r /opt/nexar-tienda/requirements.txt
else
  python3 -m pip install Flask python-dotenv openpyxl reportlab pywebview --break-system-packages
fi
EOF
chmod +x "${BUILD_DIR}/DEBIAN/postinst"

dpkg-deb --build "${BUILD_DIR}"
mv build_deb/*.deb .
echo "¡Hecho! Paquete generado en el directorio raíz."
