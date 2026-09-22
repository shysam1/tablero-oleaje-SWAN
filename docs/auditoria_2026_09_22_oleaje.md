# Auditoría del motor de oleaje y ERA5 — 22 de septiembre de 2026

Alcance: ingesta MAT/CSV/NetCDF, productos estadísticos, borde derivado, descarga y caché ERA5, partición y paneles espectrales. Esta revisión acompaña la auditoría de distribución y UI. No certifica resultados de diseño ni sustituye validación con observaciones.

## Hallazgos corregidos

| Prioridad | Hallazgo reproducible y efecto | Corrección y ubicación |
|---|---|---|
| P1 | Un solo NaN en Hs/Tp llegaba a `hist2d`, que lanzaba `ValueError: autodetected range of [nan, nan] is not finite`. El tablero completo abortaba al dibujar. | `productos.py:_calc_hstp` filtra pares finitos y omite el panel si no queda ninguno. Prueba completa de exportación PNG. |
| P1 | Una serie de 1.100 días con Hs constante provocaba `OverflowError` dentro de `gumbel_r.fit`. Los años completamente NaN también entraban al ajuste. | `productos.py:ajustar_gumbel` exige máximos anuales finitos y distintos; el tablero omite el ajuste inválido. `borde_oleaje.py` usa el mismo ajuste. |
| P1 | La petición espectral usaba `reanalysis-era5-single-levels` y `variable=2d_wave_spectra`, aunque ese producto no está en el catálogo de disco. | `io_era5.py:_DATASET_ESPECTRO/_peticion_espectro` usan `reanalysis-era5-complete`, sintaxis MARS, parámetro 140251, 30 frecuencias, 24 direcciones y grid explícita. Contrato contrastado con ECMWF; pendiente descarga autenticada real. |
| P1 | NetCDF se abría/escribía desde los trabajadores ERA5 sin exclusión compartida. El fallo depende del build, pero netcdf-c no garantiza seguridad entre hilos. | `io_oleaje.py:NETCDF_LOCK/leer_netcdf` y `io_era5.py` serializan apertura, carga, cierre y escritura del camino ERA5. Las peticiones HTTP conservan paralelismo. Prueba instrumentada confirma máximo un escritor. |
| P2 | Una caché sin viento se reutilizaba aunque el usuario luego pidiera incluir viento. | `_serie_cache_limpia(..., incluir_viento=True)` exige `u10/v10`; se aplica en caché final y tramos. El puente web debe propagar la misma opción. |
| P2 | `astype(int)` truncaba fechas: año 2024.9 y hora 0.9 se convertían silenciosamente a 2024-01-01 00:00. | `io_oleaje.py:_columna_tiempo` exige componentes enteros, fechas válidas y hora 0–23. |
| P2 | NetCDF arbitrarios pasaban directo al motor: series vacías, tiempo numérico o campos espaciales fallaban después o se interpretaban mal. Archivos abiertos conservaban handles hasta cierre explícito. | `validar_estructura` exige serie puntual, fechas reales y variables numéricas conocidas; ordena tiempo. `cargar` devuelve datos ya cargados y archivo cerrado. No convierte unidades desconocidas. |
| P2 | Dir de 359° y 1° se resumía con media 180° y desviación 179°. | `productos.py:_calc_resumen` usa estadísticos circulares y lo indica en el panel. Rosa normaliza 360° a 0°. |
| P2 | El parser espectral buscaba solo `d2fd`, conservaba dimensiones en cualquier orden y sumaba 180° únicamente si las direcciones eran índices. Un archivo con direcciones físicas quedaba en propagación. | `_parsear_espectro_nc` acepta `2dfd/d2fd`, ordena `(time,freq,dir)`, transforma todas las direcciones de origen ERA5 y etiqueta procedencia. Las cachés espectrales sin nueva marca se invalidan. |
| P2 | Tp de una familia se obtenía del máximo de `S(f)·df`, sesgándolo hacia bandas anchas. Con f=[0.05,0.1,0.2] y S=[1,2,1.8] podía elegir 5 s en lugar de 10 s. | `particion_espectral.py:_parametros` busca el máximo de densidad integrada en dirección. Se valida forma y frecuencias; infinito/densidad negativa se rechazan. |
| P2 | Un Hs infinito podía seleccionarse como máximo para el borde. | `borde_oleaje.py` selecciona Hs finitos y no negativos. |
| P2 | El panel polar no fijaba orientación y podía representar procedencia náutica con 0° al este y sentido antihorario. La suma de las cuatro familias retenidas se llamaba Hs total aunque se omiten familias y celdas por umbral. | `productos_particion.py` respeta `dir.attrs['convencion']` y rotula Hs de familias representadas. Las curvas se identifican por orden de energía en cada instante; no se presenta seguimiento físico entre tiempos. |
| P2 | Fallar durante la escritura atómica podía dejar `.part` y había un único nombre temporal fijo. | `_escribir_nc_atomico` usa un temporal único en la misma carpeta y lo elimina en `finally`, conservando el destino previo si falla la escritura. |

## Comprobación realizada

Entorno real de esta revisión: Windows, Python 3.13.13, NumPy 2.4.6, xarray 2026.4.0, netCDF4 1.7.4.

- Antes de corregir, se reprodujeron el fallo NaN del histograma, truncamiento de fechas, media direccional errónea y `OverflowError` de Gumbel constante.
- `python -m pytest test_regresion.py -q --basetemp C:\Users\123ja\pytest-tablero-oleaje-regresion`: **125 passed, 8 skipped**. Se incluyeron ambos tests ERA5 paralelos que la guía anterior deseleccionaba.
- `python -m pytest test_auditoria_oleaje.py -q --basetemp C:\Users\123ja\pytest-tablero-oleaje-nuevos`: **21 passed**. Incluye exportación completa PNG, pares incompletos, Gumbel, circularidad, fechas, estructura y handles NetCDF, caché con viento, MARS, parser transpuesto, Tp, bloqueo y fallo de escritura.
- Se inspeccionó visualmente el PNG generado por `test_tablero_con_nan_en_hs_tp_se_exporta`: seis paneles, ejes/unidades y omisiones legibles. Es una muestra sintética de tres días para reproducir el error, no un estudio de oleaje.
- Se observó una advertencia del entorno `numpy.ndarray size changed` al importar netCDF4; las pruebas pasan, pero conviene verificar con las dependencias del instalador limpio. La advertencia de `argmax` de xarray es de deprecación y no cambió resultados.

Los ocho skips de regresión requieren datos reales señalados por variables `TABLERO_DATOS_*`; no deben contarse como validación científica. No se inspeccionaron ni usaron credenciales, no hubo peticiones de datos a CDS, no se modificaron datasets originales y no se crearon commits.

## Pendientes y mejoras recomendadas

1. **P1 — Validación externa antes de distribuir.** Ejecutar una descarga breve real de serie, luego añadir viento sobre su caché, y descargar un espectro MARS con cuenta autorizada. Comprobar licencia, respuestas ZIP/NetCDF, fechas, coordenada seleccionada, dirección y energía contra una referencia. La nueva petición se probó con dobles y fuentes oficiales; no se afirma éxito ante el servicio real.
2. **P2 — Viento y olas en peticiones separadas.** La documentación CDS vigente recomienda no mezclar campos atmosféricos y de olas en una petición NetCDF por sus grillas distintas. El parser actual maneja ZIP por stream, pero la petición de serie todavía los combina si se pide viento. Dividir esas peticiones y probar la unión real es el siguiente cambio de integración.
3. **P2 — Calidad y cobertura de extremos.** Dos años de calendario y 730 días de span no garantizan años completos, independencia ni suficiencia para extrapolar a 50/100 años. Añadir cobertura por año, exclusión explícita de años incompletos, incertidumbre y criterios metodológicos acordados. Tampoco se ha validado físicamente heredar Tp/Dir del máximo observado para un Hs de retorno.
4. **P2 — Contrato de unidades y calendario.** MAT continúa esperando `DataTarea` de siete columnas; CSV usa columnas canónicas y coma. La nueva comprobación de estructura no reconoce automáticamente unidades diferentes, calendarios CF no gregorianos ni CSV regional con punto y coma. Implementar mapeo de columnas/unidades visible y un archivo de ejemplo en el flujo de importación.
5. **P2 — Revisión científica de la partición.** La separación implementada es watershed con rotación de valle; no equivale a una reproducción validada completa de Hanson–Phillips. Revisar criterio de edad de ola, umbral, mallas direccionales irregulares, varios windseas y seguimiento temporal. La integración angular asume paso uniforme. Ninguna corrección de esta auditoría certifica las familias ante observaciones.
6. **P2 — Grandes series y puntos costeros.** La carga NetCDF es en memoria y `particionar_serie` retiene máscaras de todos los pasos. Medir límites reales, procesar por bloques y mostrar el nodo efectivo, cobertura NaN y distancia a la coordenada solicitada. La selección actual es el vecino más cercano, que puede ser tierra.
7. **P2 — Temporales y caché entre procesos.** El bloqueo añadido protege el proceso Python actual, no dos instancias independientes. La escritura final usa temporales únicos, pero descargas crudas de la misma clave aún comparten nombre. Evaluar bloqueo por destino o caché transaccional si se permiten varias instancias.
8. **Resuelto — Pruebas portables de concurrencia.** Los dos mocks históricos de `retrieve` escribían NetCDF desde varios hilos, fuera del bloqueo del camino real HTTP. Ahora construyen los NetCDF y leen sus bytes antes de lanzar trabajadores; cada `retrieve` simulado únicamente escribe esos bytes. Se conservan los chequeos de concatenación y exactamente dos peticiones simultáneas. Ambos tests se ejecutan sin deselección; la protección del I/O real se comprueba por separado en `test_io_netcdf_concurrente_se_serializa`.
9. **P3 — Legibilidad y trazabilidad.** En series de pocos días las etiquetas de fecha se repiten al ocultar horas. Añadir número de datos válidos por variable al resumen y una tabla/exportación de calidad; los límites físicos actualmente se reportan pero no filtran todas las estadísticas de manera uniforme.

## Fuentes primarias contrastadas

- [Unidata, API netCDF4: advertencia de seguridad entre hilos](https://unidata.github.io/netcdf4-python/). La afirmación previa de que un segfault era únicamente un problema de una VM no basta para considerar portable la aplicación.
- [ECMWF, documentación ERA5 vigente](https://confluence.ecmwf.int/spaces/CKB/pages/76414402/ERA5%2Bdata%2Bdocumentation): acceso espectral por MARS; ejes de 30 frecuencias/24 direcciones; log10, procedencia/propagación y unidades.
- [ECMWF, descarga ERA5 desde CDS vigente](https://confluence.ecmwf.int/spaces/CKB/pages/129135000/How%2Bto%2Bdownload%2BERA5%2Bfrom%2Bthe%2BClimate%2BData%2BStore%2BCDS): sintaxis MARS, rejilla regular para conversión NetCDF y separación de grillas atmosférica y de olas.
- [ECMWF, espectros bidimensionales](https://www.ecmwf.int/en/forecasts/documentation-and-support/2d-wave-spectra): convención de propagación y selección de todas las bandas.
- [SciPy, media circular](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.circmean.html): estadística angular usada en el resumen.
