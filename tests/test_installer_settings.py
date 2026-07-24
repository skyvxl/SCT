from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sct.installer_settings import merge_ersc_settings


class InstallerSettingsTests(unittest.TestCase):
    def test_uses_new_template_and_overlays_all_existing_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "template.ini"
            existing = root / "existing.ini"
            destination = root / "installed" / "ersc_settings.ini"
            template.write_text(
                "# New release documentation stays here\n"
                "[GAMEPLAY]\n"
                "allow_invaders = 1\n"
                "new_setting = 7\n"
                "\n"
                "[PASSWORD]\n"
                "cooppassword = template\n",
                encoding="utf-8",
            )
            existing.write_text(
                "[GAMEPLAY]\n"
                "allow_invaders = 0\n"
                "legacy_setting = 42\n"
                "\n"
                "[PASSWORD]\n"
                "cooppassword = old-password\n"
                "\n"
                "[CUSTOM]\n"
                "keep_me = yes\n",
                encoding="utf-8",
            )

            merge_ersc_settings(template, existing, destination, "new-password")

            document = destination.read_text(encoding="utf-8")
        self.assertIn("# New release documentation stays here", document)
        self.assertIn("allow_invaders = 0", document)
        self.assertIn("new_setting = 7", document)
        self.assertIn("legacy_setting = 42", document)
        self.assertIn("[CUSTOM]", document)
        self.assertIn("keep_me = yes", document)
        self.assertIn("cooppassword = new-password", document)
        self.assertNotIn("old-password", document)

    def test_works_without_existing_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "template.ini"
            destination = root / "result.ini"
            template.write_text(
                "[PASSWORD]\ncooppassword = template\n",
                encoding="utf-8",
            )

            merge_ersc_settings(template, None, destination, "12345")

            self.assertIn(
                "cooppassword = 12345",
                destination.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
