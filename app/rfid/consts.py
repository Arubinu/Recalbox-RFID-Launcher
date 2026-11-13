"""Shared constants of the project."""

from __future__ import annotations

import os

#: Default install folder on Recalbox (persistent, visible from the Windows
#: network share: \\\\RECALBOX\\share\\system\\rfid).
DEFAULT_HOME = "/recalbox/share/system/rfid"

#: State file written by the Recalbox frontend on every event.
ES_STATE_FILE = "/tmp/es_state.inf"

#: Official UDP command of the Recalbox frontend (Recalbox 9 and later).
ES_UDP_HOST = "127.0.0.1"
ES_UDP_PORT = 1337

#: Lock preventing two service instances (tmpfs, reset at reboot).
LOCK_FILE = "/var/run/rfid-launcher.lock"

#: Configuration file name.
CONFIG_FILENAME = "config.ini"

#: Automatic reader tuning state (written by the service, read by the agent).
CALIBRATION_FILENAME = "calibration.json"

#: Values from before the automatic tuning (to go back).
CALIBRATION_BACKUP_FILENAME = "calibration-backup.json"

#: Database file name.
DB_FILENAME = "tags.json"

#: Log folder.
LOG_DIRNAME = "logs"

#: Legacy WebSocket agent access token (in the install folder; removed at startup).
TOKEN_FILENAME = "token.txt"

#: Command queue between the WebSocket agent and the RFID service.
AGENT_COMMAND_FILENAME = "agent-command.json"
#: Reader test result (written by the service, read by the agent).
READER_TEST_FILENAME = "reader-test.json"

#: Default port of the WebSocket agent.
AGENT_PORT = 8765


def home_dir() -> str:
    """Returns the working folder (can be overridden with RFID_HOME)."""
    return os.environ.get("RFID_HOME", DEFAULT_HOME)


def config_path() -> str:
    return os.path.join(home_dir(), CONFIG_FILENAME)


def db_path() -> str:
    return os.path.join(home_dir(), DB_FILENAME)


def log_dir() -> str:
    return os.path.join(home_dir(), LOG_DIRNAME)
