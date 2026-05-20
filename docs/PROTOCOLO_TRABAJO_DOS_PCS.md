# Protocolo de trabajo con Git, Codex y dos PCs

Este protocolo sirve para trabajar en el repo de Nexar sin desincronizar ramas, versiones o cambios locales entre distintas máquinas.

La idea principal es simple:

> GitHub es la fuente de verdad. Cada PC tiene una copia local, pero antes de trabajar siempre hay que sincronizar con `origin/main`.

---

## 1. Regla principal

Nunca empezar una fase nueva sin hacer primero:

```powershell
git status
git fetch origin
git checkout main
git pull origin main
```

Después recién crear una rama nueva.

---

## 2. Empezar a trabajar en una PC

Usar esto al abrir el proyecto:

```powershell
cd C:\Users\usuario\Documents\nexar-tienda

git status
git fetch origin
git checkout main
git pull origin main
git status
```

Verificar que no haya cambios pendientes.

---

## 3. Crear una rama nueva para una fase

Siempre crear la rama desde `main` actualizado:

```powershell
git checkout main
git pull origin main
git checkout -b feature/nombre-de-la-fase
```

Ejemplo:

```powershell
git checkout -b feature/arca-arquitectura-base
```

---

## 4. Continuar una rama existente

Si la rama ya existe en la PC:

```powershell
git fetch origin
git checkout feature/nombre-de-la-fase
git pull origin feature/nombre-de-la-fase
git rebase origin/main
```

Si la rama existe en GitHub pero no en esa PC:

```powershell
git fetch origin
git checkout -b feature/nombre-de-la-fase origin/feature/nombre-de-la-fase
git rebase origin/main
```

---

## 5. Antes de pedirle algo a Codex

Pedirle siempre que empiece verificando Git.

Prompt base recomendado:

```text
Antes de modificar código:
1) Ejecutar git status.
2) Ejecutar git fetch origin.
3) Verificar rama actual.
4) Si la rama depende de main, asegurar que está basada en origin/main actualizado.
5) Si hay cambios sin commit, no hacer pull/rebase destructivo sin guardarlos antes.
6) No tocar main directo.
7) Trabajar solo en la rama actual o crear una rama feature si corresponde.
8) No cambiar VERSION, CHANGELOG ni crear tag salvo que el pedido sea explícitamente versionar/release.
```

---

## 6. Guardar avance antes de cambiar de PC

Antes de apagar, cerrar VS Code o seguir en otra máquina:

```powershell
git status
python -m pytest
git add .
git commit -m "wip: guardar avance"
git push
```

Si no querés hacer un commit definitivo, igual conviene hacer un `wip` en una rama de trabajo. Es mejor tener un commit temporal que dejar cambios sueltos en una PC.

---

## 7. Si hay cambios sin terminar

Usar commit WIP:

```powershell
git add .
git commit -m "wip: avance parcial"
git push
```

Después, cuando la fase quede bien, se puede ordenar con otro commit o squash desde GitHub si hace falta.

---

## 8. Verificar si la rama local está atrasada

Estos comandos ayudan a detectar si la PC quedó vieja:

```powershell
git fetch origin
git rev-list --left-right --count main...origin/main
git rev-list --left-right --count HEAD...origin/main
```

Interpretación:

```text
0    0
```

Todo sincronizado.

```text
0    7
```

Tu rama local está 7 commits atrás de `origin/main`.

```text
2    0
```

Tu rama local tiene 2 commits que todavía no están en `origin/main`.

```text
1    3
```

Tu rama tiene 1 commit propio y le faltan 3 commits de `origin/main`. Conviene rebasear.

---

## 9. Rebase seguro sobre origin/main

Cuando una rama fue creada desde un main viejo:

```powershell
git status
git add .
git commit -m "wip: guardar cambios antes de rebase"
git fetch origin
git rebase origin/main
```

Si hay conflictos:

```powershell
git status
```

Resolver archivos conflictivos, luego:

```powershell
git add .
git rebase --continue
```

Después verificar:

```powershell
python -m pytest
git status
```

---

## 10. Cuidado especial con archivos de versión

Estos archivos no se deben tocar salvo fase de versionado/release:

```text
VERSION
CHANGELOG.md
README.md
build/nexar_tienda.iss
```

Si hay conflicto en esos archivos durante un rebase, normalmente debe ganar lo que trae `origin/main`, salvo que estemos haciendo una release nueva.

Ejemplo: si `origin/main` está en `1.35.1`, no dejar la rama en `1.35.0`.

---

## 11. Cerrar una fase correctamente

Antes de abrir PR:

```powershell
git status
python -m pytest
git log --oneline --decorate -8
type VERSION
```

Verificar:

- tests pasando;
- rama correcta;
- versión correcta;
- sin cambios sin commit;
- app probada manualmente si aplica.

Después:

```powershell
git push -u origin feature/nombre-de-la-fase
```

Luego abrir PR hacia `main`.

---

## 12. Después de mergear un PR

En cada PC hay que actualizar `main`:

```powershell
git fetch origin
git checkout main
git pull origin main
```

Si la rama ya no sirve:

```powershell
git branch -d feature/nombre-de-la-fase
```

Si también querés borrar la rama remota:

```powershell
git push origin --delete feature/nombre-de-la-fase
```

---

## 13. No trabajar directo sobre main

Evitar esto:

```powershell
git checkout main
# modificar código directo en main
```

Mejor siempre:

```powershell
git checkout main
git pull origin main
git checkout -b feature/nueva-fase
```

---

## 14. Flujo recomendado con Codex

1. Yo defino fase y prompt.
2. Codex trabaja en una rama feature.
3. Codex ejecuta tests.
4. Se revisa `git status`.
5. Se prueba manualmente la app.
6. Se hace commit.
7. Se hace push.
8. Se abre PR.
9. Se mergea.
10. Se actualizan las dos PCs.

---

## 15. Comandos útiles de diagnóstico

Ver rama actual:

```powershell
git branch --show-current
```

Ver estado:

```powershell
git status
```

Ver últimos commits:

```powershell
git log --oneline --decorate -8
```

Ver diferencias contra remoto:

```powershell
git fetch origin
git rev-list --left-right --count HEAD...origin/main
```

Ver versión actual:

```powershell
type VERSION
```

Buscar entrada en changelog:

```powershell
Select-String -Path CHANGELOG.md -Pattern "## \[1.35.1\]" -Context 0,6
```

Ejecutar tests:

```powershell
python -m pytest
```

---

## 16. Activar y desactivar módulos por entorno en PowerShell

Desactivar módulos extra:

```powershell
Remove-Item Env:NEXAR_EXTRA_MODULES -ErrorAction SilentlyContinue
Remove-Item Env:NEXAR_MODULES -ErrorAction SilentlyContinue
```

Activar ARCA:

```powershell
$env:NEXAR_EXTRA_MODULES="arca_facturacion"
```

Probar app:

```powershell
python app.py
```

---

## 17. Protocolo para releases

Solo hacer release cuando la fase esté mergeada en `main` y probada.

Antes de tag:

```powershell
git checkout main
git pull origin main
type VERSION
python -m pytest
```

Crear tag:

```powershell
git tag vX.Y.Z
git push origin vX.Y.Z
```

Verificar que GitHub Actions se dispare.

No crear tags desde una rama feature.

---

## 18. Scripts opcionales

Se pueden crear scripts para reducir errores.

### scripts/dev_start.ps1

```powershell
git status
git fetch origin
git checkout main
git pull origin main
git status
```

### scripts/dev_save.ps1

```powershell
git status
python -m pytest
git add .
git commit -m "wip: guardar avance"
git push
```

---

## 19. Resumen corto para no meter la pata

Antes de empezar:

```powershell
git fetch origin
git checkout main
git pull origin main
```

Antes de cambiar de PC:

```powershell
git add .
git commit -m "wip: guardar avance"
git push
```

Antes de PR:

```powershell
python -m pytest
git status
type VERSION
```

Antes de release:

```powershell
git checkout main
git pull origin main
type VERSION
python -m pytest
git tag vX.Y.Z
git push origin vX.Y.Z
```
