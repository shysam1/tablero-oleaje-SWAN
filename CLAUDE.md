# Tablero de Oleaje — guía para Claude Code

Herramienta de análisis de oleaje y SWAN (Python + xarray). Ubicación del repo:
`Herramientas computacionales/Tablero Oleaje/`.

**Estado y arquitectura:** leer siempre `HANDOFF.md` antes de tocar código. Es la bitácora
compartida con Cursor; ahí está el registro de cambios (más reciente primero), GUI actual,
lanzadores, tests y trampas conocidas.

## HANDOFF obligatorio

Este proyecto se trabaja en **paralelo con Cursor**. No des por terminada una tarea con
cambios relevantes sin actualizar `HANDOFF.md`.

### Al empezar

1. Leer `HANDOFF.md` (mínimo: bloque inicial + «Registro de cambios» + sección relacionada).
2. No asumir entry point, GUI ni dependencias sin contrastar con HANDOFF.

### Al terminar (cambios relevantes)

Añadir una entrada **arriba del registro** (fecha, título, agente `Claude Code`) con:

- *Qué/por qué* — qué cambió y por qué
- *Archivos* — rutas tocadas o nuevas
- *Notas* — tests, pendientes, riesgos

Actualizar también las **secciones estáticas** de HANDOFF si quedaron desactualizadas
(p. ej. «GUI + lanzadores», «Entorno», «Modo guiado»).

**Sí documentar:** features, refactors, GUI/lanzadores, deps nuevas, bugs con impacto,
decisiones de diseño.

**No hace falta entrada:** solo Q&A, review sin edits, o cambios triviales.

### Formato de entrada

```markdown
### YYYY-MM-DD · Título breve (Claude Code)
*Qué/por qué:* …
*Archivos:* …
*Notas:* …
```

## Punteros rápidos (confirmar en HANDOFF)

| Qué | Dónde |
|-----|--------|
| UI principal | `app_web.py` + `ui/` (pywebview) — **única interfaz de usuario** |
| Código tk obsoleto | `app_tablero.py`, `asistente.py`, `pasos_*.py`, `gui_swan.py` (tests; no ampliar) |
| Puente web | `api_web.py`, `motor_web.py` |
| Motor SWAN/oleaje | `tablero_oleaje.py`, `swan_runner.py`, `pasos_*.py` |
| Lanzador usuario | `Tablero de Oleaje.lnk` (en carpeta del repo) → `python.exe app_web.py --gui` |
| Tests regresión | `pytest test_regresion.py test_asistente.py test_nesting.py -q` |

## Estilo

- Comentarios y mensajes de UI en **español neutro** (sin voseo).
- Patrón **registro adaptativo** en productos (`requiere=[...]`, reportar lo que falta).
- Correr tests tras cambios que toquen lógica; en este equipo a veces hace falta shell sin sandbox.
- Commitea los cambios relevantes al terminar, con mensaje claro en español, e incluye en el
  mismo commit la entrada del HANDOFF. Trabaja en la rama actual salvo que el usuario pida una
  propia. No hagas push ni fuerces nada sin que el usuario lo pida.

## Docs

`HANDOFF.md` (bitácora, **prioridad**) · `README.md` · `DISEÑO.md` · `test_regresion.py`
