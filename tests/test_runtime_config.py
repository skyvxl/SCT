from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sct.runtime_config import RuntimeConfig, RuntimeConfigError


class RuntimeConfigTests(unittest.TestCase):
    def test_process_environment_takes_precedence_over_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dotenv = Path(directory) / ".env"
            dotenv.write_text(
                "ERSC_RELEASE_API_URL=https://example.invalid/from-file\n",
                encoding="utf-8",
            )

            config = RuntimeConfig.load(
                environment={"ERSC_RELEASE_API_URL": "https://example.invalid/from-env"},
                search_paths=(dotenv,),
            )

        self.assertEqual(config.ersc_release_api_url, "https://example.invalid/from-env")

    def test_dotenv_is_used_when_environment_value_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dotenv = Path(directory) / ".env"
            dotenv.write_text(
                '# comment\nERSC_RELEASE_API_URL="https://example.invalid/releases/latest"\n',
                encoding="utf-8",
            )

            config = RuntimeConfig.load(environment={}, search_paths=(dotenv,))

        self.assertEqual(
            config.ersc_release_api_url,
            "https://example.invalid/releases/latest",
        )

    def test_missing_release_url_is_reported(self) -> None:
        with self.assertRaises(RuntimeConfigError) as caught:
            RuntimeConfig.load(environment={}, search_paths=())
        self.assertEqual(caught.exception.code, "runtime_config_invalid")


if __name__ == "__main__":
    unittest.main()
