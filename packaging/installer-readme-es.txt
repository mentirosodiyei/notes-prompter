NOTES PROMPTER

Agente lee las notas del PowerPoint local y las envía por la red.
Escuchar recibe las notas, aplica presets y muestra el prompter en la pantalla elegida.
Solo Escuchar tiene Panel de administración. Conecta Companion a ese receptor, puerto 8765.

Vincula un preset a cada PowerPoint y guarda sus reglas por diapositiva.
La detección automática usa el nombre del archivo y el número de diapositiva.
Usa nombres diferentes para presentaciones diferentes.

Idioma automático según el sistema: catalán, castellano o inglés para los demás.
Las notas y los nombres introducidos por el usuario no se traducen.

Cierra con Aplicación > Salir antes de actualizar. La X mantiene la aplicación en segundo plano.
Se conservan los ajustes en %LOCALAPPDATA%\NotesPrompter\settings.json.
Hace falta PowerPoint para el Agente local y Chrome/Edge para la salida de Escuchar.

Usa una red de confianza: TCP 8765 y UDP 8766 no tienen autenticación ni cifrado.
No expongas el servicio a Internet. No se modifican reglas del cortafuegos.
