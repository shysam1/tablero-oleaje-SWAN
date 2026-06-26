# Diseño — Malla por lat/lon (calcular UTM automáticamente)

Fecha: 2026-06-26
Herramienta: Tablero de Oleaje
Estado: aprobado, pendiente de plan de implementación

## Objetivo

Permitir definir la malla de cómputo de un caso SWAN por **lat/lon** (centro +
tamaño + resolución), y que la app **calcule sola la zona UTM y los campos UTM**
del formulario. Elimina el paso manual de averiguar el origen UTM (lo último
manual del flujo "Armar y correr"). No reemplaza la entrada UTM: la rellena.

## Contexto y restricciones

- El formulario "Armar y correr" (`gui_swan._pestana_nuevo`) tiene la malla en
  UTM: `self.v["xpc"]`, `["ypc"]` (origen, esquina suroeste), `["xlenc"]`,
  `["ylenc"]` (extensión m), `["mxc"]`, `["myc"]` (celdas), `["zona_utm"]`.
- Ya existe `io_batimetria.epsg_utm("19S") -> 32719` y `pyproj` 3.7.2.
- La entrada UTM se mantiene (la usan las corridas anidadas y el ajuste fino):
  esta feature agrega un botón que **escribe** esos campos, igual que las dos
  vías del borde escriben Hs/Tp/Dir.
- SWAN necesita ≥ 2 celdas por lado.

## Arquitectura

Un motor puro nuevo + un botón con diálogo en la GUI.

```
geo_malla.py                malla_desde_latlon(...) -> dict de campos UTM
gui_swan (Armar y correr)   botón "Definir por lat/lon…" + diálogo → rellena campos
```

### 1. `geo_malla.py` — motor

`malla_desde_latlon(lat_centro, lon_centro, ancho_km, alto_km, celda_m) -> dict`:

1. Valida rangos: `−90 ≤ lat ≤ 90`, `−180 ≤ lon ≤ 180`, `ancho_km > 0`,
   `alto_km > 0`, `celda_m > 0`; y que resulten ≥ 2 celdas por lado.
2. **Deriva la zona UTM** del lon central: `zona = int((lon+180)//6)+1`,
   hemisferio `"S"` si `lat < 0` si no `"N"`; `zona_utm = f"{zona}{hemis}"`.
3. EPSG con `io_batimetria.epsg_utm(zona_utm)`; proyecta el centro (lon, lat) →
   (x_c, y_c) UTM con `pyproj.Transformer` (always_xy).
4. `xlenc = ancho_km·1000`, `ylenc = alto_km·1000`; `xpc = x_c − xlenc/2`,
   `ypc = y_c − ylenc/2` (esquina suroeste); `mxc = round(xlenc/celda_m)`,
   `myc = round(ylenc/celda_m)`.
5. Devuelve `{xpc, ypc, xlenc, ylenc, mxc, myc, zona_utm}` (mismos nombres que
   `self.v`). Función pura, sin estado.

### 2. GUI — formulario "Armar y correr"

Botón **"Definir por lat/lon…"** en la sección de malla → diálogo modal
(`dialogo_latlon`, función de módulo en `gui_swan`) con 5 campos: lat centro, lon
centro, ancho (km), alto (km), tamaño de celda (m). Al aceptar:
1. Llama `geo_malla.malla_desde_latlon`.
2. Escribe cada valor en `self.v[...]` (`xpc/ypc` redondeados a metros enteros,
   `xlenc/ylenc/mxc/myc` enteros, `zona_utm` texto).
3. Registra en el log la zona UTM derivada y el nº de celdas resultante.
Errores de validación → `messagebox` sin cerrar el formulario.

### 3. Encaje

Cierra el flujo de modelado sin UTM manual: **definir zona por lat/lon → "Generar
batimetría" → borde desde ERA5 → correr**. La entrada lat/lon queda lista para que
el asistente guiado (futuro sub-proyecto C) la reutilice.

## Manejo de errores

- lat/lon fuera de rango, ancho/alto/celda ≤ 0, o < 2 celdas por lado →
  `ValueError` con mensaje claro; la GUI lo muestra con `messagebox`.

## Tests (sin GUI ni red)

- `malla_desde_latlon` para Reñaca (`lat −32.97, lon −71.55, 8 km × 8 km, celda
  100 m`): `zona_utm == "19S"`, `mxc == myc == 80`, `xlenc == ylenc == 8000`.
- **Round-trip**: reproyectar el centro de la malla calculada
  (`xpc+xlenc/2, ypc+ylenc/2`) de vuelta a lat/lon (EPSG → 4326) ≈ centro original
  (tolerancia ~1e-3°).
- Zona por longitud: `lon −73` (Coronel) → `"18S"`; `lon −71.55` → `"19S"`.
- Validación: `celda_m` mayor que la extensión (→ < 2 celdas) lanza `ValueError`;
  `lat = 200` lanza `ValueError`.

## Fuera de alcance (YAGNI)

- Definir el origen del **dominio anidado** por lat/lon (sigue en UTM): el caso
  lat/lon cubre el dominio principal.
- Reemplazar/ocultar los campos UTM del formulario: se mantienen y se rellenan.
- Mallas rotadas (`alpc ≠ 0`): se asume malla alineada N-S/E-O.
