# AGENTS.md — Instrucciones obligatorias para IA

## Lectura obligatoria

Antes de modificar código, leer:

1. docs/ai/AI_CONTEXT.md
2. docs/ai/ROADMAP_NEXAR_COMERCIO.md
3. docs/ai/AI_WORKFLOW.md
4. docs/ai/AI_CHANGELOG.md
5. El repositorio externo `nexar-ai-context` para el contexto transversal del ecosistema Nexar.

## Regla de ramas

Nunca trabajar directamente sobre main.

Cada mejora, fix o análisis con cambios debe hacerse en una rama propia.

Formato recomendado:

- feature/nombre-corto
- fix/nombre-corto
- docs/nombre-corto
- refactor/nombre-corto solo si el usuario lo pide explícitamente

Ejemplo:

git checkout main
git pull origin main
git checkout -b feature/flujo-compra-producto-nuevo

## Flujo obligatorio

1. Partir desde main actualizado.
2. Crear rama propia.
3. Hacer cambios mínimos.
4. No tocar áreas fuera del alcance.
5. Actualizar docs/ai/AI_CHANGELOG.md.
6. No crear tag.
7. No versionar release.
8. No hacer merge a main sin autorización del usuario.

## Áreas protegidas

No tocar salvo pedido explícito:

- licencias
- Mercado Pago
- Supabase
- actualizaciones
- builds
- instaladores
- GitHub Actions
- nombre técnico nexar-tienda

## Prioridad

No romper lo que ya funciona.
