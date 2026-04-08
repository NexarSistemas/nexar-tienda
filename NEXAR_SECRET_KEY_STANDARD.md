Archivo: NEXAR_SECRET_KEY_STANDARD.md 

---

# 🔐 NEXAR_SECRET_KEY_STANDARD

## 🎯 OBJETIVO

Unificar el manejo de SECRET_KEY en todos los sistemas Nexar para garantizar seguridad, consistencia y compatibilidad con herramientas de desarrollo asistido por IA.

Aplica a:

- nexar-finanzas
- nexar-almacen
- nexar-tienda
- futuros proyectos

---

## 🚨 REGLA PRINCIPAL

La SECRET_KEY debe existir SIEMPRE como variable de entorno.

NO se permite:

- hardcodear la clave
- generar claves automáticamente
- usar valores por defecto

---

## ✅ IMPLEMENTACIÓN OBLIGATORIA

```python
import os

SECRET_KEY = os.getenv("SECRET_KEY", "").strip()

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY no definida. Configurar variable de entorno.")

app.config["SECRET_KEY"] = SECRET_KEY
```

---

## 📁 CONFIGURACIÓN POR ENTORNO

### 🖥️ Desarrollo local

Crear archivo `.env` (NO subir a GitHub):

```
SECRET_KEY=clave_local_segura
```

Cargar variables:

```python
from dotenv import load_dotenv
load_dotenv()
```

---

### ☁️ GitHub

Configurar en:

Settings → Secrets and variables → Actions

Crear:

```
SECRET_KEY = tu_clave_segura
```

---

### ⚙️ GitHub Actions

```yaml
env:
  SECRET_KEY: ${{ secrets.SECRET_KEY }}
```

---

### 🖥️ Producción

Linux:

```
export SECRET_KEY="clave_produccion"
```

---

## 🚫 PROHIBIDO

- Usar `secrets.token_hex()`
- Generar claves automáticamente
- Hardcodear valores
- Mezclar múltiples métodos

---

## 🧠 INSTRUCCIONES PARA IA

Cuando se use una IA (ChatGPT, Gemini, Claude, etc.), utilizar este formato:

```
Aplica el estándar NEXAR_SECRET_KEY_STANDARD.md a este proyecto.

Reglas:
- NO reescribir todo el archivo
- SOLO modificar la configuración de SECRET_KEY
- NO cambiar lógica existente
- Mantener estructura actual
```

---

## 🔧 TAREA ESPERADA DE LA IA

La IA debe:

1. Detectar cómo se maneja actualmente la SECRET_KEY
2. Eliminar implementaciones inseguras
3. Aplicar este estándar
4. No modificar otras partes del sistema
5. NO renombrar variables existentes
6. NO cambiar imports innecesariamente

---

## 🧪 CHECKLIST

- [ ] No hay SECRET_KEY hardcodeada
- [ ] Se usa os.getenv()
- [ ] Existe validación obligatoria
- [ ] Funciona en entorno local (.env)
- [ ] Funciona en producción
- [ ] No rompe sesiones

---

## 🧩 FILOSOFÍA

Este estándar garantiza:

- Seguridad real
- Reutilización entre sistemas
- Compatibilidad con IA
- Consistencia entre proyectos Nexar

---

## ⚠️ IMPORTANTE

Si SECRET_KEY no está configurada, la aplicación NO debe iniciar.