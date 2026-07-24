from __future__ import annotations

import configparser
import os
import re
import tempfile
from collections import OrderedDict
from pathlib import Path

_SECTION_PATTERN = re.compile(r"^[ \t]*\[([^\]]+)]")
_OPTION_PATTERN = re.compile(
    r"^(?P<indent>[ \t]*)(?P<option>[^#;\s][^=]*?)"
    r"(?P<separator>[ \t]*=[ \t]*)(?P<value>.*?)(?P<ending>\r?\n)?$"
)


def _read_existing_values(
    path: Path | None,
) -> OrderedDict[str, tuple[str, OrderedDict[str, tuple[str, str]]]]:
    values: OrderedDict[str, tuple[str, OrderedDict[str, tuple[str, str]]]] = OrderedDict()
    if path is None or not path.is_file():
        return values
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    parser.read(path, encoding="utf-8-sig")
    for section in parser.sections():
        options: OrderedDict[str, tuple[str, str]] = OrderedDict()
        for option, value in parser.items(section):
            options[option.casefold()] = (option, value)
        values[section.casefold()] = (section, options)
    return values


def merge_ersc_settings(
    template: Path | str,
    existing: Path | str | None,
    destination: Path | str,
    password: str,
) -> None:
    template_path = Path(template)
    existing_path = Path(existing) if existing is not None else None
    destination_path = Path(destination)
    lines = template_path.read_text(encoding="utf-8-sig").splitlines(keepends=True)
    newline = "\r\n" if any(line.endswith("\r\n") for line in lines) else "\n"
    overlay = _read_existing_values(existing_path)
    password_section, password_options = overlay.setdefault(
        "password",
        ("PASSWORD", OrderedDict()),
    )
    password_options["cooppassword"] = ("cooppassword", password)
    overlay["password"] = (password_section, password_options)

    output: list[str] = []
    current_section: str | None = None
    seen_sections: set[str] = set()
    found_options: set[tuple[str, str]] = set()

    def append_missing(section_key: str | None) -> None:
        if section_key is None or section_key not in overlay:
            return
        _section_name, options = overlay[section_key]
        for option_key, (option_name, value) in options.items():
            if (section_key, option_key) not in found_options:
                output.append(f"{option_name} = {value}{newline}")
                found_options.add((section_key, option_key))

    for line in lines:
        section_match = _SECTION_PATTERN.match(line)
        if section_match:
            append_missing(current_section)
            current_section = section_match.group(1).strip().casefold()
            seen_sections.add(current_section)
            output.append(line)
            continue
        option_match = _OPTION_PATTERN.match(line)
        if option_match and current_section in overlay:
            option_key = option_match.group("option").strip().casefold()
            options = overlay[current_section][1]
            if option_key in options:
                value = options[option_key][1]
                line = (
                    f"{option_match.group('indent')}{option_match.group('option')}"
                    f"{option_match.group('separator')}{value}"
                    f"{option_match.group('ending') or ''}"
                )
                found_options.add((current_section, option_key))
        output.append(line)
    append_missing(current_section)

    for section_key, (section_name, options) in overlay.items():
        if section_key in seen_sections:
            continue
        if output and output[-1].strip():
            output.append(newline)
        output.append(f"[{section_name}]{newline}")
        for option_key, (option_name, value) in options.items():
            output.append(f"{option_name} = {value}{newline}")
            found_options.add((section_key, option_key))

    _atomic_write(destination_path, "".join(output))


def _atomic_write(path: Path, document: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as temporary:
            temporary.write(document)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
