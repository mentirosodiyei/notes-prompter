# Notes Prompter · Master

Módulo local para **Bitfocus Companion 5.1.1** y **Notes Prompter 0.4.0 o posterior con la misma API**. Controla el master desde Mac, Windows o Linux donde se ejecute Companion. No requiere instalar Node ni Python para usar el paquete `.tgz`.

## Conexión

1. Abre Notes Prompter y selecciona **Escuchar** en el receptor. Su servidor local es el master que vas a controlar; los agentes solo entregan notas.
2. En esta conexión escribe la IP o el nombre de **ese master** y el puerto HTTP, normalmente **8765**. Si ambos programas están en el mismo ordenador: `127.0.0.1`.
3. Configura **Paso de letra** y **Paso de velocidad**. Por defecto ambos valen 2. Ejemplo: letra 4 cambia 48 → 52 px; velocidad 1,5 cambia 24 → 25,5 px/s.
4. Guarda. La conexión pasa a verde cuando responde la API. El intervalo de actualización por defecto es 500 ms.

El módulo consulta las fuentes que detecta el master. El descubrimiento de agentes sigue a cargo de Notes Prompter. Companion no necesita escuchar UDP 8766. Si falta un equipo en la lista, comprueba primero que aparece en el panel del master.

## Seleccionar fuente

En **Presets → Fuentes detectadas por el master** aparece un botón por fuente, con nombre, PPT anunciado e identificador. Arrástralo a una tecla. Se ilumina en verde cuando está seleccionada. Los identificadores remotos son `IP:puerto`; si cambia la IP, actualiza el botón.

También puedes crear una acción **Fuente: seleccionar** y elegir una fuente del desplegable, o usar **Fuente anterior/siguiente**. El orden es el que publica el receptor. Desde Notes Prompter 0.4.3 solo se muestran los agentes detectados, sin PowerPoint local del receptor. La lista y los presets se actualizan con las altas y bajas detectadas por el master. Los botones ya colocados para una fuente desaparecida se conservan y muestran error si intentas seleccionarla.

Seleccionar una fuente cambia la entrada del master y sus receptores. Para controlar masters distintos, crea una conexión por master.

## Botones sin knob

En **Presets → Letra y velocidad · botones** hay cuatro botones:

- Letra +X y letra −X.
- Velocidad +X y velocidad −X.

Cada pulsación suma o resta el paso configurado. El campo **Paso X** de cada acción permite un paso propio; **0** usa el paso general de la conexión. Letra admite píxeles enteros; velocidad admite decimales. Ejemplo: un botón +1 y otro −5 pueden tener pasos distintos. Las teclas muestran el valor actual.

## Knobs / Stream Deck +

En **Presets → Letra y velocidad · knobs** hay dos controles listos para arrastrar a las posiciones de los diales:

- **Knob: LETRA**: giro a la derecha aumenta X px; izquierda reduce X px.
- **Knob: VELOC.**: giro a la derecha aumenta X px/s; izquierda reduce X px/s.

Los eventos de giro ya llevan sus acciones. Si configuras un control manualmente, asigna **Letra/Velocidad: aumentar** a **Rotate right** y **reducir** a **Rotate left**. El paso de ambas direcciones se puede editar por separado. La pulsación del dial no tiene una acción asignada.

## Comportamiento durante la presentación

Los ajustes son **en directo y temporales para la diapositiva actual**. Al cambiar de slide, fuente o preset, Notes Prompter vuelve a aplicar la programación correspondiente. El módulo usa los valores efectivos del master, incluidos sus presets, en cada operación.

Modificar letra activa el modo **tamaño fijo** para que el valor elegido se respete también en notas cortas. Límites de Notes Prompter: letra **24–600 px**, velocidad **−200 a +200 px/s** con receptor 0.4.5 o posterior. No supera esos límites aunque sigas girando o pulsando. La velocidad negativa retrocede; cero detiene el texto. También puedes usar **AUTO SCROLL**. En receptores anteriores se conservan sus límites.

Los giros y pulsaciones se procesan por orden. Si cambia la diapositiva o la fuente mientras una operación está pendiente, se descarta y se muestra un error; repite el ajuste en la actual. Una conexión lenta tiene una cola máxima de 64 operaciones.

Controles adicionales:

- **AUTO SCROLL** activa/desactiva el desplazamiento automático de esta slide. El retardo de inicio sigue siendo el del preset.
- **GUARDAR SLIDE** graba los ajustes actuales en la regla de esa diapositiva. Requiere un preset del PPT actual vinculado y activo en el master.
- **RECUPERAR PRESET** quita los ajustes temporales y recupera la regla/defaults actual.
- **Estado del master** muestra fuente, PPT y slide/total; al pulsarlo actualiza la lista y los valores.

La fuente local puede aparecer sin presentación; los controles de lectura requieren una diapositiva activa.

## Variables y feedbacks

Variables: `connected`, `master`, `source`, `source_id`, `sources_count`, `presentation`, `slide`, `total`, `font`, `font_mode`, `speed`, `auto_scroll`, `live`, `last_error`.

Ejemplo con la conexión llamada `NP`: `$(NP:font)` y `$(NP:speed)`. `last_error` conserva el último error de acción hasta que una acción termina correctamente. Los presets usan automáticamente el nombre de tu conexión.

Feedbacks: master conectado, fuente seleccionada, desplazamiento automático activo y ajustes temporales activos. Un estado de conexión verde indica que responde el master; la disponibilidad del PPT depende de su fuente.

## Diagnóstico

- Conexión roja: revisa IP, puerto y que esté iniciado el servidor del master. El módulo reintenta automáticamente. No cambia firewall ni ajustes de red.
- API antigua: usa Notes Prompter **0.4.0** como mínimo. La versión 0.2 no contiene los controles en directo necesarios.
- No permite seleccionar fuentes: inicia el receptor en **modo Escuchar**. Conecta a la IP de ese receptor, no a la IP de un agente.
- Error al guardar: vincula y activa un preset para ese PPT desde el panel del master.
- El master sigue una fuente, pero no llegan notas: comprueba la presentación y la conexión entre ese agente y el master en el propio Notes Prompter.

El módulo usa únicamente HTTP con la API existente de Notes Prompter. No escribe presentaciones. Solo el botón explícito de guardar escribe reglas en los presets. La API de Notes Prompter está pensada para la red local.

## Roles desde Notes Prompter 0.4.3

Configura la conexión con la **IP del receptor en modo Escuchar**, puerto 8765. Ese receptor detecta los agentes y conserva sus propios presets por PPT/slide. Un agente 0.4.3 rechaza el panel y los cambios de configuración; no es la dirección que debes indicar en Companion. Los datos del módulo y las acciones conservan compatibilidad con la API 0.4 anterior.

Con Notes Prompter 0.4.4, los ajustes de letra admiten 24–600 px. El módulo consulta el límite del receptor; en receptores anteriores conserva el máximo de 120 px.
