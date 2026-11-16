"""/sys/class/gpio: the pins are numbered from the base of the Pi's chip."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

import support  # noqa: F401 - puts app/ on the path
from rfid.drivers.gpio_backend import SysfsBackend, chip_base


class SysfsBaseTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rfid-gpio-")
        self.addCleanup(shutil.rmtree, self.root, True)
        for name in ("export", "unexport"):
            open(os.path.join(self.root, name), "w").close()

    def chip(self, base, label):
        folder = os.path.join(self.root, "gpiochip%d" % base)
        os.makedirs(folder)
        for leaf, value in (("base", base), ("label", label)):
            with open(os.path.join(folder, leaf), "w") as handle:
                handle.write("%s\n" % value)

    def test_noyau_recent(self):
        self.chip(568, "raspberrypi-exp-gpio")
        self.chip(512, "pinctrl-bcm2835")
        self.chip(566, "brcmvirt-gpio")
        self.assertEqual(chip_base(self.root), 512)
        backend = SysfsBackend(self.root)
        backend._export(17)
        with open(os.path.join(self.root, "export")) as handle:
            self.assertEqual(handle.read(), "529", "BCM 17 = 512 + 17")
        self.assertTrue(backend._path(17, "value").endswith(os.path.join("gpio529", "value")))

    def test_ancien_noyau(self):
        self.chip(0, "pinctrl-bcm2835")
        self.assertEqual(chip_base(self.root), 0)
        self.assertEqual(chip_base(os.path.join(self.root, "absent")), 0)


if __name__ == "__main__":
    unittest.main()
