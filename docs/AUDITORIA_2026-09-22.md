# Auditoría integral de Tablero Oleaje

Fecha: 22 de septiembre de 2026. Alcance: código local, interfaz de escritorio, motor de oleaje, ERA5, SWAN, batimetría, videos, instalación y distribución. Se aplicaron correcciones y se preparó una entrega local. Al finalizar, el usuario autorizó crear un commit y subir los cambios a GitHub. Los `.exe` publicados previamente se conservaron; no se creó una nueva release. Las notas de los subinformes sobre ausencia de commits describen la etapa de revisión anterior a esa autorización.

## Dictamen

**La aplicación puede instalarse y ejecutar los flujos locales comprobados en Windows con los requisitos indicados. Todavía no está lista para ofrecerla como una aplicación autónoma que cualquier persona abra sin preparación.** El instalador actual distribuye código Python y crea un entorno al primer inicio; necesita Python de 64 bits, internet inicial y WebView2. SWAN, ffmpeg y la cuenta CDS son dependencias independientes.

Se verificó un entorno virtual nuevo, separado del entorno habitual del desarrollador, en este mismo computador. La app abrió su ventana WebView2, ejecutó el puente JavaScript–Python y generó un tablero completo desde una serie sintética con vista previa. Eso prueba el camino de instalación y uso básico; no equivale a probar otro Windows, otra cuenta ni macOS.

El objetivo de distribución tiene tres bloqueos de cierre: una entrega que incluya Python si se busca doble clic sin preparación; pruebas de instalación/actualización/desinstalación en otro equipo sin administrador; y comprobación autenticada de CDS. La descarga batimétrica primaria NOAA falló en esta red; se añadió un espejo oficial del mismo dataset y se comprobó un recorte real pequeño.

## Cobertura y evidencia

| Área | Comprobación | Límite |
|---|---|---|
| Instalación | Copia limpia del manifiesto; bootstrap crea `.venv`; imports y `pip check` correctos | Misma cuenta Windows/Python 3.13 x64 |
| Aperturas posteriores | Bootstrap con `PIP_NO_INDEX=1` e índice inválido termina correctamente; se valida firma de requisitos y lock | No representa una instalación nueva sin internet |
| Escritorio | WebView2 real, puente API, análisis de 240 registros sintéticos, PNG y preview | CDS sustituido por estado sin configurar; sin usar credenciales |
| UI | Chromium real: Escape, confirmaciones repetidas, tareas rápidas/lentas, conservación de botones deshabilitados | Pruebas de interfaz independientes del servicio CDS |
| Resolución de pantalla | Inicio inspeccionado a 960×700; navegación a 520×580 sin desbordamiento horizontal del documento | La barra lateral se oculta en estrecho; mejora pendiente de navegación accesible |
| Oleaje | Regresiones, exportación PNG con NaN, estructura CSV/NetCDF, extremos degenerados, dirección circular, caché y concurrencia | No es validación de diseño de obras ni de extremos con observaciones |
| SWAN existente | Lectura de casos Coronel y archivo de oleaje de Talcahuano sin modificar originales | Casos conocidos, no todos los dialectos posibles |
| SWAN ejecutable | Dos pares anidados sintéticos, estacionario y no estacionario, en carpetas temporales; carga de resultados | No certifica la física de un caso de ingeniería |
| Batimetría remota | Espejo oficial NOAA PMEL descargó 4×4 nodos ETOPO1 tras fallar CoastWatch | Recorte pequeño; no se probó la descarga de una malla costera grande |
| Distribución | ZIP con lista explícita, CRC y verificación de exclusiones; fuentes Inno compiladas a archivo temporal | No se instaló el `.exe` en otra cuenta; publicación anterior sin modificar |
| macOS | Revisión de scripts, rutas nativas, LF, permisos de ejecutables y `bash -n` | No se ejecutó Cocoa ni se probó DMG/Gatekeeper |

Los resultados exactos de la ejecución final y el hash del ZIP se registran al final de este informe. Los subinformes documentan reproducciones y pruebas dirigidas:

- [Distribución y portabilidad](auditoria_2026_09_22_distribucion.md).
- [Oleaje, ERA5 y productos](auditoria_2026_09_22_oleaje.md).
- [SWAN, batimetría y videos](auditoria_2026_09_22_swan.md).

## Hallazgos principales corregidos

P1 significa fallo que puede impedir el uso o producir un resultado incorrecto importante; P2 indica robustez, calidad o compatibilidad que debe atenderse. Son prioridades de esta auditoría, no una certificación de seguridad.

| ID | Prioridad | Problema comprobado | Estado y referencia |
|---|---|---|---|
| D01 | P1 | Un `.venv` existente bastaba para saltarse la instalación aunque pip hubiera fallado | Corregido: `scripts/estado_entorno.py`, bootstraps y lanzadores; reintenta si falta el marcador o cambian requisitos |
| D02 | P1 | Inno copiaba por comodín y podía incluir configuración privada local o credenciales colocadas en el repo | Corregido: lista explícita común para ZIP/Inno/macOS; se probó exclusión con archivos privados ficticios, sin leer secretos |
| D03 | P2 | macOS actualizaba pip y reinstalaba librerías en cada apertura | Corregido en fuentes; apertura normal comprueba el entorno localmente |
| D04 | P2 | Preparación no reproducible entre instalaciones | Lock de las versiones verificadas para Windows/Python 3.13; todavía sin hashes de wheels ni lock de otras plataformas |
| D05 | P2 | JSON de preferencias no objeto, sonda de escritura con nombre fijo y rutas de fallback inconsistentes | Corregido: recuperación de configuración, temporal único y directorios nativos |
| D06 | P2 | Crear un acceso local borraba el homónimo del Escritorio; guías seguían indicando Program Files/admin | Corregido; accesos del usuario preservados y documentación per-user actualizada |
| U01 | P1 | Escape cerraba «¿Borrar esta descarga ERA5?» como si se hubiera aceptado | Corregido: solo el botón Continuar confirma; Escape devuelve false; prueba real en Chromium |
| U02 | P1 | Un resultado que llegaba antes de registrar `waitTask` se perdía y acababa en espera agotada | Corregido: resultados pendientes por identificador; inicio/fin ordenados bajo el bloqueo Python |
| U03 | P2 | La UI se desbloqueaba al agotar su espera aunque Python seguía trabajando; Atrás/menú permitían cambiar el contexto activo | Corregido: aviso conservando espera, controles bloqueados y cancelación SWAN disponible |
| U04 | P2 | Un archivo elegido por diálogo en otra unidad era rechazado por estar fuera del perfil | Corregido: autorización de la selección nativa durante la sesión; archivos vecinos y escapes siguen rechazados. Tras reiniciar puede requerir elegir de nuevo |
| U05 | P2 | Ciertas entradas JSON o sesiones guardadas inválidas rompían la API o el inicio | Corregido: objetos y pasos válidos; preferencias e historial corruptos se recuperan |
| U06 | P2 | Borrado de caché admitía nombres que contenían ERA5_ en cualquier posición y carpetas descendientes | Corregido: solo hijos directos `ERA5_*` de salidas; no se borra durante una tarea |
| U07 | P2 | Comparación con boya contaba pares NaN y calculaba medias sobre muestras diferentes; podía serializar NaN | Corregido: únicamente pares finitos comunes; correlación indefinida devuelve null |
| U08 | P2 | Log GUI ignoraba el fallback de salidas; consola Windows podía fallar por caracteres Unicode; SWAN fallido se mostraba «Listo» en avanzado | Corregido: ruta común, salida UTF-8 y estado que refleja el resultado del modelo |
| O01 | P1 | Un NaN en Hs/Tp podía abortar el tablero completo | Corregido: filtrado por pares finitos; exportación PNG probada |
| O02 | P1 | Gumbel fallaba con máximos constantes o años sin datos; borde podía seleccionar infinito | Corregido: entradas finitas y ajuste degenerado rechazado/omitido con motivo |
| O03 | P1 | Petición espectral ERA5 dirigida al catálogo equivocado | Corregido según documentación ECMWF: ERA5 complete/MARS, param 140251; pendiente servicio autenticado real |
| O04 | P1 | Operaciones NetCDF concurrentes podían provocar caídas dependientes del sistema | Corregido en el camino ERA5: exclusión I/O compartida, red paralela; mocks ya no generan NetCDF desde hilos |
| O05 | P2 | Caché sin viento se reutilizaba cuando después se solicitaba viento | Corregido en tramos, caché final y puente/UI |
| O06 | P2 | Fechas fraccionales se truncaban; formatos NetCDF no puntuales llegaban al análisis | Corregido: contrato estructural explícito, fechas válidas y datos ordenados |
| O07 | P2 | Media de 359° y 1° resultaba 180°; Tp espectral usaba máximo de energía por banda en lugar de densidad | Corregido con estadísticas circulares y pico de densidad; convenciones espectrales etiquetadas |
| S01 | P1 | Padre y nido escribían los mismos nombres de salidas, sobrescribiéndose | Corregido: nombres separados por caso y detección de colisiones antiguas |
| S02 | P1 | Se duplicaba el offset UTM de un nido absoluto y se confundía el padre según número de nodos | Corregido: relaciones de anidamiento, referencias de archivos y coordenadas; probado con SWAN real |
| S03 | P1 | Builder no estacionario incompleto: modo y salidas temporales insuficientes | Corregido y ejecutado con tres pasos temporales reales sobre datos sintéticos |
| S04 | P2 | Flechas náuticas se dibujaban como cartesianas; períodos medios/nivel de agua se confundían con Tp/setup | Corregido: metadatos y cantidades diferenciadas; etiquetas espectrales consistentes |
| S05 | P2 | Runner podía aceptar código de salida fallido o continuar nidos tras fallar el padre | Corregido: estado del proceso y corte de la cadena; conserva diagnósticos |
| S06 | P2 | Raster local recortaba nodos fuera de cobertura; GIF/series grandes podían agotar memoria | Corregido: rechazo de cobertura insuficiente, límites preventivos y cierre de figuras; uso de MP4 cuando corresponde |
| S07 | P1 | Timeout real del proveedor batimétrico interrumpía el flujo automático | Corregido con respaldo oficial NOAA PMEL del mismo ETOPO1, validación antes de reemplazar caché y aviso de procedencia; HTTP real comprobado |

## Pendientes priorizados para terceros

| Orden | Trabajo | Criterio verificable de cierre |
|---|---|---|
| 1 | Preparar distribución Windows con Python y librerías incluidos | Abrir desde cuenta estándar de un Windows sin Python, sin instalar librerías por pip. Incluir todos los assets y comprobar el backend WebView2 |
| 2 | Probar instalación, actualización y desinstalación fuera del equipo de desarrollo | Conservar salidas y preferencias; no pedir administrador; rutas con espacios/acentos; archivo en unidad externa; error útil si falta WebView2 |
| 3 | Validar dependencias externas reales | Descarga corta ERA5 con cuenta propia autorizada, añadir viento sobre caché, espectro MARS; probar proveedor batimétrico o permitir selección clara de fuente local cuando no responde |
| 4 | Separar solicitudes ERA5 de viento y olas | Validar rejillas/tiempos distintos y unión explícita; ECMWF recomienda no mezclarlas en una solicitud NetCDF |
| 4b | Restringir o ampliar lectura de SWAN externos antes de anunciar soporte genérico | Probar IDLA/factores de fondo, INPGRID distinto de CGRID, HEADER, varias cantidades por BLOCK y excepciones personalizadas; todavía existen supuestos que pueden interpretar mal esos archivos |
| 5 | Añadir integración continua Windows/macOS y artefactos por plataforma | Suite en entorno limpio, humo del ejecutable distribuido, versiones/hashes y reporte de release; retirar afirmaciones de compatibilidad sin evidencia |
| 6 | Mejorar diagnóstico inicial para un usuario nuevo | Mostrar Python/backend, SWAN y ffmpeg detectados, carpeta efectiva y botones de instalación/selección solo cuando hagan falta; ofrecer el ejemplo incluido sin CDS |
| 7 | Evitar sobrescritura y mejorar trazabilidad | Identificar fuente por ruta/huella, no solo stem; un mismo nombre de archivo en dos carpetas puede compartir destino. Guardar parámetros, versión, convención y fecha junto al resultado; no reemplazar entregas manuales inadvertidamente |
| 8 | Mejorar calidad científica de extremos y particiones | Cobertura anual real y años incompletos, incertidumbre Gumbel, criterio de asociación Hs–Tp–Dir, validación contra observaciones y seguimiento temporal de familias. No extrapolar «pasan tests» a validez de diseño |
| 9 | Completar accesibilidad y navegación | Tarjetas operables con Tab/Enter, avisos anunciados por lector, menú disponible en 520 px y controles de error/foco consistentes. El inicio actual tiene cuatro tarjetas distribuidas 3+1 |
| 10 | Endurecer ciclo de vida de trabajos | Cerrar durante SWAN/ERA5, cancelación de descargas, bloqueo entre dos instancias y recuperación tras interrupción. El bloqueo NetCDF añadido solo cubre un proceso |
| 11 | Definir formatos admitidos con claridad | CSV regional/separador/unidades, MAT con nombres distintos, calendarios NetCDF y límites de tamaño. SWAN rotado/esférico/no estructurado y múltiples nidos necesitan soporte explícito o rechazo claro |
| 12 | Pulir tableros exportados | En el ejemplo inspeccionado, etiquetas de percentiles altos quedan muy próximas y el pie de paneles omitidos resulta denso. Separar anotaciones y ajustar saltos de línea sin alterar los resultados |

Una ruta razonable para Windows es empaquetar primero en modo carpeta con PyInstaller y luego envolverla en Inno Setup. PyInstaller incluye el intérprete y las dependencias y requiere compilar para cada sistema; pywebview documenta esta vía para Windows/Linux. Es una recomendación de implementación, **no un ejecutable autónomo ya construido en esta auditoría**. Fuentes: [PyInstaller, modo de operación](https://pyinstaller.org/en/stable/operating-mode.html), [pywebview, empaquetado](https://pywebview.flowrl.com/guide/freezing) y [requisitos de instalación](https://pywebview.flowrl.com/guide/installation).

## Uso de la entrega local

Extraer el ZIP completo en una carpeta escribible. En Windows con Python de 64 bits, abrir `iniciar_windows.bat`. La primera preparación necesita internet; las siguientes aperturas reutilizan el entorno comprobado. El ZIP no incluye Python, SWAN, ffmpeg ni credenciales.

Para probar sin CDS, elegir **Analizar oleaje en un punto → Tengo un archivo** y abrir `ejemplos/oleaje_demo_sintetico.csv`. Es un ejemplo artificial de 240 registros, no información real de oleaje. El flujo debe llegar al PNG y omitir climatología/extremos por duración insuficiente.

Los `.exe` v1.0.0/v1.0.1 existentes y la release pública siguen siendo anteriores a esta revisión. No entregar esos binarios como si contuvieran estos cambios.

## Reproducibilidad

Desde la raíz del repositorio, en PowerShell:

```powershell
python -m pytest -q --capture=sys --basetemp="$env:USERPROFILE\pytest-tablero"
```

Los ocho tests de datos históricos se activan con `TABLERO_DATOS_SWAN` y `TABLERO_DATOS_OLEAJE`. Los dos casos SWAN sintéticos requieren `TABLERO_PROBAR_SWAN=1`; no corren sobre los originales. Playwright/Chromium es una dependencia opcional de las pruebas de UI, no de la aplicación. El humo nativo reproducible está en `tools/verificar_escritorio.py` y recibe una carpeta de entrega aislada.

La captura predeterminada `fd` de pytest produjo errores intermitentes al cargar `tk.tcl` en las pruebas tkinter antiguas: la ejecución integrada con SWAN real obtuvo 253 aprobadas y 2 fallidas por ese motivo. Se reprodujeron incluso ejecutando solo el asistente. Con `--capture=sys` pasaron API+asistente (32 casos) y el asistente solo en dos procesos consecutivos (17 cada uno), sin omitir casos ni modificar Python/Tcl. La evidencia apunta a una interacción de captura/Tcl en este entorno, sin demostrar la causa interna definitiva. La invocación recomendada usa `--capture=sys`.

El primer humo de escritorio también expuso la codificación CP1252 de su consola: se corrigió el harness y el arranque de depuración a UTF-8, y se repitió con éxito. Se mantuvo el registro de esos primeros fallos para no confundirlos con una validación limpia.

## Resultado final de comprobación

- **255 pruebas aprobadas, sin fallos, omisiones ni deselecciones**, en 37,16 s, con `--capture=sys`, los dos directorios de datos reales configurados y `TABLERO_PROBAR_SWAN=1`. Incluye las cinco pruebas Chromium y las dos integraciones SWAN reales.
- Tres advertencias: una de compatibilidad binaria NumPy/netCDF4 del entorno global y dos de deprecación `argmax` de xarray. No se ocultaron. El entorno limpio con lock pasó imports, `pip check` y exportación del tablero.
- Humo nativo final: `ok=true`, Python 3.13.13, versión local `1.0.1 + auditoría 2026-09-22`, 240 registros procesados y `preview=true`. Se inspeccionó visualmente el PNG sintético.
- `git diff --check`, compilación de los módulos Python revisados y `node --check` de todos los JavaScript terminaron correctamente.
- Evidencias locales reproducibles: `output/verificacion_escritorio.json`, `output/verificacion_zip.json` y `output/playwright/inicio-auditado.png` (fuera del paquete y de git).
- La entrega final contiene 67 archivos definidos por manifiesto. No contiene `.git`, `.venv`, configuraciones de agentes, `config.json`, credenciales ni resultados personales. El ejemplo incluido es explícitamente sintético.

Entrega: `dist/Tablero_Oleaje_auditado_2026-09-22.zip`, 607697 bytes. CRC del ZIP correcto. SHA-256:

```text
1dab994c8dde534b3c253801c12b8189f8d4dd9f29cba161e14be84887159d79
```
