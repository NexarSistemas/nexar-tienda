# Security Policy

## 📌 Versiones soportadas

Este proyecto se encuentra en desarrollo activo.

| Versión | Soporte |
|--------|--------|
| 1.20.x - 1.21.x | ✅ Soporte activo |
| < 1.20.0        | ❌ No soportado |

---

## 🚨 Reporte de vulnerabilidades

Si encontrás una vulnerabilidad de seguridad, por favor **NO abras un issue público**.

En su lugar, podés reportarlo por:

- 📧 Email: nexarsistemas@outlook.com.ar  
- 📱 WhatsApp: +54 9 264 585-8874  

### 📋 Información recomendada

Para facilitar el análisis, incluir:

- Descripción clara del problema  
- Pasos para reproducirlo  
- Impacto potencial (ej: acceso a datos, bypass de licencia, etc.)  
- Capturas o evidencia técnica (si aplica)  

---

## ⏱️ Tiempos de respuesta

- Confirmación inicial: dentro de 48 horas  
- Evaluación técnica: dentro de 3 a 5 días  
- Resolución: según criticidad del problema  

---

## 🔒 Alcance de seguridad

Este proyecto es un sistema de gestión comercial que incluye:

- Punto de Venta (POS)
- Gestión de inventario
- Finanzas y gastos
- Clientes y cuentas corrientes
- Sistema de autenticación y roles (RBAC)
- Sistema de licenciamiento offline (RSA)

---

## 🔍 Áreas críticas

Se consideran vulnerabilidades de alta prioridad aquellas que afecten:

### 🔐 Autenticación y acceso
- Login, registro y recuperación de cuenta  
- Control de roles (Administrador, Encargado, Vendedor)  
- Manejo de sesiones  

### 🔑 Datos sensibles
- `SECRET_KEY`
- Variables de entorno (`.env`)
- Credenciales de usuario  

### 🧾 Sistema de licencias
- Generación y validación de tokens RSA  
- Bypass de validación de licencia  
- Manipulación de Hardware ID  

### 💾 Base de datos
- Acceso no autorizado a SQLite  
- Inyección SQL  
- Modificación directa de registros críticos  

### 📦 Backups
- Acceso indebido a la carpeta `/respaldo`
- Exposición de datos sensibles en copias  

---

## ⚠️ Buenas prácticas implementadas

El proyecto implementa:

- Uso de variables de entorno para datos sensibles  
- Eliminación de credenciales por defecto (desde v1.20.0)  
- Validación de contraseñas fuertes  
- Sistema de autenticación con roles (RBAC)  
- Validación de inputs del usuario  
- Protección contra:
  - Inyección SQL
  - XSS
  - CSRF (cuando aplica)

---

## 🚫 Prácticas consideradas vulnerabilidades

Se consideran fallos de seguridad:

- Hardcodear claves (`SECRET_KEY`, tokens, etc.)
- Subir archivos `.env` al repositorio  
- Exponer endpoints sin autenticación  
- Bypass del sistema de licencias  
- Manipulación de precios, stock o ventas sin control  
- Acceso directo a la base de datos sin validación  

---

## 🧪 Entornos

El sistema puede ejecutarse en:

- Entorno local (Flask + pywebview)
- Aplicación de escritorio empaquetada

⚠️ El servidor de desarrollo de Flask **no debe usarse en producción**

---

## 📦 Dependencias

Las dependencias son monitoreadas mediante:

- Dependabot alerts  
- Actualizaciones periódicas del entorno Python  

---

## 🆕 Historial y cambios relevantes de seguridad

Cambios importantes relacionados a seguridad:

### v1.20.0
- Eliminación de credenciales por defecto  
- Implementación de contraseñas seguras  
- Sistema de recuperación de cuenta  
- Panel de gestión de usuario  

Estos cambios mejoran significativamente la seguridad del sistema.

---

## 🙏 Reconocimiento

Se agradece a quienes reporten vulnerabilidades de forma responsable.

---

## 📢 Nota final

Dado que este sistema gestiona información comercial sensible, la seguridad, integridad y disponibilidad de los datos son prioridades fundamentales del proyecto.
