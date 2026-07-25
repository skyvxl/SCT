from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from sct.steam import (
    STEAM_ID64_BASE,
    SteamService,
    parse_loginusers,
    steam_id64_from_account_id,
)


class SteamTests(unittest.TestCase):
    def test_loginusers_parser_returns_local_profiles_without_losing_unicode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "loginusers.vdf"
            path.write_text(
                '"users"\n'
                "{\n"
                '  "76561198000000001"\n'
                "  {\n"
                '    "AccountName" "first"\n'
                '    "PersonaName" "Игрок Один"\n'
                '    "MostRecent" "1"\n'
                "  }\n"
                '  "76561198000000002"\n'
                "  {\n"
                '    "AccountName" "second"\n'
                '    "PersonaName" "Player Two"\n'
                '    "MostRecent" "0"\n'
                "  }\n"
                "}\n",
                encoding="utf-8",
            )

            profiles = parse_loginusers(path)

            self.assertEqual(
                [profile.steam_id for profile in profiles],
                [
                    "76561198000000001",
                    "76561198000000002",
                ],
            )
            self.assertEqual(profiles[0].persona_name, "Игрок Один")
            self.assertTrue(profiles[0].most_recent)

    def test_account_id_is_converted_to_steam_id64(self) -> None:
        self.assertEqual(
            steam_id64_from_account_id(12345),
            str(STEAM_ID64_BASE + 12345),
        )
        self.assertIsNone(steam_id64_from_account_id(0))

    def test_auto_detect_uses_standard_program_files_location(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "Steam" / "Steam.exe"
            executable.parent.mkdir()
            executable.touch()
            with patch.dict("os.environ", {"PROGRAMFILES(X86)": directory}):
                detected = SteamService().detect_executable()

        self.assertEqual(detected, executable)

    def test_status_check_matches_steam_from_in_process_enumeration(self) -> None:
        service = SteamService(
            process_names=lambda: ("System", "explorer.exe", "Steam.EXE")
        )

        self.assertTrue(service.is_running())

    def test_status_check_does_not_match_similarly_named_process(self) -> None:
        service = SteamService(
            process_names=lambda: ("steamwebhelper.exe", "not-steam.exe")
        )

        self.assertFalse(service.is_running())

    def test_silent_start_and_game_launch_use_expected_process_arguments(self) -> None:
        popen = Mock()
        service = SteamService(start_process=popen)

        service.start(r"C:\Steam\Steam.exe", silently=True)
        service.launch_game(r"C:\Games\ELDEN RING\Game\ersc_launcher.exe")

        steam_call, game_call = popen.call_args_list
        self.assertEqual(steam_call.args[0], [r"C:\Steam\Steam.exe", "-silent"])
        self.assertEqual(
            game_call.args[0],
            [r"C:\Games\ELDEN RING\Game\ersc_launcher.exe"],
        )
        self.assertEqual(game_call.kwargs["cwd"], r"C:\Games\ELDEN RING\Game")

    def test_batch_launch_uses_command_processor_and_game_directory(self) -> None:
        popen = Mock()
        service = SteamService(start_process=popen)

        with patch.dict("os.environ", {"COMSPEC": r"C:\Windows\System32\cmd.exe"}):
            service.launch_game(r"C:\Games\ELDEN RING\Game\launchmod_eldenring.bat")

        popen.assert_called_once_with(
            [
                r"C:\Windows\System32\cmd.exe",
                "/d",
                "/s",
                "/c",
                "launchmod_eldenring.bat",
            ],
            cwd=r"C:\Games\ELDEN RING\Game",
        )


if __name__ == "__main__":
    unittest.main()
