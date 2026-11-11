#!/usr/bin/env python3
"""Lance toute la suite de tests : ``python3 tests/run_tests.py``."""

from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)

for path in (HERE, os.path.join(PROJECT, "app")):
    if path not in sys.path:
        sys.path.insert(0, path)


def main() -> int:
    suite = unittest.TestLoader().discover(HERE, pattern="test_*.py", top_level_dir=HERE)
    print("=" * 70)
    print(" Tests unitaires -- Recalbox RFID Launcher")
    print("=" * 70)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print()
    if result.wasSuccessful():
        print("Tous les tests sont passes (%d tests)." % result.testsRun)
        return 0
    print("Echecs : %d, erreurs : %d" % (len(result.failures), len(result.errors)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
