# Auditoría SWAN, batimetría, geometría y exportación

Fecha: 22-09-2026. Alcance: `swan_builder.py`, `swan_runner.py`, `io_swan.py`,
`io_swan_nonst.py`, `io_batimetria.py`, `geo_malla.py`, `productos_swan.py`,
`tablero_swan.py`, `video_swan.py`. Pruebas nuevas en `test_auditoria_swan.py`.

Se leyó AGENTS/CLAUDE/HANDOFF antes de editar. Los datos históricos de Coronel se
usaron exclusivamente para lectura; ninguna corrida se ejecutó sobre originales.
No se hicieron commits ni publicación. Las comprobaciones realizadas en este equipo
no equivalen a una instalación certificada en otro computador.

## Errores corregidos

| ID / prioridad | Evidencia y efecto previo | Corrección y verificación |
|---|---|---|
| S01 / P1 | `escribir_par_anidado` emitía `Hs.txt`, `Tp.txt` y `Dir.txt` tanto para el padre como para el nido. La segunda corrida sobrescribía la primera. | Prefijos por caso; rechazo de nombres de caso iguales y detección de colisiones antiguas antes de ejecutar y al cargar. Integración con SWAN real conserva ambas salidas. Los resultados ya sobrescritos requieren regeneración. |
| S02 / P1 | Los lectores sumaban UTM del padre + origen absoluto del nido; un nido fino podía ser elegido padre por tener más nodos. | Padre por dependencia BOU NEST y extensión física; todos los dominios reciben la misma traslación desde el origen del padre. Pruebas con UTM 600000/5800000, nidos de igual tamaño y nidos más finos. Conservada la convención local histórica de Coronel. |
| S03 / P1 | Campos y fondos se asignaban solo por tamaño; dos dominios con igual número de nodos podían mostrar el mismo resultado. | Prioridad a los archivos declarados en BLOCK y READINP de cada dominio. Pruebas estacionarias y temporales con resultados y fondos distintos pero igual forma. |
| S04 / P1 | El generador declara SET NAUTICAL, pero mapas y videos interpretaban siempre Dir con cos/sin cartesianos. | Convención obtenida del .swn y registrada en atributos. Flechas representan propagación: procedencia 270° → este; 0° → sur. Caso cartesiano conserva su interpretación. |
| S05 / P1 | El generador no estacionario no emitía MODE NONSTATIONARY ni salida temporal compatible con el lector MAT. | Modo explícito, archivos MAT, calendario OUT para BLOCK/NESTOUT/SPEC, validación de fechas y unidad del paso. Verificado con dos dominios, tres pasos de un minuto y SWAN instalado. |
| S06 / P1 | `generar_bot` recortaba silenciosamente coordenadas fuera del raster a su borde: podía inventar un fondo constante para otro lugar. | Rechazo de cobertura incompleta y datos no finitos; orden de dimensiones lat/lon explícito. Ningún .bot queda escrito al rechazar. |
| S07 / P1 | CoastWatch falló realmente por timeout WinError10060 durante un recorte mínimo. | Respaldo en el espejo oficial NOAA PMEL del mismo ETOPO1. Descarga real de 4×4 nodos, 4476 bytes, elevaciones −24 a 36 m. Aviso y URL de procedencia; caché solo reemplazada tras validar NetCDF y normalización. |
| S08 / P1 | Un código de salida distinto de cero podía aceptarse si existía norm_end; tras fallar el padre se seguía con sus nidos. | Exige retorno 0, norm_end y ausencia de .erf; detiene la cadena al fallar o cancelar. Las salidas regeneradas se reconocen por fecha/tamaño. |
| S09 / P2 | Con ffmpeg ausente, Pillow podía guardar GIF intentando conservar sufijo .mp4; una exportación fallida dejaba figuras abiertas. | Extensión ajustada al escritor real y cierre en finally, también en tablero PNG. GIF cuyo búfer estimado supera 512 MiB falla con orientación accionable. |
| S10 / P2 | El parser aceptaba mallas rotadas/esféricas interpretándolas como UTM rectangular y fallaba con la sintaxis válida CGRID REGULAR. | Soporte REGULAR y continuidad `&`; rechazo explícito de rotación/esférico y geometría no finita. UTF-8 y archivos históricos cp1252. No se anuncia soporte de geometrías no implementadas. |
| S11 / P2 | TM01, TM02 y PER se rotulaban Tp; WATLEV se rotulaba Setup; direcciones peak/transporte se rotulaban media. | Variables y atributos separados; las magnitudes distintas dejan de sustituir los productos que requieren otra cantidad. |
| S12 / P2 | Espectros ya convertidos a radianes seguían mostrando /°; NDIR se rotulaba cartesiano; múltiples puntos se reducían silenciosamente a uno. | Etiquetas /rad, convención NDIR/CDIR conservada, validación de cantidad y unidad, rechazo claro de varios puntos/cantidades. Un archivo ya en /rad no se reconvierte. |
| S13 / P2 | Campos MAT de cualquier tamaño se cargaban completos sin previsión; mallas manuales eludían el límite geométrico. | Límite previo de 512 MiB de datos por campo temporal y cuatro millones de nodos al generar fondo; números finitos y conteos enteros en el generador. No constituye un presupuesto total de RAM del proceso. |
| S14 / P2 | El multipanel indexaba el nido por el mismo índice del padre aun si las fechas diferían. | Rechazo de ejes temporales distintos antes de animar. |
| S15 / P2 | En POSIX se cancelaba solo el lanzador, pudiendo quedar SWAN hijo ejecutándose. | Sesión de proceso independiente y terminación del grupo. Revisado por código; ejecución POSIX pendiente en ese sistema. |
| S16 / P3 | El tablero solo recuperaba Hs/Tp/Dp de comentarios; un caso recién generado mostraba `?`, y un comentario viejo podía prevalecer sobre el borde real. | Recupera parámetros comunes de BOUN SIDE CON PAR; comentarios quedan como compatibilidad para archivos antiguos. |

## Evidencia de ejecución

Último chequeo enfocado: **79 passed, 96 deselected**, sin omisiones de datos
SWAN dentro de la selección. Incluye las pruebas nuevas, nesting y regresiones
relacionadas de `test_regresion.py`.

```powershell
Set-Location -LiteralPath 'C:\Users\123ja\OneDrive\Escritorio\Proyectos\Herramientas computacionales\Tablero Oleaje'
$env:PYTHONIOENCODING='utf-8'
$env:TABLERO_PROBAR_SWAN='1'
$env:TABLERO_DATOS_SWAN='C:\Users\123ja\OneDrive\Escritorio\Proyectos\Python\SWAN_Coronel'
python -m pytest test_auditoria_swan.py test_nesting.py test_regresion.py -q --basetemp=C:\Users\123ja\pytest-auditoria-swan-cierre -k 'swan or nesting or raster or malla or espectro_temporal or bot or cgrid or par_anidado or vectores_nauticos or runner or fallback_gif or error_writer or cantidades_medias or espectros_con_varios or espectro_ya_en'
```

Los dos tests `test_integracion_swan_real_par_anidado[False/True]` requieren
`TABLERO_PROBAR_SWAN=1`. Cada uno construye su propia carpeta temporal, fondo
uniforme sintético y mallas 7×7; ejecuta padre y nido reales y vuelve a cargar sus
salidas. Ninguno usa archivos originales como destino. Al ensayar inicialmente
10 minutos, SWAN rechazó el caso sintético por CFL > 10; la prueba final usa
un minuto, sin modificar el esquema ni forzar ignorar el error.

También se ejecutaron **8 regresiones específicas sobre datos reales de Coronel**
(TR100, TR10, reinante, offset, estructura temporal, nido y espectro). Son
comprobaciones de lectura contra referencias históricas, no validación física
nueva del modelo.

Se generó y revisó visualmente el tablero sintético estacionario y se exportó
realmente un GIF multipanel de tres cuadros. Evidencia temporal local:
`C:\Users\123ja\pytest-auditoria-swan-final\tablero_sintetico.png` y
`C:\Users\123ja\pytest-auditoria-swan-final\video_sintetico.gif`.
El PNG se inspeccionó antes del ajuste menor de metadatos del borde, por lo que
esa copia todavía muestra `?` en el encabezado; el cálculo y las flechas revisadas
ya corresponden a las correcciones.

Prueba HTTP real posterior al cambio: el primario falló y el fallback descargó
`raster_fallback.nc`, 4476 bytes. Solo se descargó el recorte
latitud [−37.05, −37.0], longitud [−73.2, −73.15].

## Límites que siguen abiertos

1. **P1 — Parser de fondos/BLOCK externo.** La app cubre su formato de salida y
   las corridas históricas verificadas, no cualquier entrada SWAN. Persisten
   supuestos de orientación `flipud`, fondo con factor 1/IDLA 1, fondo coincidente
   con CGRID, una cantidad por archivo, sin HEADER y extensión de texto `.txt`.
   Layouts alternativos, otras mallas INPGRID, factores de fondo y excepciones
   QUANTITY personalizadas necesitan soporte y fixtures antes de afirmar lectura
   genérica. Las geometrías rotadas/esféricas ahora se rechazan explícitamente.
2. **P2 — Anidamiento profundo.** El runner ordena padre antes de nidos, pero no
   implementa un grafo topológico completo para nidos de segundo/tercer nivel,
   ciclos ni comprobación de frescura de cada NESTOUT/BOU NEST. El flujo creado
   por la interfaz utiliza un padre y un nido, que sí quedó probado.
3. **P2 — Memoria total y red.** Los nuevos límites evitan casos extremos conocidos,
   pero no suman todos los campos, espectros, matrices temporales y figuras en un
   presupuesto global. El cuerpo HTTP del raster todavía se recibe completo.
   Conviene procesamiento por bloques y cancelación durante carga/descarga para
   archivos grandes. No se probó una máquina con poca RAM.
4. **P2 — Supuestos científicos predeterminados.** `gamma_rotura=0.29` proviene
   de la plantilla Coronel y requiere justificación para otro sitio. La advertencia
   de resolución basada en celdas por longitud de onda profunda no reemplaza un
   estudio de convergencia de SWAN ni la resolución del fondo. ETOPO1 tiene un
   minuto de arco; refinar CGRID no crea detalle batimétrico costero adicional.
5. **P2 — Ubicación local desconocida.** Un CGRID local sin metadatos sigue usando
   el offset histórico Coronel con aviso. El usuario debe fijar el origen correcto;
   no se dispone de información suficiente para inferirlo de cualquier caso.
6. **P2 — Plataformas.** Se probaron Windows, SWAN instalado y los paquetes de
   este equipo. Falta repetir lanzador/instalación/ffmpeg/WebView en una cuenta
   limpia y probar cancelación en macOS/Linux. Esos componentes se consolidan en
   la auditoría general, fuera de este informe especializado.

## Fuentes primarias contrastadas

- [SWAN: convenciones y unidades](https://swanmodel.sourceforge.io/online_doc/swanuse/node7.html): cartesiana de propagación y náutica de procedencia.
- [SWAN: CGRID](https://swanmodel.sourceforge.io/online_doc/swanuse/node25.html): sintaxis REGULAR y geometrías.
- [SWAN: salidas BLOCK y cantidades](https://swanmodel.sourceforge.io/online_doc/swanuse/node32.html): períodos medios/peak, nivel/setup, salida temporal.
- [SWAN: cálculo no estacionario](https://swanmodel.sourceforge.io/online_doc/swanuse/node34.html): modo, unidades del paso y restricciones temporales.
- [SWAN: archivo espectral](https://swanmodel.sourceforge.io/online_doc/swanuse/node50.html): localizaciones, QUANT y unidades.
- [NOAA PMEL: ETOPO1 etopo180](https://data.pmel.noaa.gov/socat/erddap/griddap/etopo180.html): espejo verificado del mismo dataset global y resolución nominal.
