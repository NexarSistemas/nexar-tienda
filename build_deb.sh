#!/bin/bash
set -e

VERSION=$(cat VERSION)
PACKAGE="nexar-tienda"
BUILD_DIR="build_deb/nexar-tienda_${VERSION}"
APP_BIN="dist/NexarTienda"

echo "Generando paquete .deb v${VERSION}..."

if [ ! -f "${APP_BIN}" ]; then
  echo "❌ No se encontró ${APP_BIN}."
  exit 1
fi

rm -rf build_deb

# Estructura
mkdir -p "${BUILD_DIR}/opt/nexar-tienda"
mkdir -p "${BUILD_DIR}/usr/share/applications"
mkdir -p "${BUILD_DIR}/usr/share/pixmaps"
mkdir -p "${BUILD_DIR}/usr/local/bin"
mkdir -p "${BUILD_DIR}/DEBIAN"

# Binario
cp "${APP_BIN}" "${BUILD_DIR}/opt/nexar-tienda/NexarTienda"
chmod +x "${BUILD_DIR}/opt/nexar-tienda/NexarTienda"

# Recursos
cp -r templates static VERSION CHANGELOG.md "${BUILD_DIR}/opt/nexar-tienda/"

# ICONO
cp "static/icons/nexar_tienda.PNG" "${BUILD_DIR}/usr/share/pixmaps/nexar_tienda.png"

# WRAPPER (para poder ejecutar "nexartienda")
cat > "${BUILD_DIR}/usr/local/bin/nexartienda" << EOF
#!/bin/bash
/opt/nexar-tienda/NexarTienda
EOF

chmod +x "${BUILD_DIR}/usr/local/bin/nexartienda"

# .DESKTOP (UNO SOLO y correcto)
cat > "${BUILD_DIR}/usr/share/applications/nexar-tienda.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Nexar Tienda
Comment=Sistema integral de gestión para tiendas
Exec=/opt/nexar-tienda/NexarTienda
Icon=nexar_tienda
Terminal=false
Categories=Office;
StartupNotify=true
EOF

# CONTROL
cat > "${BUILD_DIR}/DEBIAN/control" << EOF
Package: ${PACKAGE}
Version: ${VERSION}
Architecture: amd64
Maintainer: Nexar Sistemas
Depends: libgtk-3-0, libwebkit2gtk-4.1-0
Description: Sistema integral de gestión para tiendas.
EOF

# BUILD
dpkg-deb --build "${BUILD_DIR}"
mv build_deb/*.deb .

echo "✅ Paquete generado correctamente"