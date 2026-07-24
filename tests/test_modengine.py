from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sct.modengine import ModEngineConfig, ModEngineConfigError


class ModEngineConfigTests(unittest.TestCase):
    def test_lists_active_and_commented_external_dlls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config_eldenring.toml"
            path.write_text(
                "[modengine]\n"
                "debug = false\n"
                "external_dlls = [\n"
                '    "SeamlessCoop\\\\ersc.dll",\n'
                '    # "mods\\\\disabled.dll",\n'
                '    "mods\\\\active.dll"\n'
                "]\n"
                "[extension.mod_loader]\n"
                "enabled = true\n",
                encoding="utf-8",
            )

            dlls = ModEngineConfig(path).list_dlls()

        self.assertEqual(
            [(dll.path, dll.enabled, dll.locked) for dll in dlls],
            [
                (r"SeamlessCoop\ersc.dll", True, True),
                (r"mods\disabled.dll", False, False),
                (r"mods\active.dll", True, False),
            ],
        )

    def test_ensure_ersc_uncomments_existing_entry_and_preserves_other_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config_eldenring.toml"
            path.write_text(
                "[modengine]\n"
                "external_dlls = [\n"
                '    # "SeamlessCoop\\\\ersc.dll"\n'
                "]\n"
                "# keep this comment\n",
                encoding="utf-8",
            )

            ModEngineConfig(path).ensure_ersc()

            document = path.read_text(encoding="utf-8")
        self.assertIn('    "SeamlessCoop\\\\ersc.dll"', document)
        self.assertNotIn('# "SeamlessCoop', document)
        self.assertIn("# keep this comment", document)

    def test_ensure_ersc_creates_missing_array(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config_eldenring.toml"
            path.write_text("[modengine]\ndebug = false\n", encoding="utf-8")

            ModEngineConfig(path).ensure_ersc()

            document = path.read_text(encoding="utf-8")
        self.assertIn("external_dlls = [", document)
        self.assertIn('"SeamlessCoop\\\\ersc.dll"', document)
        self.assertIn("debug = false", document)

    def test_toggles_regular_dll_but_refuses_to_disable_ersc(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config_eldenring.toml"
            path.write_text(
                "[modengine]\n"
                "external_dlls = [\n"
                '    "SeamlessCoop\\\\ersc.dll",\n'
                '    "mods\\\\toggle.dll"\n'
                "]\n",
                encoding="utf-8",
            )
            config = ModEngineConfig(path)

            config.set_enabled(r"mods\toggle.dll", False)
            self.assertFalse(config.list_dlls()[1].enabled)
            config.set_enabled(r"mods\toggle.dll", True)
            self.assertTrue(config.list_dlls()[1].enabled)
            with self.assertRaises(ModEngineConfigError):
                config.set_enabled(r"SeamlessCoop\ersc.dll", False)


if __name__ == "__main__":
    unittest.main()
