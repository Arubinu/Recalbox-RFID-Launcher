"""Another time per day on some days and in the holidays; the guest card."""

from __future__ import annotations

import time
import unittest

import support  # noqa: F401 - puts app/ on the path
from rfid.players import Players, day_quota, guest_expired
from rfid.storage import StorageError, clean_params

#: Wednesday 11 and Saturday 14 November 2026, at noon (local time).
WEDNESDAY = time.mktime((2026, 11, 11, 12, 0, 0, 0, 0, -1))
SATURDAY = time.mktime((2026, 11, 14, 12, 0, 0, 0, 0, -1))
CARD = {"quota_min": 30, "period": "day", "alt_min": 90}


class DayQuotaTest(unittest.TestCase):
    def test_semaine_et_week_end(self):
        self.assertEqual(day_quota(CARD, WEDNESDAY), 30)
        self.assertEqual(day_quota(CARD, SATURDAY), 90, "le week-end par defaut")
        self.assertEqual(day_quota(dict(CARD, alt_days=[2]), WEDNESDAY), 90, "jours choisis")
        self.assertEqual(day_quota({"quota_min": 30}, SATURDAY), 30, "sans autre temps")
        self.assertEqual(day_quota(dict(CARD, period="week"), SATURDAY), 30, "pas pour un temps par semaine")
        self.assertEqual(day_quota(dict(CARD, alt_min=0), SATURDAY), 0, "0 = sans limite ces jours-la")

    def test_vacances(self):
        self.assertEqual(day_quota(CARD, WEDNESDAY, holidays=("2026-11-09", "2026-11-13")), 90)
        self.assertEqual(day_quota(CARD, WEDNESDAY, holidays=("2026-11-12", "2026-11-13")), 30)
        self.assertEqual(day_quota(CARD, WEDNESDAY, holidays=("2026-11-11", "")), 90, "un seul jour")

    def test_heure_de_remise_a_zero(self):
        early_saturday = time.mktime((2026, 11, 14, 3, 0, 0, 0, 0, -1))
        self.assertEqual(day_quota(CARD, early_saturday, reset_hour=4), 30, "avant 4 h : encore vendredi")

    def test_joueurs(self):
        wall = support.FakeClock(SATURDAY)
        players = Players(None, wall=wall, clock=support.FakeClock())
        self.assertEqual(players.quota_of(CARD), 90)
        status = players.status([("P1", {"name": "Lea", "params": CARD})])
        self.assertEqual(status["players"][0]["quota_min"], 90, "la page voit le temps du jour")


class GuestCardTest(unittest.TestCase):
    def test_date_de_fin(self):
        card = {"guest": True, "until": "2026-11-13"}
        self.assertFalse(guest_expired(card, WEDNESDAY))
        self.assertTrue(guest_expired(card, SATURDAY))
        self.assertFalse(guest_expired({"guest": True}, SATURDAY), "sans date : toujours valable")

    def test_validation(self):
        params = clean_params("player", {"quota_min": 45, "guest": True, "until": "2026-11-13"})
        self.assertEqual(params["until"], "2026-11-13")
        self.assertTrue(params["guest"])
        with self.assertRaises(StorageError):
            clean_params("player", {"quota_min": 45, "guest": True, "until": "13/11/2026"})
        params = clean_params("player", {"quota_min": 30, "alt_min": 90, "alt_days": [5, 6]})
        self.assertEqual(params["alt_min"], 90)
        self.assertNotIn("alt_days", params, "le week-end : rien a ecrire")
        params = clean_params("player", {"quota_min": 30, "alt_min": None})
        self.assertNotIn("alt_min", params)
        params = clean_params("player", {"quota_min": 30, "period": "week", "alt_min": 90})
        self.assertNotIn("alt_min", params, "pas pour un temps par semaine")


if __name__ == "__main__":
    unittest.main()
