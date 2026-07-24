from __future__ import annotations

import hashlib
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

from sct.downloads import DownloadError, UnsafeArchiveError, download_file, safe_extract_zip


class DownloadTests(unittest.TestCase):
    def test_download_streams_file_and_verifies_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.zip"
            source.write_bytes(b"archive payload")
            destination = root / "downloaded.zip"
            progress: list[tuple[int, int | None]] = []

            result = download_file(
                source.as_uri(),
                destination,
                expected_digest=hashlib.sha256(source.read_bytes()).hexdigest(),
                progress=lambda received, total: progress.append((received, total)),
            )

            self.assertEqual(result, destination)
            self.assertEqual(destination.read_bytes(), b"archive payload")
            self.assertEqual(progress[-1][0], len(b"archive payload"))

    def test_digest_mismatch_removes_download(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.zip"
            source.write_bytes(b"bad payload")
            destination = root / "downloaded.zip"

            with self.assertRaisesRegex(DownloadError, "SHA-256"):
                download_file(
                    source.as_uri(),
                    destination,
                    expected_digest="0" * 64,
                )

            self.assertFalse(destination.exists())


class SafeZipTests(unittest.TestCase):
    def test_extracts_regular_archive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "safe.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("folder/file.txt", "ok")

            destination = root / "extract"
            safe_extract_zip(archive, destination)

            self.assertEqual((destination / "folder" / "file.txt").read_text(), "ok")

    def test_rejects_path_traversal_and_absolute_entries(self) -> None:
        malicious_names = ("../outside.txt", r"..\outside.txt", "/absolute.txt", r"C:\drive.txt")
        for name in malicious_names:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                archive = root / "unsafe.zip"
                with zipfile.ZipFile(archive, "w") as bundle:
                    bundle.writestr(name, "bad")

                with self.assertRaises(UnsafeArchiveError):
                    safe_extract_zip(archive, root / "extract")

    def test_rejects_symbolic_link_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "link.zip"
            link = zipfile.ZipInfo("link")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr(link, "target")

            with self.assertRaisesRegex(UnsafeArchiveError, "символическую ссылку"):
                safe_extract_zip(archive, root / "extract")


if __name__ == "__main__":
    unittest.main()
