#!/bin/bash
# Script de configuración automática para Nexar Tienda

echo "🚀 Iniciando configuración de Nexar Tienda..."

# 1. Crear entorno virtual si no existe
if [ ! -d "venv" ]; then
    echo "📦 Creando entorno virtual (venv)..."
    python3 -m venv venv
fi

# 2. Activar el entorno e instalar dependencias
echo "📥 Instalando dependencias desde requirements.txt..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 3. Inicializar la base de datos
echo "🗄️ Inicializando base de datos..."
python3 -c "import database; database.init_db()"

echo "✅ Configuración finalizada con éxito."
echo "💡 Para comenzar, ejecuta: source venv/bin/activate && python app.py"