#!/bin/bash
# ============================================================
# build_deb.sh — Genera el paquete .deb para Nexar Tienda
#
# Uso desde la raíz del proyecto:
#   bash build_deb.sh
#
# Requiere:
#   - dist/NexarTienda    (binario compilado por PyInstaller)
#   - dpkg-deb, fakeroot
# ============================================================

set -e

# ── Leer versión desde el archivo VERSION ───────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VERSION=$(cat "${SCRIPT_DIR}/VERSION")

PACKAGE="nexar-tienda"
ARCH="amd64"
MAINTAINER="Nexar Sistemas <nexarsistemas@outlook.com.ar>"
DESCRIPTION="Nexar Tienda — v${VERSION}"

BUILD_DIR="${SCRIPT_DIR}/build_deb"
PKG_DIR="${BUILD_DIR}/${PACKAGE}_${VERSION}"
INSTALL_DIR="${PKG_DIR}/opt/nexar-tienda"
DEBIAN_DIR="${PKG_DIR}/DEBIAN"
APP_BIN="${SCRIPT_DIR}/dist/NexarTienda"

echo "════════════════════════════════════════════════════"
echo "  Nexar Tienda — Builder .deb v${VERSION}"
echo "════════════════════════════════════════════════════"

# ── Verificar que el binario exista ─────────────────────────
if [ ! -f "${APP_BIN}" ]; then
  echo "❌ No se encontró ${APP_BIN}"
  echo "   Compilá primero con PyInstaller:"
  echo "   pyinstaller build/nexar_tienda_linux.spec --distpath dist --noconfirm"
  exit 1
fi

# ── Limpiar build anterior ───────────────────────────────────
rm -rf "${BUILD_DIR}"

# ── Crear estructura de directorios ─────────────────────────
mkdir -p "${INSTALL_DIR}"
mkdir -p "${DEBIAN_DIR}"
mkdir -p "${PKG_DIR}/usr/local/bin"
mkdir -p "${PKG_DIR}/usr/share/applications"
mkdir -p "${PKG_DIR}/usr/share/pixmaps"

echo "→ Copiando binario y recursos..."

# Binario compilado (OneFile — único ejecutable)
cp "${APP_BIN}" "${INSTALL_DIR}/NexarTienda"
chmod +x "${INSTALL_DIR}/NexarTienda"

# Recursos del proyecto
cp -r "${SCRIPT_DIR}/templates"    "${INSTALL_DIR}/"
cp -r "${SCRIPT_DIR}/static"       "${INSTALL_DIR}/"
cp    "${SCRIPT_DIR}/VERSION"      "${INSTALL_DIR}/"
cp    "${SCRIPT_DIR}/CHANGELOG.md" "${INSTALL_DIR}/"

# Configuración pública de licencias generada por CI.
# También se incluye dentro del binario PyInstaller, pero dejarla al lado del
# ejecutable hace el .deb más robusto ante cambios de modo onefile/onedir.
if [ -f "${SCRIPT_DIR}/build/license_runtime_config.json" ]; then
  cp "${SCRIPT_DIR}/build/license_runtime_config.json" "${INSTALL_DIR}/"
else
  echo "❌ No se encontró build/license_runtime_config.json"
  echo "   El paquete .deb necesita SUPABASE_URL y SUPABASE_ANON_KEY para validar licencias online."
  exit 1
fi

# README y LICENSE opcionales
[ -f "${SCRIPT_DIR}/README.md" ] && cp "${SCRIPT_DIR}/README.md" "${INSTALL_DIR}/"
[ -f "${SCRIPT_DIR}/LICENSE"   ] && cp "${SCRIPT_DIR}/LICENSE"   "${INSTALL_DIR}/"
[ -f "${SCRIPT_DIR}/LICENSE.txt" ] && cp "${SCRIPT_DIR}/LICENSE.txt" "${INSTALL_DIR}/"

# Limpieza de archivos innecesarios
find "${INSTALL_DIR}" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "${INSTALL_DIR}" -name "*.pyc"       -delete 2>/dev/null || true
find "${INSTALL_DIR}" -name "*.db"        -delete 2>/dev/null || true

echo "→ Configurando ícono y entrada de menú..."

# Ícono (soporta .PNG y .png — Linux es case-sensitive)
if [ -f "${SCRIPT_DIR}/static/icons/nexar_tienda.PNG" ]; then
  cp "${SCRIPT_DIR}/static/icons/nexar_tienda.PNG" \
     "${PKG_DIR}/usr/share/pixmaps/nexar_tienda.png"
elif [ -f "${SCRIPT_DIR}/static/icons/nexar_tienda.png" ]; then
  cp "${SCRIPT_DIR}/static/icons/nexar_tienda.png" \
     "${PKG_DIR}/usr/share/pixmaps/nexar_tienda.png"
else
  echo "⚠️  No se encontró ícono en static/icons/ — el paquete se generará sin ícono"
fi

# Archivo .desktop (entrada de menú)
if [ -f "${SCRIPT_DIR}/build/nexar_tienda.desktop" ]; then
  cp "${SCRIPT_DIR}/build/nexar_tienda.desktop" \
     "${PKG_DIR}/usr/share/applications/nexar-tienda.desktop"
else
  # Generar uno básico si no existe
  cat > "${PKG_DIR}/usr/share/applications/nexar-tienda.desktop" << DESKTOP_EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Nexar Tienda
Comment=Sistema integral de gestión para tiendas
Exec=/usr/local/bin/nexartienda
Path=/opt/nexar-tienda
Icon=nexar_tienda
Terminal=false
Categories=Office;
StartupNotify=true
StartupWMClass=NexarTienda
DESKTOP_EOF
fi

echo "→ Creando script de lanzamiento..."

# Wrapper CLI: resuelve problemas de GTK/GSettings en binarios PyInstaller
cat > "${PKG_DIR}/usr/local/bin/nexartienda" << 'WRAPPER_EOF'
#!/bin/bash
# Lanzador de Nexar Tienda
# Limpia variables de entorno que pueden causar conflictos con GTK
unset GSETTINGS_SCHEMA_DIR

if [ -n "${XDG_DATA_DIRS:-}" ]; then
  export XDG_DATA_DIRS="/usr/local/share:/usr/share:${XDG_DATA_DIRS}"
else
  export XDG_DATA_DIRS="/usr/local/share:/usr/share"
fi

cd /opt/nexar-tienda
exec ./NexarTienda "$@"
WRAPPER_EOF

chmod +x "${PKG_DIR}/usr/local/bin/nexartienda"

echo "→ Calculando tamaño instalado..."
INSTALLED_SIZE=$(du -sk "${INSTALL_DIR}" | cut -f1)

echo "→ Generando metadata del paquete..."

cat > "${DEBIAN_DIR}/control" << CONTROL_EOF
Package: ${PACKAGE}
Version: ${VERSION}
Architecture: ${ARCH}
Maintainer: ${MAINTAINER}
Installed-Size: ${INSTALLED_SIZE}
Depends: libegl1, libgl1, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-render-util0, libxcb-shape0, libxcb-xinerama0, libxkbcommon-x11-0
Recommends: fonts-liberation
Section: misc
Priority: optional
Homepage: https://wa.me/5492645858874
Description: ${DESCRIPTION}
 Sistema integral de gestión para tiendas y comercios.
 Incluye gestión de ventas, inventario, caja y reportes.
CONTROL_EOF

# ── Scripts de instalación ───────────────────────────────────

cat > "${DEBIAN_DIR}/postinst" << 'POSTINST_EOF'
#!/bin/bash
set -e

chmod +x /usr/local/bin/nexartienda
chmod +x /opt/nexar-tienda/NexarTienda
chmod -R a+rX /opt/nexar-tienda

# Actualizar caché de íconos y menús
update-desktop-database /usr/share/applications 2>/dev/null || true
gtk-update-icon-cache /usr/share/pixmaps 2>/dev/null || true

echo ""
echo "════════════════════════════════════════════"
echo " Nexar Tienda instalado correctamente ✅"
echo "════════════════════════════════════════════"
echo " Ejecutar: nexartienda"
echo "  O buscar 'Nexar Tienda' en el menú de apps"
echo "════════════════════════════════════════════"

exit 0
POSTINST_EOF
chmod +x "${DEBIAN_DIR}/postinst"

cat > "${DEBIAN_DIR}/prerm" << 'PRERM_EOF'
#!/bin/bash
set -e
echo "Desinstalando Nexar Tienda..."
exit 0
PRERM_EOF
chmod +x "${DEBIAN_DIR}/prerm"

cat > "${DEBIAN_DIR}/postrm" << 'POSTRM_EOF'
#!/bin/bash
set -e
update-desktop-database /usr/share/applications 2>/dev/null || true
exit 0
POSTRM_EOF
chmod +x "${DEBIAN_DIR}/postrm"

echo "→ Construyendo paquete .deb..."

DEB_FILE="${BUILD_DIR}/${PACKAGE}_${VERSION}_${ARCH}.deb"
dpkg-deb --build --root-owner-group "${PKG_DIR}" "${DEB_FILE}"

# Mover al directorio raíz del proyecto
mv "${DEB_FILE}" "${SCRIPT_DIR}/"
FINAL_DEB="${SCRIPT_DIR}/${PACKAGE}_${VERSION}_${ARCH}.deb"

echo ""
echo "════════════════════════════════════════════"
echo " ✅ Paquete generado:"
echo "    $(basename "${FINAL_DEB}")"
echo "    $(du -sh "${FINAL_DEB}" | cut -f1)"
echo ""
echo " Instalar recomendado:"
echo "    sudo apt install ./$(basename "${FINAL_DEB}")"
echo ""
echo " Nota: sudo dpkg -i ./$(basename "${FINAL_DEB}") no descarga dependencias."
echo "       Si usaste dpkg y queda sin configurar, ejecutar:"
echo "    sudo apt --fix-broken install"
echo "════════════════════════════════════════════"
