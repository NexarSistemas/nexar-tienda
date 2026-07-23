# AGENTS.md — Instrucciones obligatorias para IA

## Lectura obligatoria

Antes de modificar código, leer:

1. `README.md`
2. `docs/ai/AI_CONTEXT.md`
3. `docs/ai/ROADMAP_NEXAR_COMERCIO.md`
4. `docs/ai/AI_WORKFLOW.md`
5. `docs/ai/AI_CHANGELOG.md`
6. El repositorio externo `nexar-ai-context`, especialmente `CONTEXTO_NEXAR.md`, `repos/nexar-tienda/CONTEXTO_REPO.md` y `standards/AI_WORKFLOW.md`, si está disponible.
7. Issues y PR abiertas relacionadas.

## Roles

- ChatGPT analiza, diseña, revisa y redacta prompts.
- Codex implementa, valida y ejecuta el flujo Git.
- Copilot/Gemini auditan o proponen salvo instrucción explícita.

## Regla de ramas

Nunca trabajar directamente sobre `main`.

Usar ramas:

- `feature/*`
- `fix/*`
- `docs/*`
- `test/*`
- `chore/*`
- `refactor/*` solo si el usuario lo pide explícitamente

Usar remoto SSH. `main` recibe cambios solo mediante Pull Request y la estrategia predeterminada es `Squash and Merge`.

## Flujo obligatorio

1. Partir desde `main` actualizada.
2. Crear rama propia.
3. Hacer cambios mínimos y trazables.
4. No tocar áreas fuera del alcance.
5. No mezclar refactorización con cambios funcionales.
6. Reutilizar helpers y convenciones existentes.
7. Actualizar `docs/ai/AI_CHANGELOG.md` cuando corresponda.
8. Ejecutar tests focalizados y después la suite completa del repo.
9. Ejecutar `git diff --check` y confirmar `git status` limpio.

## Revisión eficiente

- La primera revisión puede cubrir toda la implementación.
- Revisiones posteriores: analizar solo `COMMIT_ANTERIOR...COMMIT_NUEVO`.
- No reauditar módulos no modificados ni ampliar el alcance sin regresión directa demostrada.
- Si hay tests fallidos, conflictos, checks fallidos, hallazgos funcionales reales o PR no mergeable, detenerse y no mergear.
- Si la revisión final resulta `APROBABLE`, cerrar automáticamente: Ready for Review si aplica, validación final, `Squash and Merge`, actualización de `main`, eliminación de ramas y `git status` limpio.

## Áreas protegidas

No tocar salvo pedido explícito y revisión de impacto transversal:

- licencias;
- Mercado Pago;
- Supabase;
- actualizaciones;
- builds;
- instaladores;
- GitHub Actions;
- nombre técnico `nexar-tienda`.

`Nexar Comercio` es la marca visible. `nexar-tienda` sigue siendo el identificador técnico compatible y no debe reemplazarse por otro producto legacy.

## Versionado

- Crear tag y Release solo cuando la tarea indique explícitamente un cierre de versión.
- No crear tag o release para fixes internos, revisiones post-merge o cambios documentales aislados.
- Cerrar un Issue solo si quedó completamente resuelto.

## Prioridad

No romper lo que ya funciona. Si falta evidencia, usar `TODO(confirmar)` en vez de inventar comportamiento.
