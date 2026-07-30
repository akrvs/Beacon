from __future__ import annotations

import os
import tomllib
from pathlib import Path


def beacon_home() -> Path:
    root = os.environ.get("BEACON_HOME")
    if root is None:
        data_home = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
        root = str(Path(data_home) / "beacon")
    return Path(root)


def load_config() -> dict:
    for path in (Path("beacon.toml"), beacon_home() / "beacon.toml"):
        if path.is_file():
            try:
                return tomllib.loads(path.read_text(encoding="utf-8"))
            except tomllib.TOMLDecodeError as error:
                raise ValueError(f"{path} is not valid TOML: {error}") from error
    return {}
