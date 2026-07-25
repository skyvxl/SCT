# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


project_root = Path(SPECPATH).parent
source_root = project_root / "src"
package_root = source_root / "sct"

datas = [
    (str(package_root / "resources"), "sct/resources"),
    (
        str(package_root / "game" / "elden_ring" / "offsets.toml"),
        "sct/game/elden_ring",
    ),
    (
        str(package_root / "game" / "elden_ring" / "signatures.toml"),
        "sct/game/elden_ring",
    ),
]

analysis = Analysis(
    [str(package_root / "__main__.py")],
    pathex=[str(source_root)],
    binaries=[],
    datas=datas,
    hiddenimports=collect_submodules("pymem"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)

python_archive = PYZ(analysis.pure)

executable = EXE(
    python_archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Seamless Co-op Toolkit",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(package_root / "resources" / "icons" / "icon.ico"),
    version=str(project_root / "packaging" / "windows_version_info.txt"),
    contents_directory="_internal",
)

bundle = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Seamless Co-op Toolkit",
)
