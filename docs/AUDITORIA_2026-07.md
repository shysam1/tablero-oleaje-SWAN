# Auditoría de código — Tablero de Oleaje (julio 2026)

> Auditoría integral realizada por Claude Code en modo /loop, en tres etapas:
> **A)** auditoría de solo lectura por áreas, **B)** corrección de hallazgos CRÍTICOS
> con test de regresión y commit por hallazgo, **C)** cierre con prompt para Cursor
> (hallazgos MEDIO/MENOR y críticos diferidos) y entrada en HANDOFF.md.
>
> **Regla de la etapa A:** ningún archivo de la app se modifica; solo se escribe este
> documento. Cada hallazgo cita código exacto (`archivo:línea`) o se reproduce.
>
> **Clasificación:** CRÍTICO (resultado físico incorrecto, pérdida de datos, crash en
> flujo principal, agujero de seguridad) · MEDIO (bug real pero con workaround o en
> flujo secundario) · MENOR (robustez, UX, texto, deuda).

**Estado:** AUDITORÍA CERRADA (2026-07-06). Etapa A completa (7 áreas), etapa B
completa (A2-1/A2-2/A2-3 corregidos; A6-1 diferido a Cursor), etapa C completa
(«Prompt para Cursor» al final de este documento + entrada en HANDOFF.md).

---

## Resumen ejecutivo

Auditoría completa de las 7 áreas (2026-07-06). Suite de tests en verde
(141 passed, 8 skipped). **Total: 4 CRÍTICOS, 6 MEDIOS, 18 MENORES.**
La mecánica de la app (runner SWAN, seguridad del puente web, UI, descarga por
tramos) está sólida tras los QA de junio; **los problemas graves se concentran en la
física del parseo ERA5** — una zona que la suite no cubre porque valida contra
estructuras sintéticas, no contra los datos reales del CDS.

### CRÍTICOS (rankeados por impacto)

| # | Hallazgo | Evidencia | Impacto |
|---|----------|-----------|---------|
| A2-1 | `mwd + 180°` invierte la dirección del oleaje ERA5 (`io_era5.py:531`) | **Empírica**: caché real del usuario con procedencia NE–E (desde tierra) en la costa del Maule | Rosa de oleaje invertida y borde SWAN derivado de ERA5 con dirección opuesta → corridas inválidas |
| A2-2 | Producto cartesiano año×mes×día sin recorte temporal (`io_era5.py:406-415`, sin `slice` en parsers) | **Reproducida**: rango de 22 días cruzando año nuevo conserva pasos de 2024-01 y 2025-12 | Serie con fechas nunca pedidas; activa productos multi-anuales sobre datos espurios |
| A2-3 | Espectro d2fd con ejes índice 1..30/1..24 sin reconstruir (`io_era5.py:755-768`) | Documentación ECMWF; el código no contiene reconstrucción | Tp, m₀, Hs espectral y partición sea/swell sin sentido con datos reales |
| A6-1 | Instalador Windows: primer arranque sin permisos en Program Files (`TableroOleaje.iss:27-30`, `bootstrap_windows.ps1:26-98`, `rutas.py:15`) | Análisis de permisos NTFS + flujo de elevación Inno | El `.exe` publicado (v1.0.0) deja la app rota de fábrica para usuarios estándar |

### MEDIOS

1. **A1-1** — Percentiles P50/P90/P99 = NaN con huecos en Hs (`productos.py:139-140`; reproducido).
2. **A1-2** — `time` sin ordenar ni validar → span y productos silenciosamente erróneos con CSV desordenado (`io_oleaje.py:84-87`; reproducido).
3. **A2-4** — Credenciales CDS exigen formato `UID:API-KEY` antiguo; endpoint de prueba `/v2/tasks` obsoleto (`io_era5.py:103-114,166`).
4. **A3-1** — Partición espectral integra espectros SWAN (m²/Hz/°) con ddir en radianes → Hs de familias ~7,6× menor (`particion_espectral.py:33` + `productos_swan.py:129`).
5. **A4-1** — `_error_tarea` reduce los `RuntimeError` informativos a "RuntimeError" (`api_web.py:63-67`).
6. **A7-1** — Test de regresión fija el comportamiento erróneo de A2-1 (`test_regresion.py:465-470`); corregir junto con A2-1.

### MENORES (18)

Área 1: rosa no suma 100 % con Dir NaN (A1-3), carpeta espuria por `carpeta_salida`
en comparación (A1-4), motivo de error engañoso en `evaluar` (A1-5), `KeyError` sin
capturar con Efth no estándar (A1-6), JONSWAP sin validar Hs (A1-7).
Área 2: `_cache_utilizable` muerta (A2-5), Dataset lazy bloquea caché en Windows
(A2-6), fechas futuras sin rechazar (A2-7).
Área 3: `swan_disponible` vs `correr_caso` inconsistentes (A3-2), γ=0,29 fijo sin
documentar (A3-3).
Área 4: borrar caché puede fallar sin mensaje (A4-2), tareas no-SWAN sin cancelación
(A4-3).
Área 5: errores invisibles en vistas sin `#inline-error` (A5-1), rechazos del puente
sin capturar (A5-2), textos de credenciales con formato antiguo (A5-3).
Área 6: `.exe` commiteado en el repo (A6-2).
Área 7: `test_motor_web.py` fuera de la suite oficial (A7-2), tests con datos reales
siempre saltados (A7-3).

### Plan de la etapa B (un CRÍTICO por iteración)

1. **A2-1** (+A7-1): quitar el `+180°`, marcar la convención en los atributos de la
   caché parseada para invalidar las cachés corrompidas, actualizar el test que fija
   el bug y añadir test de regresión de la convención.
2. **A2-2**: recortar `time` al rango pedido en `_parsear_serie_nc` y
   `_parsear_espectro_nc` + test con fechas cartesianas espurias.
3. **A2-3**: reconstruir ejes físicos del espectro d2fd (f₁=0,03453 Hz ·1,1ⁿ⁻¹;
   dir=7,5°+15°·(n−1), convertida a procedencia) + corregir etiqueta de unidades +
   test con estructura real del CDS.
4. **A6-1**: evaluar fix parcial testeable (fallback de `rutas.py`/`config.py` a
   `%LOCALAPPDATA%` cuando el código no es escribible); la parte del `.iss` requiere
   compilar/probar instalador → candidata a **DIFERIDO A CURSOR**.

---

## Plan de áreas

| # | Área | Archivos principales | Foco | Estado |
|---|------|----------------------|------|--------|
| 1 | Motor de oleaje y productos | `tablero_oleaje.py`, `productos.py`, `io_oleaje.py`, `validacion.py` | Correctitud física: convenciones de dirección, unidades, NaN, integración espectral | Pendiente |
| 2 | Descarga y caché ERA5 | `io_era5.py` | Casos borde de fechas, tramos mensuales, espectro 2D, corrupción de caché | Pendiente |
| 3 | Cadena SWAN | `swan_runner.py`, `swan_builder.py`, `pasos_modelar.py`, `pasos_ver.py`, nesting (`test_nesting.py` como espejo) | Generación de `.swn`, convención cartesiana vs náutica, manejo de errores de `swan.exe` | Pendiente |
| 4 | Puente web y seguridad | `api_web.py`, `motor_web.py`, `seguridad.py` | Rutas confinadas, inyección por el puente JS, estados de tarea en hilo | Pendiente |
| 5 | UI web | `ui/index.html`, `ui/app.js`, `ui/js/*.js`, `ui/styles.css` | Consistencia endpoints JS↔Python, estados de error visibles, español neutro | Pendiente |
| 6 | Empaquetado e instaladores | `scripts/`, `installer/`, `empaquetar_*`, lanzadores | Rutas hardcodeadas, venv, supuestos de Python 3.11+ | Pendiente |
| 7 | Tests | `test_regresion.py`, `test_asistente.py`, `test_nesting.py` (+ `test_motor_web.py`) | Cobertura real, correr `pytest -q` y reportar | Pendiente |

Módulos de apoyo que se revisan dentro del área que los usa: `borde_oleaje.py`,
`geo_malla.py`, `io_batimetria.py`, `previews.py`, `rutas.py`, `sistema.py`,
`config.py`, `particion_espectral.py`, `productos_particion.py`, `prioridad.py`,
`io_swan.py`, `io_swan_nonst.py`, `productos_swan.py`, `tablero_swan.py`,
`video_swan.py`. Código tkinter obsoleto (`app_tablero.py`, `asistente.py`,
`pasos_analizar.py`, `gui_swan.py`, `estilo.py`) solo se mira si un hallazgo
lo cruza (no se amplía, según HANDOFF).

---

## Área 1 — Motor de oleaje y productos

Archivos revisados: `productos.py`, `io_oleaje.py`, `validacion.py`, `tablero_oleaje.py`,
más `particion_espectral.py`, `productos_particion.py` y `rutas.py` (apoyo directo).
Estado del área: **sin hallazgos CRÍTICOS**. La física central está bien: JONSWAP con
forma estándar y escalado a Hs vía m₀; Gumbel con Gringorten y gating multi-anual;
dirección media circular por componentes (correcta en cualquier convención); rosa en
convención náutica de procedencia (`theta_zero_location("N")`, sentido horario).

### A1-1 · MEDIO — Percentiles de excedencia con NaN → anotaciones "P50 = nan m"

`productos.py:139-140`: `_calc_excedencia` filtra los NaN para la curva, pero los
percentiles se calculan sobre la serie cruda:

```python
crudo = ds["Hs"].values
percentiles = {p: float(np.percentile(crudo, p)) for p in (50, 90, 99)}
```

`np.percentile` propaga NaN. **Reproducido**: serie de 100 puntos con 1 NaN →
`{50: nan, 90: nan, 99: nan}`; el panel dibuja tres anotaciones "P50 = nan m" y
ninguna línea. Cualquier `.mat`/CSV con huecos lo gatilla. Corrección: `np.nanpercentile`
(o percentiles sobre el arreglo `hs` ya filtrado).

### A1-2 · MEDIO — `time` sin ordenar ni validar → productos silenciosamente erróneos

`io_oleaje.py:84-87` (`construir_dataset`) acepta el orden de filas tal cual viene y en
ninguna parte se ordena ni se exige monotonicidad. Con un CSV desordenado:

- `_span_dias` (`productos.py:39-44`) usa `t[-1] − t[0]`; **reproducido**: serie real de
  125 días barajada → span calculado 18,5 días. Eso decide el modo de la serie temporal
  (`productos.py:63-64`) y el gating multi-anual (`productos.py:52-55`) con un dato falso.
- La serie "nativa" se dibuja con zigzag ilegible (líneas que van y vuelven en el eje x).
- `_chequeo_tiempo` (`validacion.py:60-64`) calcula `dif` con saltos negativos: el conteo
  de huecos/duplicados pierde sentido y no avisa del desorden.

Nada crashea ni avisa: resultados físicamente incorrectos en silencio. Corrección:
`ds.sortby("time")` en `construir_dataset` (o rechazo explícito de series no monótonas)
+ chequeo de monotonicidad en `validacion`.

### A1-3 · MENOR — Rosa de oleaje: con Dir NaN los sectores no suman 100 %

`productos.py:276-282`: `n_total` cuenta los registros con Hs finito, pero
`np.histogram` descarta los Dir NaN. **Reproducido**: 10 registros con 3 Dir NaN →
los sectores dibujados suman 70 % sin nota alguna. Corrección: normalizar por registros
con (Hs, Dir) finitos, o anotar el % descartado.

### A1-4 · MENOR — Comparación de destinos crea carpetas vacías espurias

`tablero_oleaje.py:105`: para decidir la etiqueta del PNG se llama
`rutas.carpeta_salida(ruta_entrada.stem)` dentro de la comparación, y esa función
**crea** la carpeta (`rutas.py:27`, `mkdir`). Al generar el tablero de un
`era5_serie.nc` (que vive junto a la caché ERA5), queda una carpeta vacía
`salidas/era5_serie/` que nunca se usa. Además ambas ramas del ternario devuelven
casi lo mismo. Corrección: comparar contra `RAIZ_SALIDAS / seguro` sin crear, o
simplificar a `etiqueta = destino.name`.

### A1-5 · MENOR — `evaluar` reemplaza el error real por el motivo genérico

`productos.py:461-465`: al capturar `ValueError` se descarta su mensaje y se reporta
`motivo_inaplicable` (p. ej. un espectro presente pero sin energía finita se reporta como
"variable Sf o Efth (densidad espectral direccional)", que sugiere que falta la variable).
Diagnóstico engañoso en el informe de capacidades. Corrección: incluir `str(e)` en `faltan`.

### A1-6 · MENOR — `evaluar` no cubre `KeyError`: un Efth con dims no estándar tumba todo el tablero

`productos.py:463` solo captura `(ValueError, ZeroDivisionError, FloatingPointError)`.
`_sf_desde_efth` (`productos.py:333-336`) y `particionar_serie`
(`particion_espectral.py:134-137`) acceden a `["freq"]`, `["dir"]`, `["time"]` sin guard:
un Efth con nombres de coordenada distintos (o sin `time`) lanza `KeyError` que propaga
hasta `generar_tablero` y no se genera ningún panel. Con los datos ERA5 propios no ocurre
(dims garantizadas por `io_era5`); es robustez ante fuentes externas.

### A1-7 · MENOR — JONSWAP no valida Hs

`productos.py:298-301`: `_calc_jonswap` valida solo Tp; con Hs todo-NaN la escala es NaN
y el panel sale con la curva vacía (sin motivo en el informe). Simetría: validar también
`np.isfinite(hs)`.

### Observaciones (sin acción de código)

- **Convención de integración espectral:** `_pesos` (`particion_espectral.py:22-34`)
  devuelve `ddir` en **radianes**; coherente con el Efth de ERA5 (m² s rad⁻¹). Queda
  para el área 3 verificar que los espectros SWAN (SPEC2D en m²/Hz/**grado**) no pasen
  por esta misma integración sin conversión de unidades, y para el área 2 verificar la
  conversión `mwd + 180°` de `io_era5` contra la convención ECMWF.
- **Rayleigh sobre Hs de largo plazo:** el ajuste Rayleigh del panel "Distribución de Hs"
  aplica la forma teórica de alturas individuales dentro de un estado de mar a la
  distribución climática de Hs; como descriptor visual es aceptable y está en DISEÑO.md,
  pero no debe leerse como distribución teórica de Hs (eso sería Weibull/lognormal).
  Decisión de diseño documentada, no bug.

## Área 2 — Descarga y caché ERA5

Archivo revisado: `io_era5.py` (completo, 897 líneas). La infraestructura de descarga
(tramos mensuales, subdivisión ante «cost limits», descarga atómica `.part`, caché
parseada, 2 hilos máximo) está bien construida. Los problemas graves están en la
**física del parseo**, no en la mecánica de red.

### A2-1 · CRÍTICO — ✅ CORREGIDO — La conversión `mwd + 180°` invertía la dirección del oleaje

> **CORREGIDO (etapa B, 2026-07-06):** se eliminó el `+180°` en `_parsear_serie_nc`
> (Dir queda tal cual, `% 360`), se añadió el atributo `dir_convencion="procedencia"`
> a la serie parseada y `_serie_cache_limpia` ahora exige esa marca — las cachés
> antiguas (serie y chunks, con Dir invertida) se descartan y re-descargan solas.
> Tests: `test_parsear_serie_conserva_mwd_como_procedencia` (reemplaza al test que
> fijaba el bug, cierra también A7-1) y
> `test_serie_cache_sin_marca_de_convencion_se_descarta`. Suite: 142 passed.
> Commit: ver referencia al final de la sección de la etapa B.

`io_era5.py:529-531`:

```python
# ECMWF mwd = dirección de propagación; pipeline/SWAN usan procedencia náutica.
if "Dir" in ds.data_vars:
    ds["Dir"] = (ds["Dir"] + 180.0) % 360.0
```

La premisa del comentario es **falsa**: el parámetro escalar `mwd` de ERA5
(paramId 140230, «Mean wave direction», `GRIB_units: Degree true`) ya viene en
convención meteorológica de **procedencia** («direction that waves are coming from»,
según la documentación del CDS). El +180° lo convierte a propagación.

**Verificado empíricamente** sobre la caché real del usuario
(`salidas/ERA5_-35p58_-72p66_20240728_20250729_serie/era5_serie.nc`, costa del Maule,
1 año de datos): la Dir almacenada (tras el +180°) se concentra en **30–90°
(procedencia NE–E, desde tierra)** con mediana 60° — físicamente imposible en la costa
chilena, donde el oleaje procede del SW–W (~210–290°). Los valores originales de `mwd`
eran justamente esos 210–270°: ya eran procedencia.

**Impacto:** rosa de oleaje invertida 180° en todo tablero ERA5; la derivación
automática del borde SWAN desde ERA5 (`borde_oleaje` → paso Borde del wizard Modelar)
alimenta al modelo con la dirección opuesta — las corridas SWAN con borde ERA5 son
inválidas. Probable origen del error: la convención del **espectro** 2D de ERA5 sí es
oceanográfica «hacia» (ver A2-3) y se extrapoló al escalar `mwd`, que no la usa.

**Nota para el fix:** además de quitar el +180°, hay que invalidar las cachés
parseadas existentes (`era5_serie.nc` y `chunks/*.nc` guardan Dir ya corrompida) —
p. ej. marcar con un atributo de versión de convención y re-parsear/re-descargar si
falta — y ajustar el test de regresión que fija la conversión actual.

### A2-2 · CRÍTICO — ✅ CORREGIDO — Producto cartesiano año×mes×día sin recorte: la serie incluía fechas fuera del rango pedido

> **CORREGIDO (etapa B, 2026-07-06):** nuevo helper `_recortar_a_rango` aplicado en
> `_parsear_serie_nc` y `_parsear_espectro_nc` (ordena por `time`, recorta a
> `[inicio, fin]` con día final completo y lanza `ValueError` claro si el resultado
> queda vacío). Cubre serie, espectro, tramos y el camino de subdivisión. Tests:
> `test_parsear_serie_recorta_al_rango_pedido` y
> `test_parsear_espectro_recorta_al_rango_pedido`; se corrigió además el mock de
> `test_descargar_serie_rangos_distintos_no_comparten_cache`, que generaba fechas
> fuera del rango pedido (cosa que el CDS real no hace). Suite: 144 passed.

`_rango_fechas` (`io_era5.py:406-415`) arma las listas de la petición CDS como
*conjuntos independientes* de años, meses y días del rango, y el CDS devuelve el
**producto cartesiano**. `_particiones_descarga` (`io_era5.py:264-282`) no parte
rangos ≤ 31 días aunque crucen un cambio de mes/año, y ni `_parsear_serie_nc` ni
`descargar_serie` recortan el resultado al rango `[inicio, fin]`.

**Reproducido:** para el rango 2024-12-20 → 2025-01-10 (22 días, un solo tramo), la
petición pide `years=[2024,2025] × months=[01,12] × 22 días`, y `_parsear_serie_nc`
conserva pasos de **2024-01-20 y 2025-12-20** — datos de enero de 2024 y diciembre
de 2025 que el usuario nunca pidió. El tablero resultante mezcla en silencio ~4
períodos distintos; el span salta a ~2 años y activa los productos multi-anuales
(climatología, Gumbel) sobre una serie espuria.

También afecta al camino de subdivisión por «cost limits»
(`_particiones_por_dias`, `io_era5.py:249-261`, corta por número de días y puede
generar tramos que cruzan mes) y al espectro (`_peticion_espectro`,
`io_era5.py:715-724`, usa el mismo `_rango_fechas`).

**Fix directo:** recortar con `ds.sel(time=slice(inicio, fin))` al final de
`_parsear_serie_nc` y `_parsear_espectro_nc` (cubre todos los caminos), y/o cortar
`_particiones_descarga` siempre en límites de mes.

### A2-3 · CRÍTICO — ✅ CORREGIDO — Espectro ERA5: ejes de frecuencia/dirección quedaban como índices 1..30 / 1..24

> **CORREGIDO (etapa B, 2026-07-06):** `_parsear_espectro_nc` detecta ejes de bin
> (`_ejes_como_indices`) y reconstruye las magnitudes físicas
> (f₁=0,03453 Hz·1,1ⁿ⁻¹; dir=7,5°+15°·(n−1)) convirtiendo la dirección de «hacia»
> a procedencia náutica (+180°, eje reordenado). Etiqueta de unidades corregida a
> `m2/Hz/rad` (coherente con la integración en radianes de la partición) y marca
> `ejes="fisicos"` exigida por `_espectro_cache_limpia` para descartar cachés
> antiguas. Tests: `test_parsear_espectro_reconstruye_ejes_de_bin` (verifica
> frecuencias y el corrimiento +180° de la energía) y
> `test_espectro_cache_sin_marca_de_ejes_se_descarta`. Suite: 146 passed.

`_parsear_espectro_nc` (`io_era5.py:755-768`) toma `d2fd` y conserva las coordenadas
tal cual (`coords={k: d2fd.coords[k] for k in d2fd.dims}`), solo renombrando
`frequency→freq`, `direction→dir`. Pero según la documentación ECMWF/CDS, en la
conversión GRIB→NetCDF del espectro 2D **los ejes vienen como números de bin**
(frequency = 1..30, direction = 1..24); las magnitudes físicas hay que reconstruirlas:
`f₁ = 0.03453 Hz, fₙ = fₙ₋₁·1.1` y `dir = 7.5° + 15°·(n−1)` (convención oceanográfica,
«hacia dónde», 90° = hacia el este).

Con datos reales del CDS, entonces:

- `Tp = 1/fp` del producto «Espectro medido S(f)» daría 1/índice (p. ej. Tp = 0,07 s);
- `_pesos` (`particion_espectral.py:22-34`) calcularía `ddir = deg2rad(1°)` en vez de
  15°, y `dfreq = 1` en vez de ~0,003–0,05 Hz → m₀, Hs espectral y la partición
  sea/swell completos carecen de sentido;
- la dirección de cada familia quedaría en índices y además en convención «hacia».

Los tests actuales no lo detectan porque usan espectros sintéticos con ejes físicos.
El propio HANDOFF (2026-06-27) reconoce que el espectro «no se validó con datos
reales». No hay caché de espectro real en `salidas/` para verificación directa, pero
el código citado no contiene ninguna reconstrucción de ejes. Clasificado CRÍTICO
porque invalida todos los productos espectrales ERA5 en cuanto se usen.

Detalle adicional: el atributo de unidades (`io_era5.py:771`) dice `m2/Hz/deg`, pero
tras `10**d2fd` la densidad ERA5 real es **m²·s·rad⁻¹** (por radián); la etiqueta del
panel polar («S(f,θ) [m²/Hz/°]») arrastra el mismo error.

### A2-4 · MEDIO — Credenciales: se exige formato `UID:API-KEY` que el CDS nuevo ya no usa

`_validar_formato_clave_cds` (`io_era5.py:103-114`) exige `UID numérico + ":" + key`,
pero el CDS actual (post-beta 2024) emite **Personal Access Tokens sin UID** (un solo
token). Un usuario nuevo no podría guardar sus credenciales desde la UI (el archivo
del usuario actual es previo y sí funciona). Además `probar_credenciales_cds`
(`io_era5.py:166`) consulta `GET {url}/v2/tasks`, endpoint de la API CDS antigua; en
la API nueva puede responder 404 y el botón «Probar» reportaría error con credenciales
válidas. *Pendiente verificación en línea (no se tocan las credenciales del usuario).*

### A2-5 · MENOR — `_cache_utilizable` es código muerto

`io_era5.py:564-576`: definida y documentada (HANDOFF 2026-06-27/28) pero sin ninguna
llamada en el repo (verificado con búsqueda global; solo aparece su definición y dos
menciones en HANDOFF). Sus reemplazos reales son `_serie_cache_limpia` y
`_espectro_cache_limpia`. Eliminar para evitar confusión.

### A2-6 · MENOR — `descargar_serie` devuelve un Dataset lazy con el archivo de caché abierto

`io_era5.py:652`: el camino de caché retorna `xr.open_dataset(destino)` sin `.load()`
(los demás caminos devuelven datasets en memoria). En Windows el handle abierto puede
bloquear el borrado/reescritura de esa caché (p. ej. desde la gestión de caché ERA5 de
la UI) mientras el Dataset siga vivo. Devolver `ds.load()` + cerrar, como hacen los
tramos (`io_era5.py:370-371`).

### A2-7 · MENOR — `validar_rango_fechas` no rechaza fechas futuras

`io_era5.py:226-240`: un `fin` posterior a la disponibilidad de ERA5 (o directamente
futuro) pasa la validación y termina en un error críptico del CDS tras minutos de
cola. Rechazar `fin > hoy` con mensaje claro costaría dos líneas.

### Observaciones

- La carpeta `ERA5_-35p96_-72p79_..._serie/` contiene solo `chunks/` sin
  `era5_serie.nc` final: descarga interrumpida que el diseño de tramos retomaría
  correctamente; no es un bug.
- A2-1 y A2-3 interactúan con el área 3 (borde SWAN) y el área 1 (partición);
  las referencias cruzadas quedan anotadas en esas secciones.

## Área 3 — Cadena SWAN

Archivos revisados: `swan_builder.py`, `swan_runner.py`, `borde_oleaje.py`,
`geo_malla.py`, `io_batimetria.py`, más los lectores de espectro de `io_swan.py` /
`io_swan_nonst.py` en su cruce con la partición espectral. Estado general: **la
mecánica del runner y el builder es sólida** — los fixes del QA de junio (veredicto
`norm_end`+`.erf` por caso, orden grande→nido, inyección de comandos resuelta con
lista blanca + `shell=False`, inputs verificados justo antes de cada caso) están bien
implementados. `SET NAUTICAL` en el `.swn` es coherente con la convención de
procedencia que entrega `borde_oleaje`. La batimetría usa el signo correcto
(`depth = −elevation`, `io_batimetria.py:136`) y la descarga ERDDAP valida
status/content-type/bytes mágicos.

### A3-1 · MEDIO — Partición sobre espectros SWAN: espectro por-grado integrado con ddir en radianes → Hs de familias ~7,6× menor

Cadena del error:

- `io_swan.leer_espectro_swan` (`io_swan.py:315-317`) e
  `io_swan_nonst.leer_espectro_temporal` (`io_swan_nonst.py:227-230`) entregan
  `Efth` en **m²/Hz/grado** (convención nativa del SPEC2D ASCII de SWAN, declarada
  en el atributo `units`).
- `particion_espectral._pesos` (`particion_espectral.py:33`) devuelve
  `ddir = deg2rad(...)` — integra siempre **en radianes**.
- Camino vivo: el panel «Espectro particionado S(f,θ)» del tablero SWAN
  (`productos_swan.py:129` → `productos_particion.dibujar_polar:77` →
  `particionar`) y `productos_particion.tabla_familias:50`.

Con un espectro por-grado, `m₀ = Σ E·df·ddir` queda multiplicado por π/180 (≈1/57,3)
→ el **Hs de cada familia sale ~7,6× más chico** (√(π/180)) en las etiquetas del
panel polar y en la tabla exportable. El mapa de colores del panel no se ve afectado
(no está integrado), por eso pasa desapercibido. Con el Efth de ERA5 (m²·s·rad⁻¹,
ver A2-3) la integración en radianes sí es consistente: el motor **no** es agnóstico
a la convención como dice su docstring (`particion_espectral.py:6-7`) — la
normalización angular del espectro importa.

**Fix propuesto:** normalizar a una sola convención al leer (p. ej. convertir los
espectros SWAN a m²/Hz/rad multiplicando por 180/π en `io_swan`/`io_swan_nonst`) o
hacer que `_pesos` reciba las unidades del espectro. Los tests actuales usan
espectros sintéticos coherentes con radianes, por eso no lo detectan.

### A3-2 · MENOR — `swan_disponible()` acepta `swan` a secas, pero `correr_caso` solo lanza `swanrun`

`swan_runner.py:27` da por disponible SWAN si existe `swanrun` **o** `swan` en el
PATH, pero `correr_caso` (`swan_runner.py:153`) solo resuelve `swanrun`. Con solo
`swan.exe` instalado, el chequeo pasa y `subprocess.Popen` revienta con
`FileNotFoundError` crudo en lugar del mensaje amable de "instala SWAN". Alinear
ambos (o intentar `swan` como fallback).

### A3-3 · MENOR — `BREAKING CON 1.0 0.29` fijo en todos los `.swn` generados

`swan_builder.py:169` escribe el índice de rotura γ=0,29 sin opción de cambiarlo.
**Verificado** que replica deliberadamente la plantilla del curso de Coronel (todos
los `.swn` de `Python/SWAN_Coronel/` y la presentación entregada documentan
γ=0,29), así que no es un error de transcripción; pero el default de SWAN es
γ=0,73, y con γ=0,29 el modelo limita Hs a ~0,29·h — para dominios distintos de
Coronel puede sub-predecir fuerte el oleaje somero sin que el usuario lo sepa.
Sugerencia: exponerlo como parámetro avanzado (default 0,73) o al menos
documentarlo en la UI del paso Correr.

### Observaciones

- La dirección del borde derivado de ERA5 entra al `.swn` ya invertida por
  **A2-1**: las corridas SWAN con borde ERA5 heredan ese error 180° (el `.swn` y
  `SET NAUTICAL` son correctos; el dato de entrada es el que viene mal).
- `io_swan_nonst.py:232` etiqueta la dirección del espectro como «cartesiana»
  mientras los `.swn` generados usan `SET NAUTICAL`; en las corridas propias del
  builder el SPEC2D saldrá náutico. Sin efecto en la integración (solo etiqueta y
  markers del panel polar), pero conviene unificar al arreglar A3-1.
- `validar_caso` (`swan_builder.py:40-111`) cubre bien INPGRID⊇CGRID, tamaño del
  `.bot` y resolución vs L₀; `validar_caso_anidado` cubre contención, zona UTM y
  celda más fina. Sin hallazgos.

## Área 4 — Puente web y seguridad

Archivos revisados: `api_web.py` (completo), `motor_web.py` (completo), `seguridad.py`
(completo). Estado general: **la seguridad está bien resuelta.** Todos los endpoints
que reciben rutas desde JS pasan por `motor_web._ruta_usuario` →
`seguridad.confina_usuario` (home + `salidas/`); el borrado de caché exige prefijo
`ERA5_*` **y** estar bajo `salidas/` (`motor_web.py:665-675`); los nombres de caso
SWAN usan lista blanca estricta; `validar_url_cds` restringe host y esquema; el
`payload` hacia `evaluate_js` va serializado con `json.dumps` (sin interpolación
cruda). La cola de eventos con re-encolado ante fallo de `evaluate_js` y la
cancelación SWAN con `taskkill /T` están correctas.

### A4-1 · MEDIO — `_error_tarea` reduce los `RuntimeError` informativos a la palabra "RuntimeError"

`api_web.py:63-67`:

```python
def _error_tarea(self, exc):
    if isinstance(exc, ValueError):
        return str(exc)
    return exc.__class__.__name__
```

La sanitización (evitar filtrar trazas) es correcta como idea, pero el propio código
usa `RuntimeError` para todos sus mensajes accionables de cara al usuario:

- SWAN no instalado: «No se encontró 'swanrun' en el PATH…» (`swan_runner.py:203-204`)
- Inputs faltantes de un caso (`swan_runner.py:238-240`)
- Credenciales CDS con el paso a paso completo (`io_era5.py:199-206`)
- Servidor de batimetría caído / respuesta no NetCDF (`io_batimetria.py:189-209`)
- «No se generó ningún video…» (`motor_web.py:561`)

Cuando cualquiera de esos falla dentro de una tarea en hilo (`_run_task`), la UI
recibe `task_done.error = "RuntimeError"` y el usuario queda sin diagnóstico.
Corrección de una línea: tratar `RuntimeError` igual que `ValueError` (ambos son
mensajes propios, no trazas).

### A4-2 · MENOR — Borrar caché ERA5 puede fallar con un error genérico si la serie está abierta

Cadena: `descargar_serie` devuelve un Dataset lazy con el `.nc` abierto (A2-6); en
Windows ese handle bloquea `shutil.rmtree` (`motor_web.py:674`) con
`PermissionError`, que `api_web.eliminar_cache_era5` (`api_web.py:247-251`, solo
captura `ValueError`) no maneja → el fallo llega a la UI sin mensaje útil. Se arregla
solo si se corrige A2-6, pero conviene capturar `OSError` con mensaje «cierra la app
y reintenta».

### A4-3 · MENOR — Las tareas en hilo no-SWAN no se pueden cancelar

`_run_task` (`api_web.py:69-90`) usa un flag global `_busy` sin mecanismo de
cancelación salvo para SWAN (`cancelar_swan`). Una descarga ERA5 colgada en la cola
del CDS (que puede tardar >30 min) bloquea cualquier otra tarea hasta reiniciar la
app. Limitación de diseño conocida; al menos documentarla en la UI o añadir un botón
«Cancelar descarga» que aborte el hilo de forma cooperativa entre tramos.

### Observaciones

- `revision_con_referencia` (`api_web.py:232-239`) captura solo `ValueError` de
  `comparar_series`; un `TypeError` propagaría al puente. Caso improbable (el
  endpoint hermano `comparar_series` sí lo captura); anotado por completitud.
- Los mensajes de log que la UI recibe (`_emit("log", ...)`) contienen contenido
  controlado por el entorno (rutas, respuestas del CDS). Si la UI los inserta con
  `innerHTML` habría un vector de inyección local — se verifica en el área 5.

## Área 5 — UI web

Archivos revisados: `ui/js/core.js` y `ui/js/feedback.js` (completos), `ui/js/views.js`,
`ui/js/wizard-analizar.js`, `ui/js/wizard-modelar.js`, `ui/js/wizard-ver.js` (secciones
de validación, errores y llamadas al puente). Estado general: **bueno**.

Verificaciones que pasaron limpias:

- **Consistencia endpoints JS↔Python:** las 43 llamadas `py("…")` distintas de la UI
  existen todas como métodos de `api_web.Api` (cruzado 1 a 1). En sentido inverso,
  `comparar_series` y `punto_espectral` no se invocan desde la UI (endpoints sin uso
  directo; `revision_con_referencia` cubre el primero).
- **Sin vector de inyección por el log:** los mensajes de `_emit("log", …)` se insertan
  con `pre.textContent` (`core.js:160-167`), y las plantillas HTML usan `T.esc()` en
  los valores dinámicos. Cierra la observación pendiente del área 4.
- **El bloqueo de «Siguiente» no se puentea:** aunque `setBusy(false)` re-habilita
  todos los `.btn.primary` (`core.js:141`), la validación de cada paso se re-ejecuta
  dentro de `next()` (`wizard-modelar.js:570-613`), así que un botón re-habilitado no
  salta ninguna verificación.
- **Textos en español neutro** con tildes correctas; sin voseo ni modismos regionales.
- El timeout deslizante de la descarga ERA5 (`waitTask` con `renewOnActivity`,
  `core.js:96-120`; 30–60 min según días pedidos, `wizard-analizar.js:161-164`)
  funciona como documenta el HANDOFF.

### A5-1 · MENOR — En las vistas fuera de wizard los errores no se muestran en ninguna parte

`feedback.js:7-16`: `T.notify` escribe en `#inline-error` y, si no existe, cae a
`T.setStatus` (`.status-bar`). Pero las vistas Caché ERA5 y Acerca (`views.js:334-342`,
`views.js:358+`) no incluyen **ninguno** de los dos elementos → `T.notify` termina en
`setStatus`, que hace `return` silencioso al no encontrar `.status-bar`. Caso concreto:
si borrar una caché falla (`views.js:348`, p. ej. por A4-2), el usuario no ve mensaje
alguno y la fila simplemente no desaparece. Añadir `<div id="inline-error">` a esas
vistas (la vista Credenciales tiene su propio `#cds-msg` y no la afecta).

### A5-2 · MENOR — Excepciones no controladas del puente se tragan como *unhandled rejection*

`core.js:66-73`: `T.py` no captura rechazos; si un endpoint Python lanza una excepción
que `api_web` no convierte a `{ok: false}` (p. ej. el `PermissionError` de A4-2, o
cualquier bug futuro), la promesa se rechaza dentro de un handler `async` sin
`try/catch` y no se muestra nada. Un envoltorio en `T.py` que capture y llame
`T.notify(...)` cubriría toda la UI de una vez.

### A5-3 · MENOR — Las instrucciones de credenciales fijan el formato antiguo `UID:API-KEY`

`views.js:277` («Copia la API key (`UID:API-KEY`)») y el placeholder de
`views.js:284` documentan el formato del CDS antiguo; si se corrige A2-4 (aceptar el
token PAT del CDS nuevo), estos textos deben actualizarse a la vez.

### Observaciones

- `era5RangoBorde` (`wizard-modelar.js:105-110`) usa como default un rango fijo
  2022-01-01 → 2024-12-31 cuando no hay preferencias guardadas; envejecerá en
  silencio, pero siempre pasa por el chequeo de caché antes de descargar.
- El `setInterval` de `poll_eventos` cada 150 ms (`core.js:129`) corre aunque la API
  no esté disponible (solo relevante al abrir `index.html` en un navegador de
  desarrollo; ruido de consola, sin efecto en la app).

## Área 6 — Empaquetado e instaladores

Archivos revisados: `scripts/bootstrap_windows.ps1`, `scripts/launch_windows.bat`,
`scripts/bootstrap_mac.sh` (lógica de venv), `installer/windows/TableroOleaje.iss`,
`crear_acceso_directo.ps1`; barrido global de rutas personales hardcodeadas
(**ninguna encontrada** — la limpieza del 2026-06-27 fue efectiva). El supuesto
Python 3.11+ es consistente entre `.iss`, bootstrap y guías. Los lanzadores de
desarrollo (zip/repo clonado) están bien: venv local, mensajes de error con
referencia al log, `pause` para que la consola no se cierre.

### A6-1 · CRÍTICO — DIFERIDO A CURSOR — La app instalada con el `.exe` en Program Files no puede funcionar sin elevación

> **DIFERIDO A CURSOR (etapa B, 2026-07-06):** el fix completo tiene dos mitades
> inseparables: (a) instalación per-user en el `.iss` (`PrivilegesRequired=lowest`
> + `DefaultDirName={localappdata}\Tablero de Oleaje`) que exige **recompilar con
> Inno Setup 6 y probar el instalador en una máquina real** (elevación, primer
> arranque, SmartScreen) — imposible de verificar en esta sesión —, y (b) fallback
> de `rutas.py`/`config.py` a `%LOCALAPPDATA%` cuando la carpeta del código no es
> escribible. Hacer solo (b) no desbloquea nada: el bootstrap
> (`bootstrap_windows.ps1:26-29`) falla antes, al crear `salidas\install.log` y
> `.venv` bajo Program Files. Siguiendo la regla de no hacer fixes críticos a
> medias, el hallazgo completo (a+b) queda especificado como Tarea 1 del «Prompt
> para Cursor», con criterio de éxito y pasos de verificación manual.

Cadena del problema (instalador Windows v1.0.0, ya **publicado** en GitHub Releases):

1. `TableroOleaje.iss:27-30` instala en `{autopf}` (`C:\Program Files\Tablero de
   Oleaje`) con `PrivilegesRequired=admin` — la **instalación** va elevada, pero el
   primer arranque (`[Run] postinstall`, `TableroOleaje.iss:57`, que por defecto corre
   `runasoriginaluser`, y los accesos directos de `TableroOleaje.iss:51-54`) corre
   como usuario **normal**.
2. `bootstrap_windows.ps1:26-29` intenta crear `salidas\` y el log **dentro de
   `{app}`**, y `bootstrap_windows.ps1:89-98` crea `.venv` ahí mismo → en Program
   Files un usuario estándar no tiene permiso de escritura → el bootstrap muere en la
   primera línea de escritura y el usuario ve «ERROR durante la preparación».
3. Aunque el bootstrap pasara (usuario administrador con UAC deshabilitado), el
   runtime escribe junto al código: `rutas.py:15` (`RAIZ_SALIDAS = Path(__file__).parent
   / "salidas"`), `config.json` junto al código, `salidas/app_web.log` — todo bajo
   Program Files → descargas ERA5, tableros y preferencias fallarían.

El bootstrap de macOS sí contempla el caso (`bootstrap_mac.sh:77-80`: si el código es
de solo lectura, el venv va a `~/Library/Application Support/`), pero **también** deja
`salidas/` bajo el código, así que el `.app` instalado arrastra el punto 3.

**Impacto:** cualquier tercero que instale desde el `.exe`/`.dmg` publicado tiene la
app rota de fábrica; el modo zip/repo (el que usa el usuario y su cliente actual) no
se ve afectado. **Fix correcto (dos frentes):** (a) instalar per-user
(`PrivilegesRequired=lowest` + `DefaultDirName={localappdata}\…`), y (b) que
`rutas.py`/`config.py` caigan a `%LOCALAPPDATA%\Tablero de Oleaje\` cuando la carpeta
del código no sea escribible (mismo patrón que el bootstrap de Mac). La parte (b) es
testeable con pytest; la (a) requiere recompilar y probar el instalador en una máquina
real, que excede esta sesión.

### A6-2 · MENOR — El binario del instalador está commiteado en el repo público

`installer/windows/Tablero_Oleaje_Setup_1.0.0.exe` vive en el árbol de git. Los
releases van en GitHub Releases (ya se hace); el `.exe` en el repo solo infla clones.
Añadir `installer/windows/*.exe` al `.gitignore` y quitarlo del índice.

### Observaciones

- `TableroOleaje.iss:48` excluye `*.md` del paquete (README/HANDOFF/DISEÑO fuera de
  la instalación) — deliberado y razonable para el usuario final.
- `PythonOk()` (`TableroOleaje.iss:66-113`) permite «continuar de todas formas» sin
  Python; el primer arranque falla con mensaje y guía. Diseño aceptable.
- `empaquetar_entrega.ps1` (zip de entrega) no se revisó línea a línea; el HANDOFF
  documenta sus exclusiones y el flujo zip está verificado por el uso real.

## Área 7 — Tests

**Ejecución (2026-07-06, este equipo):**

- `pytest test_regresion.py test_asistente.py test_nesting.py -q` →
  **141 passed, 8 skipped, 11,2 s** (sin el flake tkinter documentado en HANDOFF).
- `pytest test_motor_web.py -q` → **3 passed, 2,3 s**.
- Los 8 skips son los tests con datos reales (corridas `SWAN_Coronel` y `.mat` de
  Talcahuano) porque `TABLERO_DATOS_SWAN` / `TABLERO_DATOS_OLEAJE` no están
  configuradas.

**Cobertura real:** fuerte en parsers/IO (`.mat`, CGRID, SPEC2D, zip CDS, caché),
`seguridad`, `swan_builder`/`swan_runner` (incl. el veredicto `norm_end`/`.erf` y el
orden de nesting) y partición espectral con espectros sintéticos. Débil o nula en:
funciones de dibujo (`_dib_*` no se ejercen), `api_web` (`_run_task`, `_error_tarea`),
UI JS (nada, asumido), y — lo más relevante — **la estructura real de los datos del
CDS**: los tests de espectro usan ejes físicos sintéticos, por eso los tres CRÍTICOS
de ERA5 conviven con una suite 100 % verde.

### A7-1 · MEDIO — Un test de regresión fija el comportamiento erróneo de A2-1

`test_regresion.py:465-470` (`test_parsear_serie_convierte_mwd_a_procedencia`)
asserta `mwd=225° → Dir=45°` bajo la premisa (falsa) de que «mwd ERA5 es
propagación». Es la contraparte en tests del hallazgo A2-1: cualquier intento de
corregir la dirección rompe este test, y el test da respaldo aparente al bug. El fix
de A2-1 debe actualizarlo (Dir debe quedar en 225°) en el mismo commit.

### A7-2 · MENOR — `test_motor_web.py` quedó fuera del comando oficial de la suite

`CLAUDE.md` y la regla de trabajo del HANDOFF definen la suite como
`test_regresion.py test_asistente.py test_nesting.py`; los 3 tests de
`test_motor_web.py` (verdes, 2 s) no los corre nadie por defecto. Incluirlo en el
comando oficial.

### A7-3 · MENOR — Los tests con datos reales nunca corren en este equipo pese a que los datos existen

Los 8 tests saltados validan los valores de regresión más valiosos (Hs de borde
TR100/TR10/reinante, `nt=168`, `peak=118` del NonSt). Los datos están en este equipo
(`Proyectos\Python\SWAN_Coronel\`, `Tarea 3 Costas`), pero al no exportar
`TABLERO_DATOS_SWAN`/`TABLERO_DATOS_OLEAJE` se saltan en silencio. Sugerencia:
setearlas en `.claude/settings` del proyecto o documentar el export en el flujo de
trabajo para que la regresión con datos reales corra al menos antes de cada entrega.

---

## Hallazgos corregidos (etapa B)

| Hallazgo | Fix | Commit | Suite |
|----------|-----|--------|-------|
| A2-1 (+A7-1) — Dir ERA5 invertida 180° | Sin `+180°`; marca `dir_convencion` invalida cachés antiguas; test del bug reemplazado + test de invalidación | `e19abd6` | 142 passed, 8 skipped |
| A2-2 — Fechas fuera del rango pedido (producto cartesiano CDS) | `_recortar_a_rango` en ambos parsers + guard de serie vacía; 2 tests nuevos y mock corregido | `f0fef4e` | 144 passed, 8 skipped |
| A2-3 — Espectro d2fd con ejes índice | Reconstrucción de ejes físicos + dirección a procedencia + unidades `m2/Hz/rad` + marca `ejes` invalida cachés; 2 tests nuevos | `38ac6af` | 146 passed, 8 skipped |
| A6-1 — Instalador Windows en Program Files | **DIFERIDO A CURSOR**: requiere recompilar y probar el `.exe` en máquina real; el fallback de runtime solo no desbloquea el primer arranque | — | Tarea 1 del Prompt para Cursor |

## Prompt para Cursor

> Copiar desde aquí hasta el final del documento y pegarlo como instrucción a Cursor.

---

Trabaja en el repo del **Tablero de Oleaje** (raíz: la carpeta que contiene `app_web.py`). Vas a cerrar los hallazgos pendientes de la auditoría `docs/AUDITORIA_2026-07.md`. Los 3 críticos de ERA5 ya están corregidos (commits `e19abd6`, `f0fef4e`, `38ac6af`) — **no toques esas correcciones ni reintroduzcas el `+180°` en la dirección ERA5**.

**REGLAS DURAS (aplican a TODAS las tareas, sin excepción):**

1. Antes de empezar, lee `HANDOFF.md` (bloque inicial + registro de cambios) y `docs/AUDITORIA_2026-07.md` (resumen ejecutivo + la sección del hallazgo que estés tocando).
2. Después de CADA tarea corre: `python -m pytest test_regresion.py test_asistente.py test_nesting.py test_motor_web.py -q`. Si algo queda en rojo, arréglalo antes de pasar a la siguiente tarea. Si `test_asistente.py` falla con `TclError` (flake de tkinter documentado en HANDOFF), re-corre una vez antes de asumir que rompiste algo.
3. Un commit por tarea, mensaje en español, formato `fix(...): descripción` o `docs(...)`/`chore(...)` según corresponda, mencionando el ID del hallazgo (p. ej. "A1-1").
4. **NO hagas `git push`** bajo ninguna circunstancia.
5. Al terminar todas las tareas: añade UNA entrada arriba del registro de `HANDOFF.md` (formato del propio archivo, agente "Cursor") listando las tareas cerradas, y marca cada hallazgo como `✅ CORREGIDO (Cursor)` en su sección de `docs/AUDITORIA_2026-07.md`.
6. Si una tarea no la puedes verificar (p. ej. compilar el instalador), haz la parte de código, deja el estado claro en el HANDOFF («pendiente prueba manual del usuario») y sigue con la siguiente. No inventes verificaciones.
7. Ejecuta las tareas EN ESTE ORDEN. No agrupes commits.

---

**TAREA 1 — A6-1 (CRÍTICO diferido): instalador Windows per-user + escrituras fuera de la carpeta del código.**

Contexto: instalado en `C:\Program Files\` el primer arranque corre sin elevación y no puede crear `.venv` ni `salidas\` (detalle en la sección A6-1 de la auditoría).

1. En `installer/windows/TableroOleaje.iss`: cambia `PrivilegesRequired=admin` → `PrivilegesRequired=lowest` y `DefaultDirName={autopf}\Tablero de Oleaje` → `DefaultDirName={localappdata}\Tablero de Oleaje` (líneas 27-30). Sube `AppVersion` a `1.0.1`.
2. En `rutas.py` (líneas 14-15): si `Path(__file__).parent` NO es escribible (haz la prueba creando y borrando un archivo temporal, en un `try/except OSError`), usa `Path(os.environ["LOCALAPPDATA"]) / "Tablero de Oleaje" / "salidas"` como `RAIZ_SALIDAS` (en macOS/Linux: `~/.local/share/Tablero de Oleaje/salidas`). Extrae la lógica a una función `_raiz_salidas()` para poder testearla.
3. En `config.py`: aplica el mismo fallback a la ruta de `config.json` (misma función o una equivalente).
4. En `scripts/bootstrap_windows.ps1` (líneas 26-30): escribe `install.log` en `$env:LOCALAPPDATA\Tablero de Oleaje\` si la carpeta del proyecto no es escribible (con instalación per-user en `{localappdata}` sí lo será; el fallback es defensa extra).
5. Test nuevo en `test_regresion.py`: `_raiz_salidas()` con una carpeta de código simulada no-escribible (monkeypatch de la función de chequeo) devuelve la ruta bajo LOCALAPPDATA; con carpeta escribible devuelve `<código>/salidas`.
6. **Criterio de éxito:** suite en verde + los cambios del `.iss` compilan mentalmente contra la doc de Inno Setup (no puedes compilar; deja nota en HANDOFF: «recompilar `empaquetar_instalador.bat` y probar el Setup en una máquina sin permisos de admin antes de re-publicar el Release»).

**TAREA 2 — A1-1 (MEDIO): percentiles de excedencia con NaN.**

En `productos.py:139-140` (`_calc_excedencia`): cambia `np.percentile(crudo, p)` por `np.nanpercentile(crudo, p)`. Test: serie de 100 puntos con 1 NaN → los tres percentiles son finitos y coherentes (P50 < P90 < P99). **Criterio:** test nuevo en verde.

**TAREA 3 — A1-2 (MEDIO): ordenar `time` al construir el Dataset.**

En `io_oleaje.py`, función `construir_dataset` (líneas 70-94): tras crear `ds`, aplica `ds = ds.sortby("time")` si la coordenada no es monótona creciente. En `validacion.py`, `_chequeo_tiempo` (líneas 51-64): si `t` no es monótono, repórtalo en el detalle. Test: DataFrame con filas barajadas → `productos._span_dias` devuelve el span real (no uno menor). **Criterio:** test nuevo en verde; los tests existentes de `io_oleaje` no cambian.

**TAREA 4 — A2-4 + A5-3 (MEDIO): credenciales del CDS nuevo (PAT sin UID).**

1. En `io_era5.py`, `_validar_formato_clave_cds`: acepta también claves SIN `:` (Personal Access Token del CDS actual, un solo token no vacío); conserva la validación `UID:KEY` para claves con `:`. Ajusta `enmascarar_clave_cds` para mostrar `…últimos4` cuando no hay UID.
2. En `probar_credenciales_cds`: investiga en la documentación del CDS (https://cds.climate.copernicus.eu/how-to-api) el endpoint de verificación vigente; si `GET {url}/v2/tasks` ya no existe, usa el que documenten (con el mismo header `PRIVATE-TOKEN`). Si no encuentras documentación clara, deja el endpoint actual pero trata el 404 con el mensaje «No se pudo verificar (el CDS cambió su API); la clave se guardó igual».
3. En `ui/js/views.js:277` y `:284`: actualiza los textos («Copia tu Personal Access Token (o el formato antiguo UID:API-KEY)»).
4. Tests: `_validar_formato_clave_cds` acepta `"abcdef123456"` y `"12345:abcdef"`, rechaza `""` y `"  "`. **Criterio:** tests nuevos en verde; guardar credenciales con PAT no lanza.

**TAREA 5 — A3-1 (MEDIO): unidades de la partición espectral con espectros SWAN.**

Contexto: `particion_espectral._pesos` (línea 33) integra con `ddir` en radianes; los espectros SWAN se leen en m²/Hz/**grado** → Hs de familias ~7,6× menor en el panel polar del tablero SWAN.

1. En `io_swan.py` (`leer_espectro_swan`, cerca de la línea 313: `densidad = matriz * factor`) y en `io_swan_nonst.py` (`leer_espectro_temporal`, cerca de la línea 213: `dens = mat * factor`): multiplica la densidad por `180.0 / np.pi` para convertirla a m²/Hz/rad, y cambia el atributo `units` de `"m2/Hz/deg"` a `"m2/Hz/rad"` (líneas 317 y 230 respectivamente).
2. En `productos_particion.py:75`: cambia la etiqueta del colorbar a `S(f,θ) [m²/Hz/rad]`.
3. Test nuevo: espectro sintético constante `E₀` por grado sobre 24 direcciones de 15° y una banda de frecuencia conocida → tras leer (simular la conversión) y particionar, `Hs = 4·√m₀` coincide con la integral analítica `m₀ = E₀·Δf·360` (tolerancia 1 %).
4. **Cuidado:** los tests existentes de partición usan espectros ya en radianes y NO deben cambiar; solo cambia la conversión al LEER espectros SWAN.
5. **Criterio:** test nuevo en verde y `test_regresion.py` completo en verde (si un test existente fijaba valores del espectro SWAN leído, actualiza su valor esperado multiplicando por 180/π y dilo en el commit).

**TAREA 6 — A4-1 (MEDIO): no ocultar los mensajes de `RuntimeError`.**

En `api_web.py:63-67` (`_error_tarea`): trata `RuntimeError` igual que `ValueError` (devuelve `str(exc)`); el resto sigue devolviendo solo el nombre de clase. Test en `test_motor_web.py`: `Api()._error_tarea(RuntimeError("no hay swan"))` devuelve `"no hay swan"`; `_error_tarea(KeyError("x"))` devuelve `"KeyError"`. **Criterio:** tests en verde.

**TAREA 7 — MENORES del área 1 (un solo commit).**

1. A1-3, `productos.py:276-282` (`_dib_rosa`): normaliza por el número de registros con Hs **y** Dir finitos (`np.isfinite(hs) & np.isfinite(dir)`).
2. A1-4, `tablero_oleaje.py:105`: reemplaza la comparación por `etiqueta = destino.name` (elimina la llamada a `rutas.carpeta_salida` que creaba carpetas vacías).
3. A1-5, `productos.py:461-465` (`evaluar`): al capturar la excepción usa `faltan = [str(e) or p.get("motivo_inaplicable", ...)]`.
4. A1-6, `productos.py:463`: añade `KeyError` a la tupla del `except`.
5. A1-7, `productos.py:298-301` (`_calc_jonswap`): valida también `np.isfinite(hs) and hs > 0` con `ValueError`.
6. **Criterio:** suite en verde; un test nuevo para A1-3 (rosa con Dir NaN suma ≈100 %).

**TAREA 8 — MENORES del área 2 (un solo commit).**

1. A2-5: elimina la función muerta `_cache_utilizable` de `io_era5.py` (sin llamadas en el repo; verifica con búsqueda global antes de borrar).
2. A2-6: en `descargar_serie`, camino de caché (busca `return xr.open_dataset(destino)`): cambia a abrir, `.load()`, cerrar y devolver el Dataset en memoria (mismo patrón que `_obtener_tramo_serie`). Igual en `descargar_espectro`.
3. A2-7: en `validar_rango_fechas`, rechaza `fin` posterior a la fecha actual con `ValueError` («ERA5 no tiene datos futuros»).
4. **Criterio:** suite en verde; test para A2-7.

**TAREA 9 — MENORES del área 3 (un solo commit).**

1. A3-2, `swan_runner.py:27` y `:153`: si no hay `swanrun` pero sí `swan`, `correr_caso` debe fallar con `RuntimeError` claro («se encontró swan.exe pero falta swanrun; agrega el script swanrun al PATH») en vez del `FileNotFoundError` de `Popen`.
2. A3-3, `swan_builder.py:169`: extrae γ a un parámetro `gamma_rotura=0.29` de `construir_swn` (default actual para no cambiar corridas existentes) y añade un comentario: «0,29 replica la plantilla del curso Coronel; el default de SWAN es 0,73».
3. **Criterio:** suite en verde (el round-trip builder→runner no cambia con el default).

**TAREA 10 — MENORES del área 4 y 5 (un solo commit).**

1. A4-2, `api_web.py:247-251` (`eliminar_cache_era5`): captura también `OSError` y devuelve `{"ok": False, "error": "No se pudo borrar (archivo en uso); cierra la app y reintenta."}`.
2. A5-1, `ui/js/views.js` (`renderCache` y `renderAcerca`): añade `<div class="inline-error hidden" id="inline-error"></div>` bajo el título de cada vista.
3. A5-2, `ui/js/core.js:66-73` (`T.py`): envuelve la llamada en `try/catch`; en el catch haz `console.error` y `T.notify("Error interno: " + (e?.message || e))`, y devuelve `null`.
4. A4-3: no implementes cancelación nueva; solo añade en la ayuda del paso Origen (`ui/js/core.js`, texto del wizard analizar) la frase «La descarga no se puede cancelar; si se cuelga, cierra y reabre la app.»
5. **Criterio:** suite en verde (los cambios JS no tienen tests; verifica a mano que `python app_web.py` abre y las vistas Caché/Acerca cargan sin errores de consola).

**TAREA 11 — MENORES de áreas 6 y 7 (un solo commit).**

1. A6-2: añade `installer/windows/*.exe` a `.gitignore` y ejecuta `git rm --cached "installer/windows/Tablero_Oleaje_Setup_1.0.0.exe"` (el archivo queda en disco, fuera del índice).
2. A7-2: en `CLAUDE.md` (tabla «Punteros rápidos») y en la regla de trabajo del HANDOFF, actualiza el comando de tests a `pytest test_regresion.py test_asistente.py test_nesting.py test_motor_web.py -q`.
3. A7-3: en `AGENTS.md`, documenta que en el equipo del usuario se pueden exportar `TABLERO_DATOS_SWAN` → `...\Proyectos\Python\SWAN_Coronel` y `TABLERO_DATOS_OLEAJE` → ruta del `.mat` de Talcahuano para correr los 8 tests con datos reales antes de una entrega.
4. **Criterio:** `git status` limpio tras el commit; suite en verde.

**CIERRE:** entrada en `HANDOFF.md` + marcas `✅ CORREGIDO (Cursor)` en `docs/AUDITORIA_2026-07.md` + commit final `docs(handoff): cierra hallazgos MEDIO/MENOR de la auditoría 2026-07`. Sin push.
