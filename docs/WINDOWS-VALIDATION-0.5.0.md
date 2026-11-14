# Notes Prompter 0.5.0 · Windows x64

Entrega: 2026-11-14. Base pública 0.5.0 compilada en Windows, conservando macOS y la versión solicitada. No se ha publicado ni subido ningún archivo a GitHub.

## Cambios de esta integración

- Conservada la corrección Windows de descubrimiento: calcular broadcast por IP/máscara cuando psutil no lo proporciona, descartando interfaces inactivas, loopback, máscaras inválidas y enlaces /31 o /32. Se mantienen dos regresiones específicas.
- Conservado el icono propio del EXE en la especificación de PyInstaller; se usa el nuevo empaquetado de static y locales.
- Corregidas las traducciones omitidas de Elegir archivo PowerPoint y de la navegación del control manual (anterior, siguiente, ir a y títulos). La revisión visual detectó el botón sin traducir. Se añadieron pruebas de respuesta HTML en los tres idiomas y cobertura de textos estáticos para evitar omisiones futuras.
- Conservadas la protección de ajustes dañados, revisión monótona de reproducción, presets, velocidad reversible, cero magnético y controles remotos solo en el panel.

## Pruebas ejecutadas

- **237 pruebas Python correctas, 1 omitida**, 13,87 s en la ejecución final. La omitida corresponde a Cocoa/macOS. Permanece un aviso de deprecación de Starlette/httpx. Incluye los casos de 150 reglas en seis PPT, 150 presets, persistencia, ajustes dañados, idiomas, roles y ámbitos.
- **2 pruebas JavaScript correctas** sobre el renderizador: órdenes de pausa/reinicio retrasadas no sustituyen revisiones más recientes.
- Auditoría final del código público: **101 archivos, 0 incidencias**, incluido este informe. No sustituye una auditoría integral de binarios.
- Navegador real en Windows: panel castellano, catalán e inglés con datos sintéticos y lenguaje del receptor seleccionado explícitamente por el demo. Se comprobaron títulos, nombres de preset sin traducir, pausa/reanudación localizada y ausencia de botones de operador en la salida. Pausa estable, reinicio a cero manteniendo pausa y reanudación con velocidad elegida. Tras corregir los catálogos se verificaron visualmente el selector de archivo catalán/inglés y los mensajes Reprendre/Resume. Estas pruebas de lenguaje forzado no equivalen a cambiar el idioma real de Windows.
- El idioma real de interfaz de este Windows es castellano (0x0c0a). El usuario ejecutó el instalador inicial 0.5.0 y se observó la app instalada con interfaz castellana. Se observó Agente sin botón de administración, cambio a Escuchar, acceso único al panel y dos pantallas detectadas.
- En la prueba entre equipos, la ventana instalada mostró un agente remoto Mac y una salida activa. El usuario confirmó que llegaban las notas desde su agente Mac Apple Silicon 0.5.0 y decidió continuar él las pruebas manuales. No se registraron notas ni nombres reales en este informe.
- PowerPoint local Windows estaba abierto, pero el entorno automatizado no obtuvo su conexión COM: GetActiveObject devolvió Operación no disponible y el sondeo no detectó una presentación. No se modificó ni guardó el PPT. No se da por validada aquí la lectura COM de PowerPoint real Windows.

## Binarios finales

Compilados con Python 3.12.14 x64/Tk 8.6, PyInstaller 6.22.3 e Inno Setup 7 x64. Node disponible usado para las pruebas: 24.22.1. El instalador contiene inglés, catalán y español, con política de idioma de interfaz del sistema. Ambos PE verificados AMD64 y subsistema GUI; versión del instalador 0.5.0.0.

Se comprobó dentro del EXE final que los tres catálogos y los scripts admin/i18n/display coinciden byte por byte con las fuentes entregadas. Los nombres de archivo de código del paquete notes_prompter en PYZ son relativos, sin rutas de usuario. Se conserva la instalación por usuario y los ajustes fuera del directorio del programa. Ambos binarios están **sin firma Authenticode**.

La prueba instalada y Mac→Windows corresponde a la compilación inicial 0.5.0. Los binarios finales se recompilaron después únicamente por las correcciones de traducción y sus pruebas. No se afirma que el usuario haya instalado todavía este segundo compilado. Los SHA256 entregados identifican los archivos finales.

## Límites y pruebas pendientes

El usuario continúa las pruebas manuales del montaje. No se certifican: interfaz nativa y avisos con Windows configurado realmente en catalán/inglés; lectura COM local, notas editadas sin guardar y modo presentación en Windows; desconexión/reconexión entre equipos; seis PPT físicos; tamaño/DPI y salida a pantalla extendida durante todo el uso; actualización desde una instalación anterior con comprobación completa de ajustes, desinstalación y accesos directos. Companion no está incluido y no se ha probado.

La identificación de PPT sigue usando nombre de archivo normalizado sin extensión y número de diapositiva. Evitar nombres iguales y revisar reglas al reordenar slides. Se preservan límites de 200 presets y 2.000 reglas por preset.

Se hizo un respaldo privado de los ajustes existentes antes de solicitar la instalación; el respaldo queda fuera del proyecto y de las distribuciones. No se modificaron firewall, protecciones, idioma del sistema ni configuración de red. Uso previsto: LAN de confianza sin autenticación/cifrado, sin exposición a Internet.
