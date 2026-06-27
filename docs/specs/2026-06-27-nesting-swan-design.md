# Modelo anidado (nesting) SWAN en el camino Modelar — diseño

**Fecha:** 2026-06-27
**Estado:** aprobado (brainstorming), pendiente de plan de implementación
**Sub-proyecto:** el "2.º proyecto" que dejó preparado el asistente guiado (hueco del nesting). Ver `2026-06-26-asistente-guiado-design.md`.

## Problema

El camino guiado **Modelar** (y el modo avanzado "Armar y correr") construye **un solo dominio**: un `CGRID` con un `INPGRID`/`.bot`. Las corridas reales del usuario (p. ej. Coronel extremo Tr100) son **anidadas**: un dominio grande (Golfo de Arauco, malla gruesa) y un dominio nido (Bahía de Coronel, malla fina), cada uno con su **propia batimetría**. Por eso el usuario tuvo que armar el Tr100 a mano con dos `.bot`, y la app no puede reproducirlo desde cero.

Hoy la app **sí** puede correr y graficar un caso anidado ya armado (modo avanzado → "Correr caso existente" + "Crear"; `swan_runner` ordena grande→nido). La carencia está en **construir** el par anidado desde el flujo guiado.

## Sintaxis de referencia (Tr100 del usuario)

Grande (`Coronel1.swn`):
```
CGRID 0. 0. 0. 48000 59000 48 59 Circle 180 .04 1
INPGRID BOTTOM 0. 0. 0. 48 59 1000. 1000.
READINP BOTTOM 1. 'batGC.bot' 1 0 FREE
BOUN SIDE W CCW CON PAR 8.16 13 315. 17.7
...
NGRID 'subN1' 36480 32229 0. 9000 10000 45 50
NESTOUT 'subN1' 'CoronelNest1'
COMPUTE
```
Nido (`Coronelanidada.swn`):
```
CGRID 36480 32229 0. 9000 10000 45 50 Circle 180 .04 1
INPGRID BOTTOM 36480 32229 0. 45 50 200. 200.
READINP BOTTOM 1. 'bataniGC.bot' 1 0 FREE
BOU NEST 'CoronelNest1' CLOSED
...
POINTS 'SpecOut' 42423 37171
SPEC 'SpecOut' SPEC2D ABS 'Espectro_Punto.txt'
COMPUTE
```
El enlace es el nombre del nido (`subN1`) + el archivo de contorno (`CoronelNest1`): el `NGRID`/`NESTOUT` del grande y el `BOU NEST` del nido deben coincidir. El `NGRID` del grande y el `CGRID` del nido describen el **mismo recuadro**.

## Decisiones tomadas en el brainstorming

1. **Ubicación:** el nesting se arma desde el **camino guiado Modelar**, como un paso opcional. (No en el modo avanzado en esta versión.)
2. **Salidas del nido:** mapas `BLOCK` (Hs/Tp/Dir/Setup) **y** un punto espectral opcional (`POINTS`/`SPEC`), como en el Tr100.
3. **Alcance:** un solo nivel de nido (grande + 1 nido). Múltiples niveles/nidos quedan fuera (YAGNI).
4. **Enfoque de motor:** extender `swan_builder` con parámetros opcionales + una función orquestadora; no se crea un módulo paralelo que duplique `construir_swn`.
5. **Coordenadas:** grande y nido en **UTM absolutas** de la misma zona (consistente con el resto del camino Modelar).

## Motor (`swan_builder.py`)

### Parámetros nuevos en `construir_swn`

- **`nido`** (dict o `None`): `{sname, nestfile, xpn, ypn, xlenn, ylenn, mxn, myn}`. Si se pasa, antes de `COMPUTE` el grande emite:
  ```
  NGRID '<sname>' <xpn> <ypn> 0. <xlenn> <ylenn> <mxn> <myn>
  NESTOUT '<sname>' '<nestfile>'
  ```
- **`bou_nest`** (str o `None`): si se pasa, el `.swn` es el nido — en vez de los `BOUN SIDE` emite:
  ```
  BOU NEST '<bou_nest>' CLOSED
  ```
- **`punto_espectral`** (dict o `None`): `{x, y, archivo}`. Si se pasa, tras los `BLOCK` emite:
  ```
  POINTS 'SpecOut' <x> <y>
  SPEC 'SpecOut' SPEC2D ABS '<archivo>'
  ```

Cuando `bou_nest` está presente, `construir_swn` ignora `bordes` (el nido toma su contorno del nesting, no de `BOUN SIDE`).

### Función orquestadora `escribir_par_anidado`

```
escribir_par_anidado(carpeta, nombre_grande, nombre_nido,
                     malla_g, bat_g, bordes,
                     malla_n, bat_n,
                     salidas=("Hs","Tp","Dir"),
                     punto_espectral=None,
                     estacionario=True, tiempo=None) -> (ruta_grande, ruta_nido)
```
1. Deriva el recuadro del nido desde `malla_n` (`xpn=xpc_n`, `ypn=ypc_n`, `xlenn=xlenc_n`, `ylenn=ylenc_n`, `mxn=mxc_n`, `myn=myc_n`).
2. Escribe el `.swn` grande con `nido={sname,…}` + `nestfile`, sus `BLOCK` y `bordes`.
3. Escribe el `.swn` del nido con `malla=malla_n`, `batimetria=bat_n`, `bou_nest=nestfile`, `salidas` y `punto_espectral`.
4. Devuelve `(ruta_grande, ruta_nido)`.

Nombres de enlace fijos: `sname = "nido1"`, `nestfile = "nest1"`.

### Validación `validar_caso_anidado(malla_g, malla_n)`

Devuelve `(errores, avisos)`:
- **Error** si el recuadro del nido no está **contenido** en el del grande (`xpc_n ≥ xpc_g`, `ypc_n ≥ ypc_g`, `xpc_n+xlenc_n ≤ xpc_g+xlenc_g`, idem Y).
- **Error** si la **zona UTM** del nido ≠ la del grande.
- **Aviso** si la celda del nido no es más fina que la del grande.
Cada dominio se valida además con el `validar_caso` existente por separado.

## Orden de corrida (`swan_runner.casos_ordenados`)

Hoy ordena por "CGRID en origen local 0,0 = grande". Como el camino Modelar usa UTM absolutas, se cambia a un criterio **semántico**: un `.swn` que contiene `BOU NEST`/`BOUN NEST` es un nido → corre **después**; el resto corre **antes**. El origen 0,0 queda solo como desempate de respaldo.

Esto da el mismo orden que hoy para Coronel (`Coronel1` sin `BOU NEST` → primero; `Coronelanidada` con `BOU NEST` → después), por lo que el test de regresión se mantiene.

## Camino Modelar (`pasos_modelar.py`)

El wizard pasa de 5 a 6 pasos; el nuevo es opcional, entre Borde y Correr:

```
1. Malla (grande)  2. Batimetría (grande)  3. Borde
4. Dominio anidado (opcional)   ← NUEVO
5. Correr SWAN     6. Ver resultados
```

### `PasoNido` (titulo "Dominio anidado (opcional)")

- Checkbox **"Agregar un dominio anidado (nido) más fino"**. Apagado → `validar()` pasa y `recoger()` no agrega nada (flujo de un dominio intacto).
- Encendido habilita:
  - **Malla del nido**: lat/lon centro + ancho/alto [km] + celda [m] → `geo_malla.malla_desde_latlon`. Botón "Calcular malla del nido"; muestra zona y nº de celdas.
  - **Batimetría del nido**: "Generar batimetría del nido" (`io_batimetria.generar_bot` con la malla fina, en la misma `carpeta_caso`) o "Usar .bot propio".
  - **Punto espectral** (opcional): checkbox + lat/lon del punto.
- `validar()` con nido activo: malla del nido calculada, `validar_caso_anidado(grande, nido)` sin errores, y batimetría del nido existente.
- `recoger()` con nido activo: `append` a `contexto["dominios"]` de `{malla, bot, punto_espectral}` (punto en UTM, o `None`). Sin nido: no toca la lista.

### `PasoCorrer` (extensión)

```
dominios = ctx["dominios"]
if len(dominios) == 1:
    # como hoy: construir_swn de un dominio
else:
    g, n = dominios[0], dominios[1]
    # copiar ambos .bot a carpeta_caso
    swan_builder.escribir_par_anidado(carpeta_caso, nombre, nombre+"_nido",
        malla_g=g["malla"], bat_g={"archivo": bot_g.name}, bordes=...,
        malla_n=n["malla"], bat_n={"archivo": bot_n.name},
        salidas=..., punto_espectral=n.get("punto_espectral"))
```
Las validaciones previas (`validar_caso` por dominio, `validar_caso_anidado`) corren antes de escribir. `swan_runner.correr_swan` ya correrá grande→nido (Orden de corrida).

### `PasoVer` (sin cambios de fondo)

`tablero_swan.generar_tablero_swan` ya autodetecta dominios por su `CGRID`, así que grafica grande y nido. El `.txt` del punto espectral queda en la carpeta para animarlo con la infraestructura existente (`io_swan_nonst.leer_espectro_temporal` / `video_swan.animar_espectro`); el tablero no lo grafica.

## Coordenadas y batimetría

- Grande y nido se definen por lat/lon → UTM absolutas (`geo_malla`), misma zona UTM (exigido por `validar_caso_anidado`). El `NGRID` del grande usa las UTM del nido, idénticas a su `CGRID`.
- Cada dominio genera su propio `.bot` (`io_batimetria.generar_bot`): grande grueso, nido fino — esto resuelve las "dos batimetrías".
- El punto espectral en lat/lon → UTM absolutas; aviso si cae fuera del recuadro del nido.

## Testing

- **`swan_builder` (motor puro):** `construir_swn(..., nido=…)` emite `NGRID`/`NESTOUT` con el recuadro correcto; `construir_swn(..., bou_nest=…)` emite `BOU NEST` y **no** `BOUN SIDE`; `punto_espectral` emite `POINTS`/`SPEC`; `escribir_par_anidado` crea dos `.swn` con `sname`/`nestfile` enlazados y el `CGRID` del nido = `NGRID` del grande; `validar_caso_anidado` rechaza un nido fuera del grande o de otra zona UTM, y avisa si la celda no es más fina.
- **`swan_runner`:** `casos_ordenados` sobre la carpeta de Coronel sigue dando `[grande, nido]` con el criterio nuevo (`BOU NEST`).
- **`pasos_modelar`:** Modelar tiene 6 pasos; `PasoNido.recoger` agrega el segundo dominio solo con el checkbox activo, y no toca `dominios` cuando está apagado.
- **Verificación visual** (definir nido → batimetría fina → correr → mapas de ambos dominios): manual, a cargo del usuario.

## Fuera de alcance

- Nesting en el modo avanzado ("Armar y correr").
- Más de un nido o niveles múltiples de anidamiento.
- Corriente/viento como entrada del nido (el `.swn` real del usuario los tenía comentados).
- Graficado automático del espectro del punto dentro del tablero (se usa la animación existente por separado).
