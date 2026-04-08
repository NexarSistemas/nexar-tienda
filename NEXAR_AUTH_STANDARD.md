Archivo: NEXAR_AUTH_STANDARD.md

---

# 🔐 NEXAR AUTH STANDARD

## 🎯 OBJETIVO

Unificar el sistema de autenticación en todos los productos Nexar.

Aplica a:
- login de usuarios
- registro de usuarios
- validación de contraseñas
- manejo de sesiones

---

## 🚨 REGLAS PRINCIPALES

- Las contraseñas NUNCA se guardan en texto plano
- SIEMPRE deben estar hasheadas
- Deben cumplir requisitos mínimos de seguridad

---

## 🔑 VALIDACIÓN DE CONTRASEÑA

### Requisitos obligatorios:

- Mínimo 6 caracteres
- Al menos 1 mayúscula
- Al menos 1 minúscula
- Al menos 1 número
- Al menos 1 carácter especial

La función validar_password debe ubicarse en:

utils/security.py

para reutilización en todo el sistema.

---

## ✅ IMPLEMENTACIÓN DE VALIDACIÓN

```python
import re

def validar_password(password):
    if len(password) < 6:
        return False, "Debe tener al menos 6 caracteres"

    if not re.search(r"[A-Z]", password):
        return False, "Debe tener al menos una mayúscula"

    if not re.search(r"[a-z]", password):
        return False, "Debe tener al menos una minúscula"

    if not re.search(r"[0-9]", password):
        return False, "Debe tener al menos un número"

    if not re.search(r"[^A-Za-z0-9]", password):
        return False, "Debe tener un carácter especial"

    return True, "OK"
```

---

## 🔐 HASH DE CONTRASEÑA

Usar Werkzeug:

```python
from werkzeug.security import generate_password_hash, check_password_hash

# Crear hash
password_hash = generate_password_hash(password)

# Verificar
check_password_hash(password_hash, password_ingresada)
```

Se recomienda usar los parámetros por defecto de Werkzeug.

---

## ⚠️ IMPORTANTE

Nunca devolver la contraseña en respuestas HTTP, logs o debugging.

---

## 🚫 PROHIBIDO

* Guardar contraseñas en texto plano
* Comparar contraseñas directamente
* Usar hashes caseros

---

## 🧠 INSTRUCCIONES PARA IA

```
Aplica el estándar NEXAR_AUTH_STANDARD.md a este proyecto.

Reglas:
- NO reescribir todo el sistema
- SOLO mejorar autenticación
- NO romper lógica existente
- Mantener estructura actual
- NO cambiar el sistema de hashing
- NO reemplazar Werkzeug por otras librerías
```

---

## 🔧 TAREA ESPERADA DE LA IA

1. Detectar manejo de contraseñas
2. Aplicar validación
3. Aplicar hashing
4. No modificar otras partes

---

## 🧪 CHECKLIST

- [ ] Contraseñas hasheadas
- [ ] Validación implementada
- [ ] Login funciona correctamente
- [ ] No hay texto plano
- [ ] No se exponen contraseñas en logs

---

## 🧩 FILOSOFÍA

Este estándar garantiza:

- Seguridad de usuarios
- Consistencia entre sistemas
- Compatibilidad con IA
- Buenas prácticas profesionales

---

## 🔐 SALT Y SEGURIDAD

Werkzeug ya incluye salt automáticamente en los hashes.

NO es necesario implementarlo manualmente.  
NO modificar este comportamiento.