#!/bin/bash
# ============================================================
# build_deb.sh — Genera el paquete .deb para Nexar Tienda
# ============================================================

set -e
VERSION=$(cat VERSION)
PACKAGE="nexar-tienda"
BUILD_DIR="build_deb/nexar-tienda_${VERSION}"
APP_BIN="dist/NexarTienda"

echo "Generando paquete .deb v${VERSION}..."

if [ ! -f "${APP_BIN}" ]; then
  echo "❌ No se encontró ${APP_BIN}."
  echo "Compilá primero la app nativa con PyInstaller:"
  echo "  pyinstaller build/nexar_tienda_linux.spec"
  exit 1
fi

rm -rf build_deb
mkdir -p "${BUILD_DIR}/opt/nexar-tienda"
mkdir -p "${BUILD_DIR}/usr/local/bin"
mkdir -p "${BUILD_DIR}/usr/share/applications"
mkdir -p "${BUILD_DIR}/usr/share/pixmaps"
mkdir -p "${BUILD_DIR}/DEBIAN"

# Copiar binario nativo y recursos
cp "${APP_BIN}" "${BUILD_DIR}/opt/nexar-tienda/NexarTienda"
chmod +x "${BUILD_DIR}/opt/nexar-tienda/NexarTienda"
cp -r templates static VERSION CHANGELOG.md "${BUILD_DIR}/opt/nexar-tienda/"

# Wrapper CLI
cat > "${BUILD_DIR}/usr/local/bin/nexartienda" << EOF
#!/bin/bash
cd /opt/nexar-tienda
unset GSETTINGS_SCHEMA_DIR
if [ -n "\${XDG_DATA_DIRS:-}" ]; then
  export XDG_DATA_DIRS="/usr/local/share:/usr/share:\${XDG_DATA_DIRS}"
else
  export XDG_DATA_DIRS="/usr/local/share:/usr/share"
fi
exec ./NexarTienda
EOF
chmod +x "${BUILD_DIR}/usr/local/bin/nexartienda"

# Icono y lanzador de escritorio
cp "static/icons/nexar_tienda.PNG" "${BUILD_DIR}/usr/share/pixmaps/nexar_tienda.png"
cp "build/nexar_tienda.desktop" "${BUILD_DIR}/usr/share/applications/nexar-tienda.desktop"

# Control file
cat > "${BUILD_DIR}/DEBIAN/control" << EOF
Package: ${PACKAGE}
Version: ${VERSION}
Architecture: all
Maintainer: Nexar Sistemas
Depends: libgtk-3-0, libwebkit2gtk-4.1-0
Description: Sistema integral de gestión para tiendas.
EOF

dpkg-deb --build "${BUILD_DIR}"
mv build_deb/*.deb .
echo "¡Hecho! Paquete generado en el directorio raíz."
