# 🎮 Recalbox RFID Launcher

[English](README.md) · [Français](README.fr.md) · **Deutsch** · [Español](README.es.md) · [Italiano](README.it.md) · [Português](README.pt.md)

**Ein Badge, ein Spiel.** Legen Sie einen RFID-Badge auf einen Leser an Ihrer Recalbox: Das zugeordnete Spiel
startet, wie ein Steckmodul. Alles wird über eine einzige Webseite auf Ihrem Computer eingerichtet, ohne Installation
dort und ohne Kommandozeile.
Dieselbe Seite öffnet sich auch auf einem Telefon, direkt von der Recalbox bereitgestellt.

## 💡 Die Idee

Das Projekt entstand aus einem einfachen Bild: ein **Schlitz im Gehäuse der Konsole**, direkt dahinter der versteckte
Leser, in den man **Karten wie Spielmodule einsteckt**. Karte hinein, das Spiel startet; mit der Einstellung **„Spiel
beenden, wenn der Badge entfernt wird“** führt das Herausziehen der Karte zurück ins Recalbox-Menü, genau wie beim
Herausnehmen eines Moduls. Jede Karte kann das Bild ihres Spiels tragen: ein Regal voller „Module“, das alle nutzen
können, auch Kinder, ohne je durch die Menüs zu gehen.

## ✨ Funktionen

- 🏷️ **Ein Badge = ein Spiel**: Das Spiel startet genau wie aus dem Recalbox-Menü (Ladebildschirm, Spielstände,
  Erfolge)
- 🔘 **Zuordnung in zwei Sekunden**: Spiel auf der Recalbox auswählen, Gehäusetaste drücken (oder in der Seite
  klicken), Badge auflegen
- 🧭 **Geführte Installation**: Anschlussplan, Kopie auf die Recalbox, Installation aus dem Menü von Recalbox 10
  **ohne Neustart**, danach Freigabe mit der Gehäusetaste
- 🔐 **Kein Passwort**: Ein Computer wird freigegeben, indem man die Gehäusetaste 3 Sekunden hält
- 🩺 **Hardware-Prüfung** in verständlicher Sprache, Lesertest und **automatische Lesereinstellung**
- 🔄 **Updates mit einem Klick** aus der Seite; Badges und Einstellungen bleiben immer erhalten
- 🌍 **6 Sprachen** (Englisch, Französisch, Deutsch, Spanisch, Italienisch, Portugiesisch), helles und dunkles Design
- 🧩 **Keine Abhängigkeiten**: nur das in Recalbox enthaltene Python 3, kein Paket, keine Systemänderung
- 🖨️ **Karten zum Drucken**: das Bild des Spiels, Logo und Farben seiner Konsole, sieben Vorlagen, jedes Element
  verschieb- und drehbar; zehn Karten pro A4-Blatt
- 📱 **Auch auf dem Telefon**: Die Recalbox stellt die Seite selbst bereit (QR-Code); Spiel suchen und Badge zuordnen,
  ohne Fernseher
- 🎲 **Sonderkarten**: Zufallsspiel, Bonuszeit, Spiel beenden, ausschalten
- ⏱️ **Spielzeit**: ein Limit pro Badge oder für alle, Warnungen vor dem Ende, Bonuskarten mit Kontingent
- 💡 **Statusleuchte und Bildschirmmeldungen**: eine RGB-LED oder programmierbare LEDs, Meldungen auf dem
  Spielbildschirm

## 🧰 Was Sie brauchen

| Hardware | Details |
| --- | --- |
| Recalbox | **Version 9 oder neuer** (Recalbox 10 empfohlen: Installation ohne Neustart) |
| Raspberry Pi | 3, 4 oder Zero 2, mit Recalbox |
| RFID-Leser **MFRC522** | Modul „RC522“, zum Beispiel nf-SL001 (**nur 3,3 V**) |
| Badges / Schlüsselanhänger | 13,56 MHz ISO 14443-A (MIFARE Classic, Ultralight…). 125-kHz-Badges funktionieren nicht |
| Eine Drucktaste | jeder Taster, kein Widerstand nötig |
| Dupont-Kabel | 7 (6 für den Leser, 1 zusätzlich für die Taste) |
| Statusleuchte (optional) | ein RGB-LED-Modul oder programmierbare WS2812-LEDs: siehe [docs/WIRING.md](docs/WIRING.md) |

> ⚠️ Der RC522 arbeitet **nur mit 3,3 V**. Schließen Sie ihn nie an den 5-V-Pin des Raspberry Pi an: Er würde zerstört.

## 🔌 Anschluss

![Anschluss des RC522-Lesers und der Taste](docs/wiring.svg)

| RC522 | Raspberry Pi (BCM-GPIO) | Physischer Pin |
| --- | --- | --- |
| SDA | GPIO8 (CE0) | 24 |
| SCK | GPIO11 (SCLK) | 23 |
| MOSI | GPIO10 (MOSI) | 19 |
| MISO | GPIO9 (MISO) | 21 |
| RST | GPIO25 | 22 |
| GND | GND | 6 |
| 3.3V | 3V3 | 1 |
| **Taste** | GPIO17 und GND | 11 und 9 |

Der interne Pull-up des Raspberry Pi wird vom Programm aktiviert: kein Widerstand. Details:
[docs/WIRING.md](docs/WIRING.md) (auf Englisch).

## 🚀 Installation

### Am einfachsten: die Seite

1. **Laden Sie** `recalbox-rfid-installer.html` aus der [neuesten Version](../../releases/latest) herunter (oder
   nehmen Sie `dist/recalbox-rfid-installer.html` aus diesem Repository) und öffnen Sie sie mit **Edge oder Chrome**.
2. Wählen Sie **„Erstinstallation“** und folgen Sie den vier Schritten:
   1. **Anschließen**: Der Anschlussplan wird angezeigt.
   2. **Kopieren**: Klicken Sie auf „Recalbox-Ordner wählen“; die Seite kopiert die Adresse, fügen Sie sie im
      Fenster ein (Strg+V, Enter) und bestätigen Sie. Die Seite schreibt alles auf die Recalbox-Freigabe.
   3. **Starten**: Unter **Recalbox 10** mit dem Controller `START` › Erweiterte Einstellungen › Benutzerskripte ›
      **Install-RFID-reader**. Unter **Recalbox 9** die Recalbox neu starten. Die Seite wartet und geht von selbst
      weiter; die Recalbox startet eventuell einmal von selbst neu, um den Leser zu aktivieren.
   4. **Freigeben**: Halten Sie die Gehäusetaste 3 Sekunden gedrückt. Die Badge-Verwaltung öffnet sich.

> **Online-Version**: <https://arubinu.github.io/recalbox-games-rf-launcher/> erlaubt die Schritte 1 und 2. Browser
> verbieten einer `https://`-Seite, mit einem Gerät in Ihrem Netzwerk zu sprechen: Die Online-Seite bietet daher an,
> sich für den Rest herunterzuladen, und die auf Ihrem Computer gespeicherte Seite erledigt alles.

### Wenn Windows `\\RECALBOX\share` nicht öffnet

- **Windows schlägt „Diagnose“ vor**: Ihre Verbindung ist ein *öffentliches* Netzwerk, das die Geräte Ihres Netzwerks
  ausblendet. Einstellungen › Netzwerk und Internet › WLAN oder Ethernet › Ihr Netzwerk › Netzwerkprofiltyp ›
  **Privat**. Sie können auch die IP-Adresse der Recalbox eingeben (`\\192.168.1.20\share`, angezeigt unter START ›
  Netzwerkeinstellungen).
- **Windows verlangt ein Passwort oder nichts funktioniert**: Nutzen Sie in Schritt 2 **„Windows-Installationsprogramm
  herunterladen“**. Diese kleine `.cmd`-Datei findet die Recalbox, verbindet sich mit der Freigabe, kopiert alles und
  öffnet die Seite wieder bei Schritt 3.

### Andere Methoden

- **Von Hand**: Kopieren Sie den Ordner `recalbox-rfid` nach `\\RECALBOX\share`,
  `recalbox-rfid\bootstrap\recalbox-rfid-agent(permanent).py3` nach `userscripts\` und unter Recalbox 10 den Inhalt
  von `recalbox-rfid\bootstrap\manual` nach `userscripts\manual\`. Dann neu starten (oder *Install-RFID-reader*
  ausführen).
- **Per SSH**: `ssh root@recalbox.local "sh /recalbox/share/recalbox-rfid/install.sh --start"` (Standardpasswort
  `recalboxroot`).

Schritt-für-Schritt-Anleitung: [docs/INSTALLATION.md](docs/INSTALLATION.md) (auf Englisch).

## 🎯 Im Alltag

- **Badge zuordnen**: Wählen Sie auf der Recalbox ein Spiel in der Liste (ohne es zu starten). Klicken Sie in der
  Seite auf **„Badge diesem Spiel zuordnen“** (oder drücken Sie kurz die Gehäusetaste) und legen Sie den Badge
  innerhalb von 10 Sekunden auf. Zwei Pieptöne bestätigen.
- **Spiel starten**: Badge auflegen. Der Ladebildschirm des Spiels ist die Rückmeldung.
- **Badge löschen**: in der Seite das Papierkorb-Symbol daneben oder **„Durch Auflegen löschen“**.
- **Badges sichern**: „Liste sichern“ speichert eine CSV-Datei (öffnet sich in Excel oder LibreOffice); „Liste
  wiederherstellen“ lädt sie wieder.

| Ton | Bedeutung |
| --- | --- |
| 1 hoher Piepton | Zuordnungsmodus aktiv |
| 2 steigende Pieptöne | Badge zugeordnet |
| 1 mittlerer Piepton | Badge erkannt, ohne Aktion (`action = none`) |
| kein Ton | ein Spiel startet: sein Ladebildschirm genügt |
| 2 tiefe Pieptöne | Löschmodus aktiv |
| 2 fallende tiefe Pieptöne | unbekannter Badge oder abgelehnte Aktion |
| 3 fallende Pieptöne | Zeit abgelaufen (10 s zum Auflegen) |

## 🖨️ Karten, Sonderkarten und Spielzeit

- **Spiel suchen** (Tab Badges): ein paar Buchstaben eingeben, dann dem Spiel einen Badge zuordnen, ohne Fernseher.
  Praktisch auf dem Telefon: `http://recalbox.local:8765/` öffnen (oder den QR-Code der Telefon-Taste in der Kopfzeile
  scannen).
- **Karten drucken** (Tab Karten): Spiel und Vorlage wählen, quer oder hoch; ein Element der Karte antippen, um es zu
  verschieben, zu vergrößern oder zu drehen; ein gelber Streifen zeigt den Teil, der aus dem Schlitz ragt. Das Layout
  als Vorlage speichern, die Karten zum Druckbogen hinzufügen, dann mit 100 % drucken (zehn Karten pro A4-Blatt).
- **Sonderkarten** (Tab Badges): Zufallsspiel, Bonuszeit, Spiel beenden, Recalbox ausschalten.
- **Spielzeit**: Einstellungen › Spielzeit pro Partie, oder pro Badge mit dem Stift. Die Recalbox warnt 5 und 1 Minute
  vor dem Ende und beendet dann das Spiel; eine Bonuskarte fügt Minuten hinzu, begrenzt oft pro Tag, Woche…

Details: [docs/USAGE.md](docs/USAGE.md) (auf Englisch).

## 🔄 Aktualisieren

In der Seite, Tab **Updates** › **„Auf X aktualisieren“**: Die Seite sendet das Programm, das sie enthält. Badges und
Einstellungen bleiben erhalten, und die Seite verbindet sich selbst wieder. Andere Wege (ZIP-Datei, Adresse, SSH):
[docs/UPDATING.md](docs/UPDATING.md) (auf Englisch).

## 🗑️ Deinstallieren

- **Recalbox 10**: `START` › Erweiterte Einstellungen › Benutzerskripte › **Uninstall-RFID-reader**. Badges und
  Einstellungen bleiben erhalten, und *Install-RFID-reader* bleibt im Menü, um mit einem Klick neu zu installieren.
- **Alles, inklusive Daten** (SSH): `sh /recalbox/share/system/rfid/uninstall.sh --remove-spi`

## 🩺 Fehlerbehebung

| Symptom | Was tun |
| --- | --- |
| Windows schlägt bei `\\RECALBOX` „Diagnose“ vor | Netzwerkprofil *Öffentlich*: auf *Privat* stellen oder die IP-Adresse nutzen |
| Die Seite findet die Recalbox nicht | selbes Netzwerk? IP-Adresse statt `recalbox.local` versuchen |
| „Leser nicht gefunden“ | Verkabelung, 3,3 V, dann Tab **Hardware** › „Mit einem Badge testen“ |
| Der Badge wird nicht gelesen | er muss 13,56 MHz haben; eine kontaktlose Bankkarte testet den Leser |
| Die Taste reagiert nicht | GPIO17 von GPIO-Controllern belegt (`controllers.gpio.enabled=0`), Verkabelung zu GND |
| Das Spiel startet nicht | Recalbox 9 oder neuer nötig; das Spiel muss *ausgewählt* sein, kein Ordner |
| Die Seite verlangt erneut eine Freigabe | die Recalbox wurde neu gestartet: Gehäusetaste 3 Sekunden halten |

Vollständige Anleitung: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) (auf Englisch).

## 🛠️ Für Entwickler

Alles lässt sich auf einem PC testen, ohne Raspberry Pi:

```sh
python app/main.py --home ./data config-init
python app/main.py --home ./data simulate      # simulierter Leser und Taste
python tests/run_tests.py                      # Unit-Tests, keine Hardware nötig
python tools/build_installer.py                # erzeugt dist/recalbox-rfid-installer.html neu
```

Auf der Recalbox wird das Kommandozeilenwerkzeug immer über `sh` aufgerufen (die exFAT-Freigabe speichert kein
Ausführungsrecht): `sh /recalbox/share/system/rfid/rfidctl help`.

Funktionsweise in Kürze:

- **Badge lesen**: MFRC522-Treiber in reinem Python über `/dev/spidev0.0` (`ioctl` über `ctypes`), Ablauf nach
  ISO 14443-3A, tolerant gegenüber geklonten Badges.
- **Ausgewähltes Spiel**: gelesen aus `/tmp/es_state.inf`, das das Recalbox-Frontend bei jedem Ereignis schreibt.
- **Spielstart**: UDP-Datagramm `START|<System>|<vollständiger Pfad>` an `127.0.0.1:1337`, der offizielle
  Frontend-Befehl.
- **Seite ↔ Recalbox**: ein WebSocket-Agent mit der Standardbibliothek; die Seite wird lokal geöffnet (`file://`) und
  ein Computer durch einen physischen Tastendruck freigegeben (Sitzungsgeheimnis im Speicher).
- **Start**: zwei dauerhafte Recalbox-Benutzerskripte (Dienst + Agent) und unter Recalbox 10 zwei Menüskripte
  (installieren / deinstallieren).

Veröffentlichung auf GitHub (Pages und Releases): [docs/PUBLISHING.md](docs/PUBLISHING.md). Die ausführlichen
Dokumente in `docs/` und die [Versionsgeschichte](CHANGELOG.md) sind auf Englisch.

## 📚 Dokumentation

- [docs/WIRING.md](docs/WIRING.md): Verkabelung im Detail, Pin-Wahl und Statusleuchte
- [docs/INSTALLATION.md](docs/INSTALLATION.md): Installation Schritt für Schritt (Windows, macOS, Linux)
- [docs/USAGE.md](docs/USAGE.md): Zuordnung, Karten zum Drucken, Sonderkarten, Spielzeit, Befehle, Konfiguration
- [docs/UPDATING.md](docs/UPDATING.md): Updates und Rückkehr zu einer älteren Version
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md): Diagnose und Lösungen
- [docs/PUBLISHING.md](docs/PUBLISHING.md): GitHub Pages und Releases
