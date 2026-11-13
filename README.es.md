# 🎮 Recalbox RFID Launcher

[English](README.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · **Español** · [Italiano](README.it.md) · [Português](README.pt.md)

**Una tarjeta, un juego.** Coloca una tarjeta RFID sobre un lector conectado a tu Recalbox: el juego asociado
arranca, como un cartucho. Todo se configura desde una sola página web abierta en tu ordenador, sin instalar nada en
él y sin línea de comandos.

## 💡 La idea

El proyecto nació de una imagen sencilla: una **ranura en la caja de la consola**, con el lector escondido justo
detrás, en la que se **insertan tarjetas como si fueran cartuchos de juego**. Se mete una tarjeta y su juego arranca;
con el ajuste **«Salir del juego al retirar la tarjeta»**, sacar la tarjeta devuelve al menú de Recalbox, igual que
al quitar un cartucho. Cada tarjeta puede llevar la ilustración de su juego: una estantería de «cartuchos» que
cualquiera puede usar, niños incluidos, sin pasar nunca por los menús.

## ✨ Funciones

- 🏷️ **Una tarjeta = un juego**: el juego arranca exactamente como desde el menú de Recalbox (pantalla de carga,
  partidas guardadas, logros)
- 🔘 **Asociación en dos segundos**: sitúate en un juego en la Recalbox, pulsa el botón de la caja (o haz clic en la
  página), coloca la tarjeta
- 🧭 **Instalación guiada**: esquema de conexión, copia en la Recalbox, instalación desde el menú de Recalbox 10
  **sin reiniciar**, y autorización con el botón de la caja
- 🔐 **Sin contraseña**: un ordenador se autoriza manteniendo pulsado el botón de la caja 3 segundos
- 🩺 **Comprobación del hardware** en lenguaje claro, prueba del lector y **ajuste automático del lector**
- 🔄 **Actualizaciones con un clic** desde la página; las tarjetas y los ajustes se conservan siempre
- 🌍 **6 idiomas** (inglés, francés, alemán, español, italiano, portugués), temas claro y oscuro
- 🧩 **Sin dependencias**: solo el Python 3 que ya trae Recalbox, sin paquetes ni cambios en el sistema

## 🧰 Qué necesitas

| Material | Detalle |
| --- | --- |
| Recalbox | **versión 9 o superior** (se recomienda Recalbox 10: instalación sin reiniciar) |
| Raspberry Pi | 3, 4 o Zero 2, arrancando con Recalbox |
| Lector RFID **MFRC522** | módulo «RC522», por ejemplo el nf-SL001 (**solo 3,3 V**) |
| Tarjetas / llaveros | 13,56 MHz ISO 14443-A (MIFARE Classic, Ultralight…). Las tarjetas de 125 kHz no funcionan |
| Un pulsador | cualquier botón de contacto momentáneo, sin resistencia |
| Cables Dupont | 7 (6 para el lector y 1 más para el botón) |

> ⚠️ El RC522 funciona **solo con 3,3 V**. Nunca lo conectes al pin de 5 V de la Raspberry Pi: se destruiría.

## 🔌 Conexión

![Conexión del lector RC522 y del botón](docs/wiring.svg)

| RC522 | Raspberry Pi (GPIO BCM) | Pin físico |
| --- | --- | --- |
| SDA | GPIO8 (CE0) | 24 |
| SCK | GPIO11 (SCLK) | 23 |
| MOSI | GPIO10 (MOSI) | 19 |
| MISO | GPIO9 (MISO) | 21 |
| RST | GPIO25 | 22 |
| GND | GND | 6 |
| 3.3V | 3V3 | 1 |
| **Botón** | GPIO17 y GND | 11 y 9 |

El programa activa el pull-up interno de la Raspberry Pi: sin resistencia. Detalles:
[docs/WIRING.md](docs/WIRING.md) (en francés).

## 🚀 Instalación

### Lo más sencillo: la página

1. **Descarga** `recalbox-rfid-installer.html` de la [última versión](../../releases/latest) (o toma
   `dist/recalbox-rfid-installer.html` de este repositorio) y ábrelo con **Edge o Chrome**.
2. Elige **«Instalar por primera vez»** y sigue los cuatro pasos:
   1. **Conectar**: el esquema aparece en pantalla.
   2. **Copiar**: haz clic en «Elegir la carpeta de la Recalbox»; la página copia la dirección, pégala en la ventana
      (Ctrl+V, Intro) y confirma. La página escribe todo en la carpeta compartida de la Recalbox.
   3. **Lanzar**: en **Recalbox 10**, con el mando, `START` › Ajustes avanzados › Scripts de usuario ›
      **Install-RFID-reader**. En **Recalbox 9**, reinicia la Recalbox. La página espera y avanza sola; la Recalbox
      puede reiniciarse una vez sola para activar el lector.
   4. **Autorizar**: mantén pulsado el botón de la caja 3 segundos. Se abre la gestión de tarjetas.

> **Versión en línea**: <https://arubinu.github.io/recalbox-games-rf-launcher/> permite hacer los pasos 1 y 2. Los
> navegadores impiden que una página `https://` hable con un dispositivo de tu red: la página en línea propone
> descargarse para el resto, y la página guardada en tu ordenador lo hace todo.

### Si Windows no abre `\\RECALBOX\share`

- **Windows propone «Diagnosticar»**: tu conexión está en una red *Pública*, que oculta los dispositivos de tu red.
  Configuración › Red e Internet › Wi-Fi o Ethernet › tu red › Tipo de perfil de red › **Privada**. También puedes
  escribir la dirección IP de la Recalbox (`\\192.168.1.20\share`, visible en START › Ajustes de red).
- **Windows pide una contraseña o nada funciona**: en el paso 2, usa **«Descargar el instalador de Windows»**. Este
  pequeño archivo `.cmd` encuentra la Recalbox, se conecta a la carpeta compartida, copia todo y vuelve a abrir la
  página en el paso 3.

### Otros métodos

- **A mano**: copia la carpeta `recalbox-rfid` en `\\RECALBOX\share`, copia
  `recalbox-rfid\bootstrap\recalbox-rfid-agent(permanent).py3` en `userscripts\` y, en Recalbox 10, el contenido de
  `recalbox-rfid\bootstrap\manual` en `userscripts\manual\`. Después reinicia (o ejecuta *Install-RFID-reader*).
- **Por SSH**: `ssh root@recalbox.local "sh /recalbox/share/recalbox-rfid/install.sh --start"` (contraseña por
  defecto `recalboxroot`).

Guía paso a paso: [docs/INSTALLATION.md](docs/INSTALLATION.md) (en francés).

## 🎯 En el día a día

- **Asociar una tarjeta**: en la Recalbox, sitúate en un juego de la lista (sin lanzarlo). En la página, haz clic en
  **«Asociar una tarjeta a este juego»** (o pulsa brevemente el botón de la caja) y coloca la tarjeta en los
  10 segundos siguientes. Dos pitidos lo confirman.
- **Lanzar un juego**: coloca la tarjeta. La pantalla de carga del juego es la confirmación visual.
- **Borrar una tarjeta**: en la página, el icono de papelera junto a ella, o **«Borrar colocando la tarjeta»**.
- **Guardar tus tarjetas**: «Guardar la lista» crea un archivo CSV (se abre en Excel o LibreOffice); «Restaurar una
  lista» lo vuelve a cargar.

| Sonido | Significado |
| --- | --- |
| 1 pitido agudo | modo asociación activado |
| 2 pitidos ascendentes | tarjeta asociada |
| 1 pitido medio | tarjeta reconocida sin acción (`action = none`) |
| ningún sonido | un juego arranca: su pantalla de carga basta |
| 2 pitidos graves | modo borrado activado |
| 2 pitidos graves descendentes | tarjeta desconocida o acción rechazada |
| 3 pitidos descendentes | tiempo agotado (10 s para colocar la tarjeta) |

## 🔄 Actualizar

En la página, pestaña **Actualizaciones** › **«Actualizar a X»**: la página envía el programa que contiene. Las
tarjetas y los ajustes se conservan, y la página se reconecta sola. Otras formas (archivo ZIP, dirección, SSH):
[docs/UPDATING.md](docs/UPDATING.md) (en francés).

## 🗑️ Desinstalar

- **Recalbox 10**: `START` › Ajustes avanzados › Scripts de usuario › **Uninstall-RFID-reader**. Las tarjetas y los
  ajustes se conservan, e *Install-RFID-reader* sigue en el menú para reinstalar con un clic.
- **Todo, datos incluidos** (SSH): `sh /recalbox/share/system/rfid/uninstall.sh --remove-spi`

## 🩺 Solución de problemas

| Síntoma | Qué hacer |
| --- | --- |
| Windows propone «Diagnosticar» en `\\RECALBOX` | perfil de red *Pública*: cámbialo a *Privada*, o usa la dirección IP |
| La página no encuentra la Recalbox | ¿misma red? prueba su dirección IP en lugar de `recalbox.local` |
| «Lector no encontrado» | cableado, 3,3 V, y luego pestaña **Hardware** › «Probar con una tarjeta» |
| La tarjeta no se lee | debe ser de 13,56 MHz; una tarjeta bancaria sin contacto sirve para probar el lector |
| El botón no hace nada | GPIO17 ocupado por mandos GPIO (`controllers.gpio.enabled=0`), cableado a GND |
| El juego no arranca | hace falta Recalbox 9 o superior; el juego debe estar *seleccionado*, no una carpeta |
| La página vuelve a pedir autorización | la Recalbox se reinició: mantén pulsado el botón de la caja 3 segundos |

Guía completa: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) (en francés).

## 🛠️ Para desarrolladores

Todo se prueba en un PC, sin Raspberry Pi:

```sh
python app/main.py --home ./data config-init
python app/main.py --home ./data simulate      # lector y botón simulados
python tests/run_tests.py                      # pruebas unitarias, sin hardware
python tools/build_installer.py                # regenera dist/recalbox-rfid-installer.html
```

En la Recalbox, la herramienta de línea de comandos se llama siempre con `sh` (la carpeta compartida exFAT no guarda
el permiso de ejecución): `sh /recalbox/share/system/rfid/rfidctl help`.

Funcionamiento, en resumen:

- **Lectura de tarjetas**: controlador MFRC522 en Python puro sobre `/dev/spidev0.0` (`ioctl` con `ctypes`),
  secuencia ISO 14443-3A, tolerante con tarjetas clonadas.
- **Juego seleccionado**: leído de `/tmp/es_state.inf`, que el frontend de Recalbox escribe en cada evento.
- **Lanzamiento**: datagrama UDP `START|<sistema>|<ruta completa>` a `127.0.0.1:1337`, la orden oficial del frontend.
- **Página ↔ Recalbox**: un agente WebSocket escrito con la biblioteca estándar; la página se abre en local
  (`file://`) y un ordenador se autoriza con una pulsación física del botón (secreto de sesión en memoria).
- **Arranque**: dos scripts de usuario permanentes (servicio + agente) y, en Recalbox 10, dos scripts del menú
  (instalar / desinstalar).

Publicación en GitHub (Pages y versiones): [docs/PUBLISHING.md](docs/PUBLISHING.md) (en inglés). Los documentos
detallados de `docs/` y el [historial de versiones](CHANGELOG.md) están en francés.

## 📚 Documentación

- [docs/WIRING.md](docs/WIRING.md): cableado detallado y elección de pines
- [docs/INSTALLATION.md](docs/INSTALLATION.md): instalación paso a paso (Windows, macOS, Linux)
- [docs/USAGE.md](docs/USAGE.md): asociación, órdenes, configuración
- [docs/UPDATING.md](docs/UPDATING.md): actualizaciones y vuelta atrás
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md): diagnóstico y soluciones
- [docs/PUBLISHING.md](docs/PUBLISHING.md): GitHub Pages y versiones
