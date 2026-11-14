# companion-module-notesprompter-master

Control de Notes Prompter desde Bitfocus Companion **5.1.1**: selección dinámica de fuentes del master, tamaño de letra y velocidad mediante knobs o botones ±X, variables, feedbacks y presets listos para arrastrar.

## Instalación

1. En Companion abre **Modules → Import module package**.
2. Selecciona `notesprompter-master-1.0.3.tgz` **sin descomprimirlo**.
3. En **Connections** añade **Notes Prompter: Master** y configura IP/puerto del master.
4. En **Presets** elige esta conexión y arrastra los botones o knobs a tu superficie.

La instalación no requiere que este módulo esté publicado en la tienda. No incluye ni sustituye Notes Prompter. Utiliza la API de administración conservada en Notes Prompter 0.5.0. La guía completa de pasos, acciones y comportamiento está en [companion/HELP.md](companion/HELP.md) y dentro de la ayuda de la conexión.

## Desarrollo y pruebas

Node **22.20 o posterior dentro de la rama 22**. Las dependencias están fijadas en `package-lock.json`.

```sh
npm ci
npm test
npm run package
```

El empaquetador oficial genera el `.tgz` listo para importar. El código del módulo no requiere procesos secundarios, archivos del usuario, complementos nativos ni dependencias adicionales en el ordenador de Companion. La prueba de integración usa Python exclusivamente para ejecutar una instancia de prueba del servidor real, nunca durante el uso del módulo.

Para ejecutar la prueba de integración contra el proyecto de Notes Prompter, define `NP_PROJECT` (carpeta que contiene `notes_prompter/`) y `NP_PYTHON` (su Python con dependencias instaladas). Desde este repositorio se detecta automáticamente el proyecto raíz y su `.venv`. En otros equipos esa prueba se marca como omitida. El resto de pruebas usa servidores HTTP locales sintéticos y el API oficial de módulos de Companion.

La prueba de integración arranca dos servidores de Notes Prompter en puertos aleatorios de `127.0.0.1`, con notas sintéticas. Comprueba cambio de fuente local/remota, ajustes en directo, mensajes de salida WebSocket, guardado de reglas y recuperación. No abre PowerPoint, no usa anuncios LAN y no toca ajustes del usuario.

Además, después de empaquetar, si está instalado Companion en `/Applications/Companion.app`, se ejecuta una prueba opcional con su **runtime real de conexiones** y el código empaquetado. Usa un proceso separado y un socket temporal, sin instalar el módulo ni abrir/cambiar la configuración habitual de Companion. Comprueba la carga, la conversión de presets con eventos de giro, los campos de configuración y la ejecución real de acciones. `COMPANION_RESOURCES` permite indicar otra carpeta de recursos en macOS. Si ese runtime no existe o aún no has empaquetado, esta prueba se omite.

Protocolo utilizado:

- `GET /api/admin/state`
- `POST /api/admin/source`
- `PUT /api/admin/live-settings`
- `POST /api/admin/live-settings/save`
- `POST /api/admin/live-settings/reset`

El módulo no modifica el proyecto de Notes Prompter ni requiere recompilar su aplicación. Los cambios en directo se aplican al master configurado y sus receptores.

Referencias oficiales: [instalar paquetes de módulos](https://github.com/bitfocus/companion/blob/main/docs/user-guide/3_config/modules.md), [API de módulos](https://bitfocus.github.io/companion-module-base/), [herramientas de empaquetado](https://github.com/bitfocus/companion-module-tools).

## Roles desde Notes Prompter 0.4.3

Configura la conexión con la **IP del receptor en modo Escuchar**, puerto 8765. Ese receptor detecta los agentes y conserva sus propios presets por PPT/slide. Un agente 0.4.3 rechaza el panel y los cambios de configuración; no es la dirección que debes indicar en Companion. Los datos del módulo y las acciones conservan compatibilidad con la API 0.4 anterior.

No incluye acciones para Pausar/Volver al principio.
