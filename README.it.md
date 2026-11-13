# 🎮 Recalbox RFID Launcher

[English](README.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Español](README.es.md) · **Italiano** · [Português](README.pt.md)

**Un badge, un gioco.** Appoggia un badge RFID su un lettore collegato alla tua Recalbox: il gioco associato parte,
come una cartuccia. Tutto si configura da un'unica pagina web aperta sul computer, senza installarci nulla e senza
riga di comando.
La stessa pagina si apre anche su un telefono, servita dalla Recalbox stessa.

## 💡 L'idea

Il progetto è nato da un'immagine semplice: una **fessura ricavata nella scatola della console**, con il lettore
nascosto subito dietro, in cui si **inseriscono le carte come cartucce di gioco**. Si infila una carta e il suo gioco
parte; con l'impostazione **«Uscire dal gioco quando si toglie il badge»**, estrarre la carta riporta al menu di
Recalbox, proprio come quando si toglie una cartuccia. Ogni carta può riportare l'illustrazione del suo gioco: uno
scaffale di «cartucce» che chiunque può usare, bambini compresi, senza mai passare dai menu.

## ✨ Funzioni

- 🏷️ **Un badge = un gioco**: il gioco parte esattamente come dal menu di Recalbox (schermata di caricamento,
  salvataggi, obiettivi)
- 🔘 **Associazione in due secondi**: posizionati su un gioco nella Recalbox, premi il pulsante della scatola (o
  clicca nella pagina), appoggia il badge
- 🧭 **Installazione guidata**: schema di collegamento, copia sulla Recalbox, installazione dal menu di Recalbox 10
  **senza riavvio**, poi autorizzazione con il pulsante della scatola
- 🔐 **Nessuna password**: un computer si autorizza tenendo premuto il pulsante della scatola per 3 secondi
- 🩺 **Verifica dell'hardware** in linguaggio semplice, test del lettore e **regolazione automatica del lettore**
- 🔄 **Aggiornamenti con un clic** dalla pagina; badge e impostazioni vengono sempre conservati
- 🌍 **6 lingue** (inglese, francese, tedesco, spagnolo, italiano, portoghese), tema chiaro e scuro
- 🧩 **Nessuna dipendenza**: solo il Python 3 già presente in Recalbox, nessun pacchetto, nessuna modifica al sistema
- 🖨️ **Carte da stampare**: l'immagine del gioco, logo e colori della sua console, sette modelli, ogni elemento si
  sposta e si ruota; dieci carte per foglio A4
- 📱 **Anche sul telefono**: la Recalbox serve la pagina da sola (codice QR); cerca un gioco e associa un badge senza
  la TV
- 🎲 **Carte speciali**: gioco a caso, tempo bonus, esci dal gioco, spegni
- ⏱️ **Tempo di gioco**: un limite per badge o per tutti, avvisi prima della fine, carte bonus con quota
- 💡 **Spia e messaggi a schermo**: un LED RGB o LED programmabili, messaggi sullo schermo del gioco

## 🧰 Cosa serve

| Materiale | Dettagli |
| --- | --- |
| Recalbox | **versione 9 o successiva** (consigliata Recalbox 10: installazione senza riavvio) |
| Raspberry Pi | 3, 4 o Zero 2, avviato su Recalbox |
| Lettore RFID **MFRC522** | modulo «RC522», ad esempio nf-SL001 (**solo 3,3 V**) |
| Badge / portachiavi | 13,56 MHz ISO 14443-A (MIFARE Classic, Ultralight…). I badge a 125 kHz non funzionano |
| Un pulsante | qualsiasi pulsante a contatto momentaneo, senza resistenza |
| Cavi Dupont | 7 (6 per il lettore, 1 in più per il pulsante) |
| Spia (facoltativa) | un modulo LED RGB o LED programmabili WS2812: vedi [docs/WIRING.md](docs/WIRING.md) |

> ⚠️ Il RC522 funziona **solo a 3,3 V**. Non collegarlo mai al pin 5 V del Raspberry Pi: verrebbe distrutto.

## 🔌 Collegamento

![Collegamento del lettore RC522 e del pulsante](docs/wiring.svg)

| RC522 | Raspberry Pi (GPIO BCM) | Pin fisico |
| --- | --- | --- |
| SDA | GPIO8 (CE0) | 24 |
| SCK | GPIO11 (SCLK) | 23 |
| MOSI | GPIO10 (MOSI) | 19 |
| MISO | GPIO9 (MISO) | 21 |
| RST | GPIO25 | 22 |
| GND | GND | 6 |
| 3.3V | 3V3 | 1 |
| **Pulsante** | GPIO17 e GND | 11 e 9 |

Il programma attiva il pull-up interno del Raspberry Pi: nessuna resistenza. Dettagli:
[docs/WIRING.md](docs/WIRING.md) (in inglese).

## 🚀 Installazione

### Il modo più semplice: la pagina

1. **Scarica** `recalbox-rfid-installer.html` dall'[ultima versione](../../releases/latest) (oppure prendi
   `dist/recalbox-rfid-installer.html` in questo repository) e aprilo con **Edge o Chrome**.
2. Scegli **«Prima installazione»** e segui i quattro passi:
   1. **Collegare**: lo schema appare sullo schermo.
   2. **Copiare**: clicca su «Scegli la cartella della Recalbox»; la pagina copia l'indirizzo, incollalo nella
      finestra (Ctrl+V, Invio) e conferma. La pagina scrive tutto nella condivisione della Recalbox.
   3. **Avviare**: su **Recalbox 10**, con il controller, `START` › Impostazioni avanzate › Script utente ›
      **Install-RFID-reader**. Su **Recalbox 9**, riavvia la Recalbox. La pagina attende e prosegue da sola; la
      Recalbox potrebbe riavviarsi una volta da sola per attivare il lettore.
   4. **Autorizzare**: tieni premuto il pulsante della scatola per 3 secondi. Si apre la gestione dei badge.

> **Versione online**: <https://arubinu.github.io/recalbox-games-rf-launcher/> permette di fare i passi 1 e 2. I
> browser vietano a una pagina `https://` di parlare con un dispositivo della tua rete: la pagina online propone
> quindi di scaricarsi per il resto, e la pagina salvata sul computer fa tutto.

### Se Windows non apre `\\RECALBOX\share`

- **Windows propone di «Diagnosticare»**: la tua connessione è su una rete *Pubblica*, che nasconde i dispositivi
  della rete. Impostazioni › Rete e Internet › Wi-Fi o Ethernet › la tua rete › Tipo di profilo di rete › **Privata**.
  Puoi anche digitare l'indirizzo IP della Recalbox (`\\192.168.1.20\share`, visibile in START › Impostazioni di rete).
- **Windows chiede una password, o non funziona niente**: al passo 2, usa **«Scarica il programma di installazione
  Windows»**. Questo piccolo file `.cmd` trova la Recalbox, si collega alla condivisione, copia tutto e riapre la
  pagina al passo 3.

### Altri metodi

- **A mano**: copia la cartella `recalbox-rfid` in `\\RECALBOX\share`, copia
  `recalbox-rfid\bootstrap\recalbox-rfid-agent(permanent).py3` in `userscripts\` e, su Recalbox 10, il contenuto di
  `recalbox-rfid\bootstrap\manual` in `userscripts\manual\`. Poi riavvia (o avvia *Install-RFID-reader*).
- **Via SSH**: `ssh root@recalbox.local "sh /recalbox/share/recalbox-rfid/install.sh --start"` (password predefinita
  `recalboxroot`).

Guida passo passo: [docs/INSTALLATION.md](docs/INSTALLATION.md) (in inglese).

## 🎯 Nell'uso quotidiano

- **Associare un badge**: sulla Recalbox, posizionati su un gioco nell'elenco (senza avviarlo). Nella pagina, clicca
  su **«Associa un badge a questo gioco»** (o premi brevemente il pulsante della scatola), poi appoggia il badge entro
  10 secondi. Due bip confermano.
- **Avviare un gioco**: appoggia il badge. La schermata di caricamento del gioco è la conferma visiva.
- **Cancellare un badge**: nella pagina, l'icona del cestino accanto, oppure **«Cancella appoggiando il badge»**.
- **Salvare i badge**: «Salva l'elenco» crea un file CSV (si apre in Excel o LibreOffice); «Ripristina un elenco» lo
  ricarica.

| Suono | Significato |
| --- | --- |
| 1 bip acuto | modalità associazione attiva |
| 2 bip ascendenti | badge associato |
| 1 bip medio | badge riconosciuto senza azione (`action = none`) |
| nessun suono | un gioco parte: la sua schermata di caricamento basta |
| 2 bip gravi | modalità cancellazione attiva |
| 2 bip gravi discendenti | badge sconosciuto o azione rifiutata |
| 3 bip discendenti | tempo scaduto (10 s per appoggiare il badge) |

## 🖨️ Carte, carte speciali e tempo di gioco

- **Cerca un gioco** (scheda Badge): digita qualche lettera, poi associa un badge al gioco, senza la TV. Comodo sul
  telefono: apri `http://recalbox.local:8765/` (o inquadra il codice QR del pulsante telefono nell'intestazione).
- **Stampa le carte** (scheda Carte): scegli un gioco e un modello, orizzontale o verticale; tocca un elemento della
  carta per spostarlo, ingrandirlo o ruotarlo; una fascia gialla mostra la parte che sporge dalla fessura. Salva
  l'impaginazione come modello, aggiungi le carte al foglio, poi stampa al 100 % (dieci carte per foglio A4).
- **Carte portatili**: matita di un badge › «Scrivi il gioco nel badge» salva il gioco nel badge stesso; funziona
  poi su qualsiasi Recalbox che abbia il gioco (badge MIFARE Classic, Ultralight, NTAG).
- **Carte speciali** (scheda Badge): gioco a caso, tempo bonus, esci dal gioco, spegni la Recalbox.
- **Tempo di gioco**: Impostazioni › Tempo di gioco per partita, o per badge con la matita. La Recalbox avvisa 5 minuti
  e 1 minuto prima della fine, poi esce dal gioco; una carta bonus aggiunge minuti, un numero limitato di volte al
  giorno, alla settimana…

Dettagli: [docs/USAGE.md](docs/USAGE.md) (in inglese).

## 🔄 Aggiornare

Nella pagina, scheda **Aggiornamenti** › **«Aggiorna alla X»**: la pagina invia il programma che contiene. Badge e
impostazioni vengono conservati e la pagina si ricollega da sola. Altri modi (file ZIP, indirizzo, SSH):
[docs/UPDATING.md](docs/UPDATING.md) (in inglese).

## 🗑️ Disinstallare

- **Recalbox 10**: `START` › Impostazioni avanzate › Script utente › **Uninstall-RFID-reader**. Badge e impostazioni
  vengono conservati, e *Install-RFID-reader* resta nel menu per reinstallare con un clic.
- **Tutto, dati compresi** (SSH): `sh /recalbox/share/system/rfid/uninstall.sh --remove-spi`

## 🩺 Risoluzione dei problemi

| Sintomo | Cosa fare |
| --- | --- |
| Windows propone di «Diagnosticare» su `\\RECALBOX` | profilo di rete *Pubblica*: impostalo su *Privata*, o usa l'indirizzo IP |
| La pagina non trova la Recalbox | stessa rete? prova il suo indirizzo IP al posto di `recalbox.local` |
| «Lettore non trovato» | cablaggio, 3,3 V, poi scheda **Hardware** › «Prova con un badge» |
| Il badge non viene letto | deve essere a 13,56 MHz; una carta bancaria contactless permette di provare il lettore |
| Il pulsante non fa niente | GPIO17 occupato dai controller GPIO (`controllers.gpio.enabled=0`), cablaggio verso GND |
| Il gioco non parte | serve Recalbox 9 o successiva; il gioco deve essere *selezionato*, non una cartella |
| La pagina chiede di nuovo l'autorizzazione | la Recalbox si è riavviata: tieni premuto il pulsante della scatola 3 secondi |

Guida completa: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) (in inglese).

## 🛠️ Per gli sviluppatori

Tutto si prova su un PC, senza Raspberry Pi:

```sh
python app/main.py --home ./data config-init
python app/main.py --home ./data simulate      # lettore e pulsante simulati
python tests/run_tests.py                      # test unitari, senza hardware
python tools/build_installer.py                # rigenera dist/recalbox-rfid-installer.html
```

Sulla Recalbox lo strumento a riga di comando si avvia sempre con `sh` (la condivisione exFAT non conserva il
permesso di esecuzione): `sh /recalbox/share/system/rfid/rfidctl help`.

Il funzionamento, in breve:

- **Lettura dei badge**: driver MFRC522 in Python puro su `/dev/spidev0.0` (`ioctl` tramite `ctypes`), sequenza
  ISO 14443-3A, tollerante con i badge clonati.
- **Gioco selezionato**: letto da `/tmp/es_state.inf`, scritto dal frontend di Recalbox a ogni evento.
- **Avvio**: datagramma UDP `START|<sistema>|<percorso completo>` su `127.0.0.1:1337`, il comando ufficiale del
  frontend.
- **Pagina ↔ Recalbox**: un agente WebSocket scritto con la libreria standard; la pagina si apre in locale
  (`file://`) e un computer si autorizza con una pressione fisica del pulsante (segreto di sessione in memoria).
- **Avvio del sistema**: due script utente permanenti (servizio + agente) e, su Recalbox 10, due script del menu
  (installa / disinstalla).

Pubblicazione su GitHub (Pages e release): [docs/PUBLISHING.md](docs/PUBLISHING.md). I documenti
dettagliati di `docs/` e lo [storico delle versioni](CHANGELOG.md) sono in inglese.

## 📚 Documentazione

- [docs/WIRING.md](docs/WIRING.md): cablaggio dettagliato, scelta dei pin e spia
- [docs/INSTALLATION.md](docs/INSTALLATION.md): installazione passo passo (Windows, macOS, Linux)
- [docs/USAGE.md](docs/USAGE.md): associazione, carte da stampare, carte speciali, tempo di gioco, comandi, configurazione
- [docs/UPDATING.md](docs/UPDATING.md): aggiornamenti e ritorno a una versione precedente
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md): diagnostica e soluzioni
- [docs/PUBLISHING.md](docs/PUBLISHING.md): GitHub Pages e release
