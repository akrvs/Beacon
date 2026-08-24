"""External checks plug in through the beacon.checks entry-point group."""

from importlib.metadata import EntryPoint

import beacon.checks as checks_mod
from beacon.checks import ALL_CHECKS, BUILTIN_CHECKS
from beacon.checks.base import Layer


class ExtraCheck:
    id = "extra"
    layer = Layer.CONTENT

    async def run(self, site):
        return []


class NoLayerCheck:
    id = "nolayer"


def _ep(obj, name):
    return EntryPoint(
        name=name,
        value=f"tests.test_plugin_checks:{obj.__name__}",
        group=checks_mod.ENTRY_POINT_GROUP,
    )


def _patch(monkeypatch, entries):
    monkeypatch.setattr(checks_mod, "entry_points", lambda group: entries)


def test_builtins_load_without_plugins(monkeypatch):
    _patch(monkeypatch, [])
    assert ALL_CHECKS == BUILTIN_CHECKS


def test_plugin_check_is_appended(monkeypatch):
    _patch(monkeypatch, [_ep(ExtraCheck, "extra")])
    plugins = checks_mod._plugin_checks()
    assert [type(c).__name__ for c in plugins] == ["ExtraCheck"]


def test_duplicate_id_is_not_appended_twice(monkeypatch):
    _patch(monkeypatch, [_ep(ExtraCheck, "extra"), _ep(ExtraCheck, "extra2")])
    assert len(checks_mod._plugin_checks()) == 1


def test_malformed_plugin_is_skipped(monkeypatch):
    class Broken:
        pass

    class Boom:
        def __init__(self):
            raise RuntimeError("no")

    _patch(
        monkeypatch,
        [_ep(Broken, "broken"), _ep(Boom, "boom"), _ep(ExtraCheck, "extra")],
    )
    plugins = checks_mod._plugin_checks()
    assert [type(c).__name__ for c in plugins] == ["ExtraCheck"]
