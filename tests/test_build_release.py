from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.build_release import (
    REQUIRED_ITEM_FILES,
    LicenseComponent,
    ReleaseBuildError,
    ReleaseLayout,
    assemble_release,
    create_items_zip,
    create_release_zip,
    validate_items,
    write_release_environment,
    write_third_party_licenses,
)


class ReleaseBuildTests(unittest.TestCase):
    def test_validate_items_reports_all_missing_release_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            items = Path(temporary_directory)
            (items / "Weapons.csv").write_text("ID,en\n", encoding="utf-8")

            with self.assertRaises(ReleaseBuildError) as raised:
                validate_items(items)

        message = str(raised.exception)
        self.assertNotIn("Weapons.csv", message)
        self.assertIn("Ammunitions.csv", message)
        self.assertIn("images.zip", message)

    def test_release_environment_uses_ci_value_without_copying_other_secrets(
            self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            (project_root / ".env").write_text(
                "ERSC_RELEASE_API_URL=https://example.invalid/local\n"
                "PRIVATE_TOKEN=do-not-copy\n",
                encoding="utf-8",
            )
            destination = project_root / "release.env"

            write_release_environment(
                destination,
                project_root,
                {
                    "ERSC_RELEASE_API_URL": "https://example.invalid/ci",
                    "PRIVATE_TOKEN": "also-do-not-copy",
                },
            )

            self.assertEqual(
                destination.read_text(encoding="utf-8"),
                "ERSC_RELEASE_API_URL=https://example.invalid/ci\n",
            )

    def test_release_environment_falls_back_to_project_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            (project_root / ".env").write_text(
                "# local release configuration\n"
                "ERSC_RELEASE_API_URL=https://example.invalid/local\n",
                encoding="utf-8",
            )
            destination = project_root / "release.env"

            write_release_environment(destination, project_root, {})

            self.assertEqual(
                destination.read_text(encoding="utf-8"),
                "ERSC_RELEASE_API_URL=https://example.invalid/local\n",
            )

    def test_assemble_release_excludes_readme_and_item_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            layout = ReleaseLayout.from_project(project_root)
            layout.bundle_dir.mkdir(parents=True)
            (layout.bundle_dir / "Seamless Co-op Toolkit.exe").write_bytes(b"exe")
            (layout.bundle_dir / "_internal").mkdir()
            (layout.bundle_dir / "_internal" / "python312.dll").write_bytes(b"dll")
            (project_root / "LICENSE").write_text("MIT\n", encoding="utf-8")
            (project_root / "README.md").write_text("# SCT\n", encoding="utf-8")

            release_dir = assemble_release(
                layout,
                environment={
                    "ERSC_RELEASE_API_URL": "https://example.invalid/releases",
                },
            )

            self.assertEqual(release_dir, layout.release_dir)
            self.assertTrue(
                (release_dir / "Seamless Co-op Toolkit.exe").is_file()
            )
            self.assertTrue((release_dir / "_internal" / "python312.dll").is_file())
            self.assertFalse((release_dir / "items").exists())
            self.assertFalse((release_dir / "README.md").exists())
            self.assertEqual(
                (release_dir / ".env").read_text(encoding="utf-8"),
                "ERSC_RELEASE_API_URL=https://example.invalid/releases\n",
            )
            self.assertEqual(
                (release_dir / "LICENSE").read_text(encoding="utf-8"),
                "MIT\n",
            )

    def test_release_zip_contains_one_versioned_root_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            release_dir = root / "Seamless-Co-op-Toolkit-0.1.0-dev-win64"
            release_dir.mkdir()
            (release_dir / "Seamless Co-op Toolkit.exe").write_bytes(b"exe")
            destination = root / f"{release_dir.name}.zip"

            archive = create_release_zip(release_dir, destination)

            self.assertEqual(archive, destination)
            with zipfile.ZipFile(archive) as release_zip:
                self.assertEqual(
                    release_zip.namelist(),
                    [
                        "Seamless-Co-op-Toolkit-0.1.0-dev-win64/"
                        "Seamless Co-op Toolkit.exe"
                    ],
                )

    def test_items_zip_has_extractable_items_root_and_required_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            source.mkdir()
            for filename in REQUIRED_ITEM_FILES:
                (source / filename).write_bytes(filename.encode())
            (source / ".gitignore").write_text("*\n", encoding="utf-8")
            destination = root / "items.zip"

            archive = create_items_zip(source, destination)

            self.assertEqual(archive, destination)
            with zipfile.ZipFile(archive) as items_zip:
                self.assertEqual(
                    items_zip.namelist(),
                    [f"items/{filename}" for filename in sorted(REQUIRED_ITEM_FILES)],
                )

    def test_third_party_license_bundle_uses_safe_component_directories(
            self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source-license.txt"
            source.write_text("License text\n", encoding="utf-8")
            destination = root / "third-party-licenses"

            written = write_third_party_licenses(
                destination,
                (
                    LicenseComponent(
                        name="Example / Package",
                        version="1.2.3",
                        declared_license="MIT",
                        license_files=(source,),
                    ),
                ),
            )

            copied_license = destination / "Example-Package" / source.name
            self.assertIn(copied_license, written)
            self.assertEqual(
                copied_license.read_text(encoding="utf-8"),
                "License text\n",
            )
            manifest = (destination / "README.txt").read_text(encoding="utf-8")
            self.assertIn("Example / Package 1.2.3", manifest)
            self.assertIn("Declared license: MIT", manifest)
            self.assertIn(
                "License file: Example-Package/source-license.txt",
                manifest,
            )


if __name__ == "__main__":
    unittest.main()
