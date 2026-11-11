#!/usr/bin/env python3
"""Recalbox RFID Launcher -- point d'entree en ligne de commande.

Exemples :

    python3 app/main.py test                 # diagnostic du cablage
    python3 app/main.py list                 # liste des badges
    python3 app/main.py add A1B2C3D4 --current
    python3 app/main.py remove A1B2C3D4
    python3 app/main.py daemon               # service (lancé par Recalbox)
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time

if __package__ in (None, ""):  # execution directe : python3 app/main.py
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rfid import __version__  # noqa: E402
from rfid import consts  # noqa: E402
from rfid.config import Config, ConfigError  # noqa: E402
from rfid.daemon import (  # noqa: E402
    pid_path,
    process_alive,
    read_pid,
    read_status,
)
from rfid.esbridge import (  # noqa: E402
    EsLauncher,
    current_target,
    read_state,
    supports_start_command,
)
from rfid.feedback import Feedback  # noqa: E402
from rfid.logutil import Logger  # noqa: E402
from rfid.storage import StorageError, TagStore, normalize_uid, pretty_uid  # noqa: E402

PROGRAM = "rfidctl"
LINE = "=" * 72

USAGE = """\
Recalbox RFID Launcher %s

Utilisation :
  %s <commande> [options] [arguments]

Commandes :
  test                     Verifie le lecteur, le bouton et le frontend
  list                     Liste les badges enregistres
  add <UID> [SYSTEME] [JEU] [NOM]
                           Associe un badge (--current pour le jeu selectionne)
  remove <UID>             Supprime un badge
  export <fichier.csv>     Exporte les associations
  import <fichier.csv>     Importe des associations
  status                   Etat du service
  start | stop | restart   Gere le service
  logs                     Affiche les dernieres lignes du journal
  frontend                 Verifie que Recalbox sait lancer un jeu par script
  self-update [URL]        Met a jour le programme (ZIP en ligne ou dossier copie)
  simulate                 Mode simulation (test sur PC, sans Raspberry Pi)
  config                   Affiche la configuration effective
  config-init              Ecrit le fichier de configuration par defaut
  version                  Version du programme

Options :
  --home <dossier>         Dossier de travail (defaut : %s)
  --config <fichier>       Fichier de configuration
  --db <fichier>           Base des badges
  -v, --verbose            Affiche les details
""" % (__version__, PROGRAM, consts.DEFAULT_HOME)


class Options:
    def __init__(self):
        self.home = consts.home_dir()
        self.config = None
        self.db = None
        self.verbose = False
        self.command = "help"
        self.args = []

    def resolve(self):
        self.home = os.path.abspath(self.home)
        if not self.config:
            self.config = os.path.join(self.home, consts.CONFIG_FILENAME)
        if not self.db:
            self.db = os.path.join(self.home, consts.DB_FILENAME)


def parse_args(argv):
    options = Options()
    positional = []
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument in ("-h", "--help"):
            options.command = "help"
            return options
        if argument in ("--home", "--config", "--db"):
            if index + 1 >= len(argv):
                raise SystemExit("option %s : valeur manquante" % argument)
            value = argv[index + 1]
            if argument == "--home":
                options.home = value
            elif argument == "--config":
                options.config = value
            else:
                options.db = value
            index += 2
            continue
        if argument in ("-v", "--verbose"):
            options.verbose = True
            index += 1
            continue
        if argument.startswith("-"):
            raise SystemExit("option inconnue : %s" % argument)
        positional.append(argument)
        index += 1

    options.resolve()
    if positional:
        options.command = positional[0]
        options.args = positional[1:]
    return options


# ---------------------------------------------------------------------------
# Aides
# ---------------------------------------------------------------------------
def make_logger(options, echo=None) -> Logger:
    log_file = os.path.join(options.home, consts.LOG_DIRNAME, "rfid.log")
    log_level = "DEBUG" if options.verbose else "INFO"
    max_bytes = 1048576
    try:
        config = Config(options.config)
        log_level = "DEBUG" if options.verbose else config.get("general", "log_level", "INFO")
        max_bytes = config.get_int("general", "log_max_bytes", 1048576)
    except ConfigError:
        pass
    return Logger(log_file, log_level, max_bytes, echo=bool(echo) or options.verbose)


def load_config(options) -> Config:
    config = Config(options.config)
    if not config.exists():
        config.create_default()
    return config


def load_store(options) -> TagStore:
    store = TagStore(options.db)
    store.load()
    return store


def print_table(rows, headers):
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(str(cell)))
    template = "  ".join("%%-%ds" % width for width in widths)
    print(template % tuple(headers))
    print(template % tuple("-" * width for width in widths))
    for row in rows:
        print(template % tuple(str(cell) for cell in row))


# ---------------------------------------------------------------------------
# Commandes
# ---------------------------------------------------------------------------
def cmd_version(options) -> int:  # noqa: ARG001
    print("Recalbox RFID Launcher %s" % __version__)
    print("Python %s" % sys.version.split()[0])
    print("Dossier : %s" % options.home)
    return 0


def cmd_config(options) -> int:
    config = load_config(options)
    print("Fichier : %s" % options.config)
    for section in sorted(config.section_list()):
        print("\n[%s]" % section)
        for key, value in sorted(config.section(section).items()):
            print("  %s = %s" % (key, value))
    return 0


def cmd_config_init(options) -> int:
    config = Config(options.config)
    created = config.create_default(overwrite=False)
    if created:
        print("Configuration ecrite : %s" % options.config)
    else:
        print("La configuration existe deja : %s" % options.config)
    return 0


def cmd_list(options) -> int:
    store = load_store(options)
    if store.count() == 0:
        print("Aucun badge enregistre pour le moment.")
        print("Utilisez le bouton poussoir dans Recalbox, ou : %s add <UID> --current" % PROGRAM)
        return 0
    rows = []
    for uid, entry in store.items():
        rows.append(
            (
                pretty_uid(uid),
                entry["system"],
                entry["name"] or entry["game"],
                entry.get("hits", 0),
                entry.get("last_used") or "-",
            )
        )
    print_table(rows, ["Badge", "Systeme", "Jeu", "Scans", "Dernier usage"])
    print("\n%d association(s) -- base : %s" % (store.count(), options.db))
    return 0


def cmd_add(options) -> int:
    store = load_store(options)
    args = list(options.args)
    use_current = False
    if "--current" in args:
        args.remove("--current")
        use_current = True

    if use_current:
        if not args:
            return usage_error("UID du badge manquant")
        uid = args[0]
        target = current_target(read_state())
        if target is None:
            print("Aucun jeu selectionne dans Recalbox : choisissez un jeu, puis relancez.")
            return 1
        system, game, name, path = target.system, target.game, target.name, target.path
    else:
        if len(args) < 3:
            print("Usage : %s add <UID> <SYSTEME> <JEU> [NOM]" % PROGRAM)
            print("        %s add <UID> --current   (jeu selectionne dans Recalbox)" % PROGRAM)
            return 2
        uid, system, game = args[0], args[1], args[2]
        name = args[3] if len(args) > 3 else os.path.basename(game)
        path = "/recalbox/share/roms/%s/%s" % (system, game)

    try:
        EsLauncher.build_payload(system, game)
        entry = store.put(uid, system, game, name, path)
    except (StorageError, ValueError) as exc:
        print("Erreur : %s" % exc)
        return 1
    print("Badge %s associe a %s (%s / %s)" % (pretty_uid(normalize_uid(uid)), entry["name"], system, game))
    return 0


def cmd_remove(options) -> int:
    if not options.args:
        return usage_error("UID du badge manquant")
    store = load_store(options)
    uid = options.args[0]
    if store.delete(uid):
        print("Badge %s supprime." % pretty_uid(normalize_uid(uid)))
        return 0
    print("Badge %s inconnu." % pretty_uid(normalize_uid(uid)))
    return 1


def cmd_export(options) -> int:
    if not options.args:
        return usage_error("fichier destination manquant")
    store = load_store(options)
    count = store.export_csv(options.args[0])
    print("%d association(s) exportee(s) vers %s" % (count, options.args[0]))
    return 0


def cmd_import(options) -> int:
    if not options.args:
        return usage_error("fichier source manquant")
    overwrite = "--keep" not in options.args
    source = [arg for arg in options.args if arg != "--keep"][0]
    store = load_store(options)
    try:
        stats = store.import_csv(source, overwrite=overwrite)
    except (OSError, StorageError) as exc:
        print("Import impossible : %s" % exc)
        return 1
    print(
        "Import termine : %d ajoute(s), %d mis a jour, %d ignore(s)"
        % (stats["ajoutes"], stats["mis_a_jour"], stats["ignores"])
    )
    return 0


def cmd_logs(options) -> int:
    path = os.path.join(options.home, consts.LOG_DIRNAME, "rfid.log")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()[-40:]
    except OSError:
        print("Aucun journal : %s" % path)
        return 1
    sys.stdout.writelines(lines)
    return 0


def cmd_status(options) -> int:
    pid = read_pid(options.home)
    alive = process_alive(pid)
    status = read_status(options.home)
    print("Service      : %s" % ("en marche (PID %d)" % pid if alive else "arrete"))
    print("Dossier      : %s" % options.home)
    print("Configuration: %s" % options.config)
    print("Base badges  : %s" % options.db)
    if status and alive:
        print("Depuis       : %s (%s s)" % (status.get("started", "?"), status.get("uptime_s", "?")))
        print("Lecteur      : %s" % (status.get("reader") or "non detecte"))
        print("Bouton       : %s" % ("OK" if status.get("button") else "indisponible"))
        print("Badges       : %s" % status.get("tags", "?"))
        if status.get("last_uid"):
            print(
                "Dernier badge: %s (%s)"
                % (pretty_uid(status["last_uid"]), status.get("last_uid_at", "?"))
            )
        controller = status.get("controller") or {}
        if controller.get("mode"):
            print(
                "Mode         : %s -> %s (%ss restantes)"
                % (controller.get("mode"), controller.get("target"), controller.get("seconds_left"))
            )
    if not alive:
        print("\nDemarrez le service avec : %s start" % PROGRAM)
    return 0 if alive else 1


def cmd_start(options) -> int:
    pid = read_pid(options.home)
    if process_alive(pid):
        print("Le service tourne deja (PID %d)." % pid)
        return 0
    os.makedirs(os.path.join(options.home, consts.LOG_DIRNAME), exist_ok=True)
    out_path = os.path.join(options.home, consts.LOG_DIRNAME, "service.out")
    command = [sys.executable, os.path.abspath(__file__), "daemon", "--home", options.home]
    if options.config:
        command += ["--config", options.config]
    if options.db:
        command += ["--db", options.db]
    with open(out_path, "ab") as output:
        process = subprocess.Popen(
            command,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
    time.sleep(1.5)
    if process.poll() is None:
        print("Service demarre (PID %d). Journal : %s" % (process.pid, out_path))
        return 0
    print("Le service n'a pas demarre. Consultez %s" % out_path)
    return 1


def cmd_stop(options) -> int:
    pid = read_pid(options.home)
    if not process_alive(pid):
        print("Le service n'est pas en marche.")
        try:
            os.remove(pid_path(options.home))
        except OSError:
            pass
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        print("Arret impossible (PID %d) : %s" % (pid, exc))
        return 1
    for _ in range(50):
        if not process_alive(pid):
            print("Service arrete.")
            return 0
        time.sleep(0.1)
    print("Le service ne repond pas (PID %d) : utilisez kill -9 %d" % (pid, pid))
    return 1


def cmd_restart(options) -> int:
    cmd_stop(options)
    time.sleep(0.5)
    return cmd_start(options)


def cmd_test(options) -> int:
    config = load_config(options)
    log = make_logger(options, echo=True)
    print(LINE)
    print(" Diagnostic du lecteur RFID Recalbox")
    print(LINE)
    print("Version            : %s" % __version__)
    print("Dossier            : %s" % options.home)
    print("Configuration      : %s%s" % (options.config, "" if config.exists() else " (defaut)"))
    print("Base de badges     : %s (%d entree(s))" % (options.db, load_store(options).count()))

    recalbox = "inconnue"
    try:
        with open("/recalbox/recalbox.version", "r", encoding="utf-8") as handle:
            recalbox = handle.read().strip()
    except OSError:
        pass
    print("Recalbox           : %s" % recalbox)
    if os.path.exists("/usr/bin/emulationstation"):
        support = supports_start_command()
        print("Lancement UDP      : %s" % ("disponible" if support else "INDISPONIBLE (Recalbox < 9 ?)"))
    else:
        print("Lancement UDP      : hors Recalbox (mode simulation)")

    result = 0
    device = config.get("rfid", "spi_device", "/dev/spidev0.0")
    print("\n--- Lecteur RC522 (%s) ---" % device)
    if not os.path.exists(device):
        print("  Le peripherique SPI n'existe pas.")
        print("  Ajoutez 'dtparam=spi=on' dans /boot/recalbox-user-config.txt puis redemarrez.")
        result = 1
    else:
        try:
            from rfid.hardware import build_gpio, build_reader

            gpio = build_gpio(config, log)
            reader = build_reader(config, log, gpio)
            version = reader.start()
            print("  Version du MFRC522 : 0x%02X" % version)
            print("  Posez un badge sur le lecteur (attente 8 secondes)...")
            deadline = time.time() + 8
            uid = None
            while time.time() < deadline and uid is None:
                uid = reader.read_uid()
            if uid:
                print("  Badge detecte : %s" % pretty_uid(uid))
            else:
                print("  Aucun badge detecte (cablage ou alimentation 3.3 V a verifier).")
                result = 1
            reader.close()
        except Exception as exc:  # noqa: BLE001
            print("  Erreur : %s" % exc)
            result = 1

    print("\n--- Bouton poussoir (broche BCM %s) ---" % config.get("button", "pin", "17"))
    try:
        from rfid.hardware import build_button, build_gpio

        gpio = build_gpio(config, log)
        button = build_button(config, log, gpio)
        if button is None or not button.available:
            print("  Bouton indisponible (desactive ou broche non accessible).")
            result = result or 1
        else:
            print("  Backend GPIO : %s" % getattr(gpio, "name", "?"))
            print("  Etat actuel  : %s" % ("appuye" if button.is_pressed() else "relache"))
            print("  Appuyez sur le bouton (attente 8 secondes)...")
            deadline = time.time() + 8
            gesture = None
            while time.time() < deadline and gesture is None:
                gesture = button.poll()
                time.sleep(0.02)
            print("  Appui detecte : %s" % (gesture or "aucun"))
            button.close()
    except Exception as exc:  # noqa: BLE001
        print("  Erreur : %s" % exc)
        result = result or 1

    state = read_state()
    print("\n--- Frontend Recalbox ---")
    if state:
        target = current_target(state)
        print("  Fichier d'etat : present")
        print("  Jeu selectionne: %s" % (target.describe() if target else "aucun"))
    else:
        print("  Fichier d'etat introuvable (/tmp/es_state.inf) : Recalbox n'est pas demarre.")

    print("\n%s" % ("Diagnostic OK" if result == 0 else "Diagnostic incomplet : voir ci-dessus"))
    return result


# ---------------------------------------------------------------------------
# Simulation (test sur PC, sans materiel)
# ---------------------------------------------------------------------------
class PrintLauncher:
    """Remplace l'envoi UDP en mode simulation."""

    def __init__(self, log=None):
        self.log = log
        self.launched = []

    def start_game(self, system, game) -> bool:
        try:
            payload = EsLauncher.build_payload(system, game)
        except ValueError as exc:
            if self.log:
                self.log.error("Lancement refuse : %s" % exc)
            return False
        self.launched.append((system, game))
        print("  >> COMMANDE ENVOYEE : %s" % payload.decode("utf-8", "replace"))
        return True


def cmd_frontend(options) -> int:  # noqa: ARG001
    """Verifie le support de la commande de lancement UDP par le frontend."""
    if not os.path.exists("/usr/bin/emulationstation"):
        print("Frontend Recalbox introuvable (mode developpement, hors Recalbox).")
        return 2
    version = "inconnue"
    try:
        with open("/recalbox/recalbox.version", "r", encoding="utf-8") as handle:
            version = handle.read().strip()
    except OSError:
        pass
    supported = supports_start_command()
    print("Recalbox %s" % version)
    print("Commande de lancement UDP : %s" % ("disponible" if supported else "INDISPONIBLE"))
    if not supported:
        print("Le lancement de jeu necessite Recalbox 9 ou une version plus recente.")
    return 0 if supported else 1


def cmd_self_update(options) -> int:
    """Met a jour l'installation (ZIP en ligne ou dossier deja copie)."""
    installer = os.path.join(options.home, "install.sh")
    if not os.path.isfile(installer):
        print("Installeur introuvable : %s" % installer)
        return 1
    url = options.args[0] if options.args else ""
    if not url:
        try:
            url = Config(options.config).get("update", "url", "")
        except ConfigError:
            url = ""
    command = ["sh", installer, "--upgrade", "--home", options.home]
    if url:
        print("Mise a jour depuis : %s" % url)
        command += ["--from-url", url]
    else:
        print("Aucune URL fournie et aucune URL dans [update] url :")
        print("reinstallation de la version locale (%s)." % options.home)
    return subprocess.call(command)


def cmd_simulate(options) -> int:
    from rfid.controller import Controller
    from rfid.drivers.fake import FakeButton, FakeReader

    config = load_config(options)
    log = make_logger(options, echo=True)
    store = load_store(options)
    state_file = os.path.join(tempfile.gettempdir(), "rfid-sim-state.inf")

    def state_provider():
        return read_state(state_file)

    reader = FakeReader(log)
    launcher = PrintLauncher(log)
    feedback = Feedback(False, "none", log)
    controller = Controller(store, launcher, feedback, config, log, state_provider=state_provider)

    print(LINE)
    print(" Mode simulation -- aucun materiel n'est utilise")
    print(LINE)
    print("Commandes :")
    print("  select <systeme> <jeu>   choisit le jeu 'selectionne' dans Recalbox")
    print("  scan <uid>               simule la lecture d'un badge")
    print("  press                    simule un appui court (association)")
    print("  hold                     simule un appui long (effacement)")
    print("  list / status / help     affichage")
    print("  quit                     quitter")
    print("\nExemple complet :")
    print("  select snes 'Super Mario World.smc'")
    print("  press")
    print("  scan A1B2C3D4")
    print("  scan A1B2C3D4")
    print()

    def write_state(system, game):
        lines = [
            "Version=2.0",
            "Action=gamelistbrowsing",
            "SystemId=%s" % system,
            "Game=%s" % os.path.basename(game),
            "GamePath=/recalbox/share/roms/%s/%s" % (system, game),
            "IsFolder=0",
            "State=selected",
            "",
        ]
        with open(state_file, "w", encoding="utf-8") as handle:
            handle.write("\r\n".join(lines))

    while True:
        try:
            line = input("rfid> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            controller.tick()
            continue
        parts = line.split(None, 1)
        command = parts[0].lower()
        argument = parts[1] if len(parts) > 1 else ""

        if command in ("quit", "exit", "q"):
            break
        if command == "help":
            print("select <systeme> <jeu> | scan <uid> | press | hold | list | status | quit")
        elif command == "select":
            fields = argument.split(None, 1)
            if len(fields) < 2:
                print("Usage : select <systeme> <jeu>")
                continue
            system, game = fields[0], fields[1].strip().strip("'\"")
            write_state(system, game)
            print("Jeu selectionne : %s / %s" % (system, game))
        elif command == "scan":
            try:
                uid = normalize_uid(argument)
            except StorageError as exc:
                print("UID invalide : %s" % exc)
                continue
            outcome = controller.on_badge(uid)
            print("Resultat : %s" % outcome)
        elif command == "press":
            print("Resultat : %s" % controller.on_button("short"))
        elif command == "hold":
            print("Resultat : %s" % controller.on_button("long"))
        elif command == "list":
            if store.count() == 0:
                print("Aucun badge enregistre.")
            for uid, entry in store.items():
                print("  %s -> %s / %s" % (pretty_uid(uid), entry["system"], entry["game"]))
        elif command == "status":
            print("  Mode : %s" % controller.status())
        else:
            print("Commande inconnue : %s" % command)
        controller.tick()
    return 0


def usage_error(message: str) -> int:
    print("Erreur : %s" % message)
    return 2


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
COMMANDS = {
    "version": cmd_version,
    "config": cmd_config,
    "config-init": cmd_config_init,
    "list": cmd_list,
    "add": cmd_add,
    "remove": cmd_remove,
    "rm": cmd_remove,
    "export": cmd_export,
    "import": cmd_import,
    "logs": cmd_logs,
    "status": cmd_status,
    "start": cmd_start,
    "stop": cmd_stop,
    "restart": cmd_restart,
    "test": cmd_test,
    "frontend": cmd_frontend,
    "self-update": cmd_self_update,
    "simulate": cmd_simulate,
}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        options = parse_args(argv)
    except SystemExit as exc:
        print(exc)
        print(USAGE)
        return 2

    if options.command in ("help", "-h", "--help", ""):
        print(USAGE)
        return 0

    if options.command == "daemon":
        from rfid.daemon import run

        os.makedirs(options.home, exist_ok=True)
        try:
            config = load_config(options)
        except ConfigError as exc:
            print("Configuration invalide : %s" % exc)
            return 2
        log = make_logger(options, echo=False)
        return run(config, log, home=options.home, db=options.db)

    handler = COMMANDS.get(options.command)
    if handler is None:
        print("Commande inconnue : %s\n" % options.command)
        print(USAGE)
        return 2
    try:
        return handler(options)
    except ConfigError as exc:
        print("Configuration invalide : %s" % exc)
        return 2
    except KeyboardInterrupt:
        print()
        return 130


if __name__ == "__main__":
    sys.exit(main())
