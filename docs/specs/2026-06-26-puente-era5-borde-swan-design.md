# Diseño — Puente ERA5/serie → condición de borde SWAN

Fecha: 2026-06-26
Herramienta: Tablero de Oleaje
Estado: aprobado, pendiente de plan de implementación

## Objetivo

Permitir derivar la **condición de borde** de un caso SWAN ("Armar y correr") a
partir de una serie de oleaje (descargada de ERA5 o un `.mat/.csv/.nc` propio),
en vez de teclearla a mano. Mantener **intactos** todos los flujos actuales
(visualizar casos por separado): esto solo **agrega** la opción.

El nexo ERA5→SWAN que hoy es manual (mirar el régimen y copiar Hs/Tp/Dir al
formulario) pasa a ser asistido: la herramienta calcula Hs/Tp/Dir de la
condición elegida y rellena el formulario. Lado, dispersión direccional (dd),
malla y batimetría siguen siendo del usuario.

## Contexto y restricciones

- El formulario "Armar y correr" vive en `gui_swan.VentanaSwan._pestana_nuevo`;
  los campos de borde son `self.v["hs"]`, `self.v["per"]`, `self.v["dir"]`,
  `self.v["dd"]` (StringVars) y los lados, checkboxes en `self.lados`.
- El régimen extremo ya está en `productos._calc_retorno` (ajuste Gumbel a los
  máximos anuales → Hs de diseño por periodo de retorno). Da **solo Hs**.
- El borde que consume `swan_builder.construir_swn` es una lista de dicts
  `{lado, hs, per, dir, dd}`.
- La carga de series ya existe: `io_oleaje.cargar(ruta)` (.mat/.csv/.nc) e
  `io_era5` (Datasets con Hs/Tp/Dir).
- **Convención direccional (decisión incluida en este diseño):** el `.swn` que
  genera `swan_builder` hoy **no** emite `SET NAUTICAL`, así que SWAN interpreta
  el `dir` del borde en convención **cartesiana**. El oleaje de ERA5 y de los
  datos del usuario viene en convención **náutica** (dirección de procedencia,
  grados desde el Norte en sentido horario). Para que el Dir derivado sea
  físicamente correcto, el builder pasará a emitir `SET NAUTICAL`. Efecto
  colateral asumido: el campo "Dir" del formulario "Armar y correr" queda en
  convención náutica ("de dónde viene el oleaje"), que es lo natural para datos
  reales. Se documenta en el README/etiqueta del campo.

## Arquitectura

Un módulo nuevo (motor puro) + relleno compartido en la ventana SWAN + dos
botones disparadores + el ajuste de convención del builder.

```
borde_oleaje.py          motor puro: Dataset(time) + modo → {hs, per, dir}
gui_swan.VentanaSwan     aplicar_borde() + _dialogo_condicion()  (compartido)
   ├─ Vía A: botón "Tomar borde de ERA5/serie…" (pestaña Armar y correr)
   └─ Vía B: abrir la ventana ya con un borde aplicado
app_tablero (ventana ERA5)  Vía B: botón "Enviar a SWAN como borde"
swan_builder.construir_swn  emite SET NAUTICAL (convención del Dir del borde)
```

### 1. `borde_oleaje.py` — motor puro

`condicion_borde(ds, modo, periodo_retorno=100) -> dict` con claves
`{"hs", "per", "dir", "descripcion"}`. `ds` es cualquier `Dataset(time)` con
`Hs` (y, según el modo, `Tp`/`Dir`). Modos:

- **`"retorno"`**: `hs` = Gumbel ppf(1−1/T) ajustado a los máximos anuales
  (misma lógica que `productos._calc_retorno`); `per` y `dir` = los del instante
  de **mayor Hs observado** (el temporal real más fuerte). `descripcion` =
  `"Periodo de retorno T={T} años"`.
- **`"maximo"`**: `hs`/`per`/`dir` = los del instante de mayor Hs.
  `descripcion` = `"Máximo observado (YYYY-MM-DD)"`.
- **`"reinante"`**: `hs` = mediana de Hs (p50); `per` = mediana de Tp; `dir` =
  centro del sector direccional dominante (rosa de 16 sectores de 22.5°).
  `descripcion` = `"Oleaje reinante (p50)"`.

Devuelve `per`/`dir` como `None` si la variable necesaria no está en `ds` (serie
sin Tp o sin Dir). Función pura, sin estado, testeable sin GUI.

### 2. `gui_swan.VentanaSwan` — relleno compartido

- `aplicar_borde(borde)`: escribe `self.v["hs"/"per"/"dir"]` con los valores del
  dict (deja en blanco los `None`); registra en el log qué condición se aplicó
  (`borde["descripcion"]`). No toca lado/dd/malla/batimetría. Si el formulario
  aún no existe (ventana recién abierta), guarda el borde y lo aplica al
  construirse.
- `gui_swan.dialogo_condicion(parent) -> (modo, periodo_retorno) | None`:
  **función de módulo** (no método) con un diálogo modal pequeño: radios
  (retorno / máximo / reinante) y un campo de T (solo relevante para retorno;
  default 100). Devuelve `None` si se cancela. Es función de módulo para que la
  usen tanto la Vía A (dentro de `VentanaSwan`) como la Vía B (desde la ventana
  ERA5 de `app_tablero`, antes de abrir `VentanaSwan`).
- `__init__(..., borde_inicial=None)`: si se pasa un borde, lo aplica tras armar
  el formulario y deja la pestaña "Armar y correr" activa (soporta la Vía B).

### 3. Vía A — botón en el formulario SWAN ("tirar")

En `_pestana_nuevo`, botón **"Tomar borde de ERA5/serie…"** →
`_tomar_borde_archivo()`:
1. `filedialog` para elegir `.nc/.mat/.csv`.
2. `_dialogo_condicion()`.
3. `io_oleaje.cargar(ruta)` → `borde_oleaje.condicion_borde(ds, modo, T)`.
4. `aplicar_borde(borde)`.

### 4. Vía B — botón en la ventana ERA5 ("empujar")

En la ventana "Descargar ERA5" de `app_tablero`, botón **"Enviar a SWAN como
borde"** → `_enviar_borde_swan()`:
1. Usa el `.nc` de la serie ERA5 ya descargada (la ruta que la ventana dejó en
   `self.ruta_datos`, o el último `era5_serie.nc`).
2. `_dialogo_condicion()` (reutiliza el de `VentanaSwan`, expuesto como función
   de módulo o método estático).
3. Carga el Dataset → `condicion_borde` → abre
   `gui_swan.VentanaSwan(self, borde_inicial=borde)`.

Ambas vías convergen en `condicion_borde` + `aplicar_borde`: el código real es
el mismo, los botones solo difieren en de dónde sale el archivo.

### 5. `swan_builder` — convención direccional

`construir_swn` agrega la línea `SET NAUTICAL` antes de las condiciones de borde,
para que el `dir` del borde (náutico) se interprete correctamente. El resto del
`.swn` no cambia.

## Flujo de datos

```
Vía A: archivo .nc/.mat/.csv → io_oleaje.cargar → Dataset(time)
Vía B: era5_serie.nc        → io_oleaje.cargar → Dataset(time)
                                   │
                  borde_oleaje.condicion_borde(ds, modo, T)
                                   │   {hs, per, dir, descripcion}
                  VentanaSwan.aplicar_borde → self.v["hs"/"per"/"dir"]
                                   │
            (usuario completa lado/dd/malla/bot) → construir_swn (SET NAUTICAL) → correr
```

## Manejo de errores

- **Modo retorno con pocos datos**: si hay <2 máximos anuales → `ValueError`
  con mensaje claro (no se puede ajustar Gumbel). Si hay entre 2 y ~10 años →
  se calcula igual pero `descripcion` incluye un aviso de baja fiabilidad, que
  `aplicar_borde` muestra en el log.
- **Serie sin Tp o sin Dir**: `condicion_borde` devuelve esa clave en `None`;
  `aplicar_borde` deja el campo en blanco y avisa en el log para que el usuario
  lo complete a mano.
- **Archivo ilegible / sin Hs**: el handler de la GUI captura la excepción y la
  muestra con `messagebox`, sin cerrar la ventana.

## Tests

- `condicion_borde` sobre una serie sintética (varios años, un peak conocido):
  - `"maximo"` devuelve exactamente Hs/Tp/Dir del instante del peak.
  - `"retorno"` con T grande extrapola Hs por **encima** del máximo observado y
    hereda el Tp/Dir del peak.
  - `"reinante"` cae cerca de la mediana de Hs y en el sector direccional
    dominante.
  - serie sin `Dir` → `dir is None` sin reventar.
  - <2 años en modo retorno → `ValueError`.
- `swan_builder.construir_swn` incluye `SET NAUTICAL` (y los tests existentes del
  builder siguen pasando).
- `aplicar_borde`: con un doble simple de `self.v` (dict de objetos con `.set`),
  rellena hs/per/dir y deja en blanco los `None` (sin abrir GUI real).

## Fuera de alcance (YAGNI)

- Sugerir automáticamente el **lado** de entrada a partir de la dirección (depende
  de la orientación del dominio): el usuario lo elige.
- Régimen extremo **direccional** por sectores (un Hs de retorno distinto por
  sector): se usa el retorno global con Tp/Dir del peak.
- Rellenar malla/batimetría desde el ERA5: fuera de alcance.
