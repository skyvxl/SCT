from __future__ import annotations

import unittest

from sct.releases import (
    ReleaseError,
    parse_release_info,
    select_named_release_asset,
    select_release_asset,
)


class ReleaseSelectionTests(unittest.TestCase):
    def test_parses_release_metadata_without_download_assets(self) -> None:
        release = parse_release_info(
            {
                "tag_name": "v0.2.0",
                "html_url": "https://github.com/skyvxl/SCT/releases/tag/v0.2.0",
                "assets": [],
            }
        )

        self.assertEqual(release.tag_name, "v0.2.0")
        self.assertEqual(
            release.html_url,
            "https://github.com/skyvxl/SCT/releases/tag/v0.2.0",
        )

    def test_rejects_release_metadata_without_web_url(self) -> None:
        with self.assertRaises(ReleaseError) as caught:
            parse_release_info({"tag_name": "v0.2.0"})

        self.assertEqual(caught.exception.code, "release_response_invalid")

    def test_selects_zip_and_reads_github_digest(self) -> None:
        asset = select_release_asset(
            {
                "tag_name": "v1.9.8",
                "assets": [
                    {
                        "name": "Seamless.Co-op.v1.9.8.zip",
                        "browser_download_url": "https://example.invalid/ersc.zip",
                        "content_type": "application/x-zip-compressed",
                        "size": 1234,
                        "digest": "sha256:ABCDEF",
                    }
                ],
            }
        )

        self.assertEqual(asset.tag_name, "v1.9.8")
        self.assertEqual(asset.name, "Seamless.Co-op.v1.9.8.zip")
        self.assertEqual(asset.download_url, "https://example.invalid/ersc.zip")
        self.assertEqual(asset.size, 1234)
        self.assertEqual(asset.sha256, "abcdef")

    def test_prefers_seamless_named_zip_when_release_has_other_archives(self) -> None:
        asset = select_release_asset(
            {
                "tag_name": "v2",
                "assets": [
                    {
                        "name": "symbols.zip",
                        "browser_download_url": "https://example.invalid/symbols.zip",
                    },
                    {
                        "name": "ERSc-release.zip",
                        "browser_download_url": "https://example.invalid/ersc.zip",
                    },
                ],
            }
        )

        self.assertEqual(asset.name, "ERSc-release.zip")

    def test_rejects_ambiguous_zip_assets(self) -> None:
        with self.assertRaises(ReleaseError) as caught:
            select_release_asset(
                {
                    "tag_name": "v2",
                    "assets": [
                        {
                            "name": "one.zip",
                            "browser_download_url": "https://example.invalid/one.zip",
                        },
                        {
                            "name": "two.zip",
                            "browser_download_url": "https://example.invalid/two.zip",
                        },
                    ],
                }
            )
        self.assertEqual(caught.exception.code, "release_zip_ambiguous")

    def test_rejects_release_without_zip_asset(self) -> None:
        with self.assertRaises(ReleaseError) as caught:
            select_release_asset({"tag_name": "v2", "assets": []})
        self.assertEqual(caught.exception.code, "release_zip_missing")

    def test_rejects_asset_name_that_can_escape_download_directory(self) -> None:
        with self.assertRaises(ReleaseError) as caught:
            select_release_asset(
                {
                    "tag_name": "v2",
                    "assets": [
                        {
                            "name": "../Seamless.zip",
                            "browser_download_url": "https://example.invalid/ersc.zip",
                        }
                    ],
                }
            )
        self.assertEqual(caught.exception.code, "release_asset_name_unsafe")

    def test_selects_exact_named_asset_for_modengine3(self) -> None:
        asset = select_named_release_asset(
            {
                "tag_name": "v0.12.1",
                "assets": [
                    {
                        "name": "me3-linux-amd64.tar.xz",
                        "browser_download_url": "https://example.invalid/linux.tar.xz",
                    },
                    {
                        "name": "me3-windows-amd64.zip",
                        "browser_download_url": "https://example.invalid/me3.zip",
                        "size": 321,
                    },
                ],
            },
            "me3-windows-amd64.zip",
        )

        self.assertEqual(asset.tag_name, "v0.12.1")
        self.assertEqual(asset.download_url, "https://example.invalid/me3.zip")
        self.assertEqual(asset.size, 321)

    def test_missing_exact_named_asset_is_reported(self) -> None:
        with self.assertRaises(ReleaseError) as caught:
            select_named_release_asset(
                {"tag_name": "v0.12.1", "assets": []},
                "me3-windows-amd64.zip",
            )

        self.assertEqual(caught.exception.code, "release_named_asset_missing")


if __name__ == "__main__":
    unittest.main()
