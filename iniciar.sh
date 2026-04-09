#!/bin/bash

echo "======================================================"
echo "  - Iniciando Nexar Tienda para Linux -"
echo "======================================================"

# 1. Verificar Python
if ! command -v python3 &> /dev/null
then
    echo "[ERROR] Python3 no esta instalado."
    echo "Instala Python 3.11 o superior."
    exit 1
fi

# 2. Crear entorno virtual si no existe
if [ ! -d "venv" ]; then
    echo "[INFO] Creando entorno virtual..."
    python3 -m venv venv
fi

# 3. Activar entorno virtual
echo "[INFO] Activando entorno virtual..."
source venv/bin/activate

# 4. Instalar dependencias
echo "[INFO] Instalando dependencias..."
python -m pip install --upgrade pip
pip install -r requirements.txt

# 5. Crear .env si no existe
if [ ! -f ".env" ]; then
    echo "[INFO] Creando archivo .env seguro..."
    python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" > .env
fi

# 6. Inicializar base de datos
echo "[INFO] Inicializando base de datos..."
python -c "import database; database.init_db()"

if [ $? -ne 0 ]; then
    echo "[ERROR] Fallo la inicializacion de la base de datos."
    exit 1
fi

# 7. Ejecutar aplicación
echo "[OK] Iniciando aplicacion..."
python app.py

if [ $? -ne 0 ]; then
    echo "[ERROR] La aplicacion se cerro con errores."
fi