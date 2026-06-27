# Asistente guiado del Tablero de Oleaje — diseño

**Fecha:** 2026-06-26
**Estado:** aprobado (brainstorming), pendiente de plan de implementación
**Sub-proyecto:** C del plan de usabilidad (asistente / modo guiado). A (malla por lat/lon) ya está hecho; B (validación SWAN vs medición) queda para después.

## Problema

Hoy la app es una caja de herramientas potentes pero **sueltas**: botones *Crear*, *Procesar SWAN…*, *Descargar ERA5…* y diálogos anidados (borde, batimetría, lat/lon) sin un orden visible. Para alguien que conoce el flujo es cómodo; para un novato no hay nada que diga "primero esto, después esto". El objetivo es poner un **modo guiado** encima de lo que ya funciona, sin perder ninguna funcionalidad actual y sin reescribir el motor.

## Decisiones tomadas en el brainstorming

1. **Pantalla de inicio nueva** ("¿Qué querés hacer?") como primera vista de la app. La GUI actual se conserva como **modo avanzado** accesible. Se permiten mejoras de claridad en la GUI donde aporten.
2. **Tres caminos** guiados: *Analizar oleaje en un punto*, *Modelar propagación con SWAN*, *Ver corrida SWAN existente*. ERA5 no es un camino propio: va embebido como medio dentro de los caminos que lo necesitan.
3. **No perder funcionalidad** existente con la nueva GUI.
4. **Modelo anidado (nesting):** deseado, pero requiere motor nuevo (el `swan_builder` actual solo arma un dominio). Se hace como **2.º proyecto** con su propio spec y tests. El wizard deja preparado el "hueco" para enchufarlo (ver más abajo).
5. **Orden:** asistente primero (sobre lo que ya funciona), nesting después.
6. **Navegación del wizard:** un paso por pantalla (tipo instalador), con barra de pasos arriba y botones Atrás/Siguiente abajo. Mismo patrón para los 3 caminos.
7. **Enfoque arquitectónico:** mini-framework de wizard reutilizable + vistas conmutables dentro de la misma ventana; los pasos reutilizan las funciones de módulo ya existentes (no se reescribe motor).

## Arquitectura

La ventana principal `AppTablero` deja de ser "una pantalla con botones" y pasa a ser un **contenedor de vistas** que muestra una a la vez dentro del mismo frame:

```
AppTablero (Tk)
 └─ contenedor (Frame que intercambia vistas)
     ├─ VistaInicio          ← "¿Qué querés hacer?"
     ├─ Wizard "Analizar"    ┐
     ├─ Wizard "Modelar"     ├─ los 3 caminos guiados
     ├─ Wizard "Ver corrida" ┘
     └─ VistaAvanzado        ← la GUI actual, movida tal cual
```

### Módulo nuevo `asistente.py`

Dos piezas reutilizables, independientes de los caminos concretos:

- **`Paso`** (clase base, hereda de `ttk.Frame`): contrato de tres métodos.
  - `entrar(contexto)`: se llama al mostrar el paso; puede leer lo que dejaron los pasos previos para precargar/ajustar widgets.
  - `validar() -> (ok: bool, mensaje: str)`: decide si se puede avanzar; el mensaje se muestra si `ok` es `False`.
  - `recoger(contexto)`: guarda los resultados del paso en el `contexto` compartido.
- **`Wizard`** (controlador, hereda de `ttk.Frame`): recibe título + lista de pasos. Dibuja la **barra de progreso de pasos** arriba y los botones **← Inicio / Atrás / Siguiente** abajo. Mantiene un `dict` **`contexto`** que viaja entre pasos. "Siguiente" solo avanza si `validar()` da OK (y antes llama `recoger`); en el último paso el botón dice "Finalizar". "← Inicio" vuelve a `VistaInicio` (con confirmación si hay trabajo a medias).

### Reuso del motor (qué NO se reescribe)

Los pasos llaman a lo que ya existe y está probado:

| Necesidad | Función/módulo reutilizado |
|---|---|
| Malla por lat/lon | `geo_malla.malla_desde_latlon` |
| Batimetría `.bot` | `io_batimetria.generar_bot` / `leer_raster_local` |
| Borde desde serie | `borde_oleaje.condicion_borde` |
| Descarga ERA5 | `io_era5.descargar_serie` / `descargar_espectro` |
| Carga de serie | `io_oleaje.cargar` |
| Validación física serie | `validacion.py` |
| Armar/correr SWAN | `swan_builder.validar_caso` / `escribir_caso`, `swan_runner.correr_swan` |
| Detección estac./nonst. | `io_swan_nonst.es_corrida_nonst` |
| Productos | `tablero_oleaje`, `tablero_swan`, `video_swan` |
| Salidas | `rutas.carpeta_salida` |

El trabajo pesado (descargas, SWAN, video) corre en hilo con `progress_callback`, igual que hoy.

## Pantalla de inicio (`VistaInicio`)

Primera vista al abrir la app. Tres tarjetas grandes (una por camino) + acceso discreto al modo avanzado:

```
┌─ Tablero de Oleaje ───────────────────────────┐
│  ¿Qué querés hacer?                            │
│  ┌──────────────┐ ┌──────────────┐ ┌────────┐ │
│  │ 📈 Analizar   │ │ 🌊 Modelar    │ │ 🗺️ Ver  │ │
│  │ oleaje en un │ │ propagación  │ │ corrida│ │
│  │ punto        │ │ con SWAN     │ │ SWAN   │ │
│  │ datos o ERA5 │ │ malla→…→mapas│ │ hecha  │ │
│  └──────────────┘ └──────────────┘ └────────┘ │
│  Herramientas sueltas (modo avanzado) →        │
└────────────────────────────────────────────────┘
```

Cada tarjeta: título + una línea de qué hace. Click → cambia la vista al wizard correspondiente. El enlace inferior lleva a `VistaAvanzado`. Todo en la misma ventana; sin Toplevels nuevos para los caminos.

## Los tres caminos

### Camino A · Analizar oleaje en un punto (3 pasos)

1. **Origen de datos.** Dos opciones: *Tengo un archivo* (selector `.mat/.csv/.nc`) o *Descargar de ERA5* (lat/lon/fechas + checks espectro/viento → `io_era5.descargar_serie` en hilo con barra; deja el `.nc` en el `contexto`).
2. **Revisión.** Carga con `io_oleaje.cargar`, corre `validacion.py` y muestra: variables presentes, rango temporal, avisos físicos y **qué productos se podrán generar** (registro adaptativo; lo que falta también se nombra).
3. **Generar tablero.** `tablero_oleaje.generar_tablero` → abre el PNG y muestra la ruta de salida. Fin.

### Camino B · Modelar propagación con SWAN (5 pasos; un dominio en v1)

1. **Malla.** Centro lat/lon + ancho/alto + celda → `geo_malla.malla_desde_latlon`. Muestra zona UTM y nº de celdas.
2. **Batimetría.** *Descargar automática* (`io_batimetria.generar_bot`, GEBCO/ETOPO) o *usar `.bot` propio*. Muestra prof. mín/máx y % en tierra.
3. **Borde.** *Manual* (Hs/Tp/Dir/dispersión + lados de entrada) o *derivar de ERA5/serie* (`borde_oleaje.condicion_borde`, modos retorno/máximo/reinante). ← punto de inserción del nesting.
4. **Correr SWAN.** `swan_builder.validar_caso` (errores/avisos) → `escribir_caso` → `swan_runner.correr_swan` con log en vivo, barra indeterminada y **Cancelar** (mismo comportamiento que `VentanaSwan` hoy).
5. **Ver resultados.** Al terminar, `tablero_swan.generar_tablero_swan` y abre el mapa. Fin.

### Camino C · Ver corrida SWAN existente (3 pasos)

1. **Elegir carpeta** de la corrida.
2. **Autodetección.** `io_swan_nonst.es_corrida_nonst` decide mapas vs. video; muestra dominios/variables detectados. Campo *offset UTM* (avanzado) disponible aquí.
3. **Generar.** `tablero_swan` o `video_swan` (con barra en el video) → abre el resultado. Fin.

## El hueco del nesting

Para que el 2.º proyecto (motor de nido) entre sin reescribir el wizard:

- El `contexto` del camino B guarda los dominios como **lista** desde ya: `contexto["dominios"] = [grande]`. En v1 hay uno solo.
- Los pasos 4 (correr) y 5 (ver) **iteran sobre `contexto["dominios"]`**, de modo que su firma no cambia cuando aparezca el nido.
- El nesting agregará, entre el paso 3 y el 4, un paso opcional *"¿Agregar dominio anidado?"* que reutiliza los mismos pasos de malla/batimetría para el nido y hace `append` a la lista.

Es decir: hoy se deja la estructura de datos y el bucle preparados; el nido será aditivo, no una reescritura.

## Modo avanzado y preservación

- **Modo avanzado = GUI actual intacta.** Se mueve el cuerpo de `_construir_widgets` a `VistaAvanzado` **sin tocar su lógica** (mismos métodos `_crear`, `_abrir_swan`, `_abrir_era5`, `_despachar`, offset UTM, consola embebida). Cero funcionalidad perdida; sigue siendo la red de seguridad para uso experto. Botón "← Inicio" para volver.
- **Lanzadores.** `Tablero de Oleaje.lnk` / `Crear Tablero.bat` siguen abriendo `app_tablero`; ahora arranca en *Inicio*.

## Testing

- El **motor no cambia** → `test_regresion.py` sigue siendo válido y debe quedar verde.
- **Framework de wizard:** la máquina de estados del `Wizard` (orden de pasos, avanzar solo si `validar()` OK, propagación del `contexto`, Atrás/Siguiente, Finalizar) se diseña separada de la parte tkinter para poder cubrirla con tests usando pasos *fake* sin abrir ventana.
- **Validación de cada paso real** (p. ej. lat/lon fuera de rango, fechas faltantes) se apoya en las funciones puras que ya tienen los módulos (`geo_malla`, `validar_inputs_era5`, `swan_builder.validar_caso`), testeables sin GUI.
- El **render visual** se verifica corriendo la app (no automatizado).

## Fuera de alcance (v1)

- Motor de modelo anidado (NGRID/NESTOUT + BOUN NEST, malla/batimetría del nido) → 2.º proyecto.
- Validación SWAN vs medición (scatter/sesgo/RMSE) → sub-proyecto B, posterior.
- Persistencia de "proyectos" guardados para retomar un flujo a medias (YAGNI por ahora; el `contexto` vive mientras la app está abierta).
