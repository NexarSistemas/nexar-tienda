#!/bin/bash
# Script de inicio y configuración para Nexar Tienda (Linux/macOS)

echo "======================================================"
echo "  🚀 Iniciando Nexar Tienda para Linux"
echo "======================================================"

# 1. Verificar si Python está instalado
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python3 no está instalado."
    exit 1
fi

# 2. Configurar Entorno Virtual
if [ ! -d "venv" ]; then
    echo "📦 Creando entorno virtual (venv)..."
    python3 -m venv venv
fi

# 3. Activar entorno y verificar dependencias
echo "📥 Activando entorno virtual..."
source venv/bin/activate

echo "🔍 Verificando y actualizando dependencias..."
pip install --upgrade pip
pip install -r requirements.txt

# 4. Verificar estándar de seguridad (NEXAR_SECRET_KEY_STANDARD)
if [ ! -f .env ]; then
    echo "⚠️ Advertencia: No se encontró el archivo .env"
    echo "Creando un .env básico..."
    echo "SECRET_KEY=clave_generada_linux_$(date +%s | sha256sum | head -c 32)" > .env
    echo "Por favor, configura una SECRET_KEY segura en el archivo .env más tarde."
fi

# 5. Inicializar la base de datos
echo "🗄️ Verificando base de datos..."
python3 -c "import database; database.init_db()"

echo "✅ Todo listo. Iniciando Nexar Tienda..."
echo ""

# 6. Ejecutar Aplicación
python3 app.py