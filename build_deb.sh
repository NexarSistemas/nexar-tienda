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
  echo "  pyinstaller build/nexar_tienda.spec"
  exit 1
fi

rm -rf build_deb
mkdir -p "${BUILD_DIR}/opt/nexar-tienda"
mkdir -p "${BUILD_DIR}/usr/share/applications"
mkdir -p "${BUILD_DIR}/usr/share/pixmaps"
mkdir -p "${BUILD_DIR}/DEBIAN"

# Copiar binario nativo y recursos
cp "${APP_BIN}" "${BUILD_DIR}/opt/nexar-tienda/NexarTienda"
chmod +x "${BUILD_DIR}/opt/nexar-tienda/NexarTienda"
cp -r templates static VERSION CHANGELOG.md "${BUILD_DIR}/opt/nexar-tienda/"

# Icono y lanzador de escritorio
cp "static/icons/nexar_tienda.PNG" "${BUILD_DIR}/usr/share/pixmaps/nexar_tienda.png"
cat > "${BUILD_DIR}/usr/share/applications/nexar-tienda.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Nexar Tienda
Comment=Sistema integral de gestión para tiendas
Exec=/opt/nexar-tienda/NexarTienda
Icon=/usr/share/pixmaps/nexar_tienda.png
Terminal=false
Categories=Office;
StartupNotify=true
EOF

# Icono y lanzador de escritorio
cp "static/icons/nexar_tienda.PNG" "${BUILD_DIR}/usr/share/pixmaps/nexar_tienda.png"
cat > "${BUILD_DIR}/usr/share/applications/nexar-tienda.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Nexar Tienda
Comment=Sistema integral de gestión para tiendas
Exec=/usr/local/bin/nexartienda
Icon=/usr/share/pixmaps/nexar_tienda.png
Terminal=false
Categories=Office;
StartupNotify=true
EOF

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
