from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from sct.errors import LocalizedError


class ReleaseError(LocalizedError):
    pass


@dataclass(frozen=True, slots=True)
class ReleaseAsset:
    tag_name: str
    name: str
    download_url: str
    size: int | None = None
    sha256: str | None = None


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    tag_name: str
    html_url: str


def parse_release_info(payload: Mapping[str, Any]) -> ReleaseInfo:
    tag_name = payload.get("tag_name")
    html_url = payload.get("html_url")
    parsed_url = urlparse(str(html_url or ""))
    if (
            not isinstance(tag_name, str)
            or not tag_name.strip()
            or not isinstance(html_url, str)
            or parsed_url.scheme not in {"http", "https"}
            or not parsed_url.netloc
    ):
        raise ReleaseError(
            "release_response_invalid",
            "GitHub Releases API returned invalid release metadata",
        )
    return ReleaseInfo(tag_name=tag_name.strip(), html_url=html_url)


def select_release_asset(payload: Mapping[str, Any]) -> ReleaseAsset:
    raw_assets = payload.get("assets")
    assets = raw_assets if isinstance(raw_assets, list) else []
    zip_assets = [
        asset
        for asset in assets
        if isinstance(asset, Mapping)
           and isinstance(asset.get("name"), str)
           and str(asset["name"]).casefold().endswith(".zip")
           and isinstance(asset.get("browser_download_url"), str)
    ]
    if not zip_assets:
        raise ReleaseError(
            "release_zip_missing",
            "The latest Seamless Co-op release does not contain a ZIP asset",
        )
    preferred = [
        asset
        for asset in zip_assets
        if any(word in str(asset["name"]).casefold() for word in ("seamless", "ersc"))
    ]
    candidates = preferred or zip_assets
    if len(candidates) != 1:
        raise ReleaseError(
            "release_zip_ambiguous",
            "Unable to select one Seamless Co-op ZIP asset",
        )

    return _build_release_asset(payload, candidates[0])


def select_named_release_asset(
        payload: Mapping[str, Any],
        asset_name: str,
) -> ReleaseAsset:
    raw_assets = payload.get("assets")
    assets = raw_assets if isinstance(raw_assets, list) else []
    candidates = [
        asset
        for asset in assets
        if isinstance(asset, Mapping)
           and asset.get("name") == asset_name
           and isinstance(asset.get("browser_download_url"), str)
    ]
    if len(candidates) != 1:
        raise ReleaseError(
            "release_named_asset_missing",
            f"The latest release does not contain {asset_name}",
            params={"asset": asset_name},
        )
    return _build_release_asset(payload, candidates[0])


def _build_release_asset(
        payload: Mapping[str, Any],
        selected: Mapping[str, Any],
) -> ReleaseAsset:
    selected_name = str(selected["name"])
    if (
            PurePosixPath(selected_name).name != selected_name
            or PureWindowsPath(selected_name).name != selected_name
            or PureWindowsPath(selected_name).drive
    ):
        raise ReleaseError(
            "release_asset_name_unsafe",
            f"Release asset has an unsafe file name: {selected_name}",
        )
    raw_digest = selected.get("digest")
    sha256 = None
    if isinstance(raw_digest, str) and raw_digest.casefold().startswith("sha256:"):
        sha256 = raw_digest.partition(":")[2].strip().casefold() or None
    raw_size = selected.get("size")
    size = raw_size if isinstance(raw_size, int) and raw_size >= 0 else None
    return ReleaseAsset(
        tag_name=str(payload.get("tag_name") or payload.get("name") or "unknown"),
        name=selected_name,
        download_url=str(selected["browser_download_url"]),
        size=size,
        sha256=sha256,
    )


class GitHubReleaseClient:
    def __init__(self, *, timeout: float = 30.0) -> None:
        self.timeout = timeout

    def latest_release(self, api_url: str) -> ReleaseInfo:
        return parse_release_info(self._request_payload(api_url))

    def latest_asset(self, api_url: str) -> ReleaseAsset:
        return select_release_asset(self._request_payload(api_url))

    def latest_named_asset(self, api_url: str, asset_name: str) -> ReleaseAsset:
        return select_named_release_asset(self._request_payload(api_url), asset_name)

    def _request_payload(self, api_url: str) -> Mapping[str, Any]:
        request = Request(
            api_url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "Seamless-Co-op-Toolkit",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except (HTTPError, URLError, OSError, json.JSONDecodeError) as error:
            raise ReleaseError(
                "release_request_failed",
                f"Unable to fetch the latest release: {error}",
            ) from error
        if not isinstance(payload, Mapping):
            raise ReleaseError(
                "release_response_invalid",
                "GitHub Releases API returned an invalid response",
            )
        return payload
