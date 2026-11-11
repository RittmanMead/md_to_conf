"""Tests for the md2conf command line tool (offline, no Confluence needed)."""

import importlib
import sys

import pytest


def _load_md2conf(tmp_path, monkeypatch, argv_extra=()):
    md_file = tmp_path / "page.md"
    md_file.write_text("# Title\n\nBody\n", encoding="utf-8")
    monkeypatch.setenv("CONFLUENCE_USERNAME", "user@example.com")
    monkeypatch.setenv("CONFLUENCE_API_KEY", "dummy")
    monkeypatch.setenv("CONFLUENCE_ORGNAME", "example")
    monkeypatch.setattr(
        sys, "argv",
        ["md2conf.py", str(md_file), "SPACE", *argv_extra],
    )
    sys.modules.pop("md2conf", None)
    return importlib.import_module("md2conf")


class FakePage:
    id = "123"
    version = 1
    properties = {}


def test_delete_exits_zero(tmp_path, monkeypatch):
    """A successful --delete must exit 0, not 1."""
    md2conf = _load_md2conf(tmp_path, monkeypatch, ("--delete",))
    monkeypatch.setattr(md2conf, "get_page", lambda title: FakePage())
    deleted = {}
    monkeypatch.setattr(
        md2conf, "delete_page", lambda page_id: deleted.setdefault("id", page_id)
    )
    with pytest.raises(SystemExit) as excinfo:
        md2conf.main()
    assert excinfo.value.code == 0
    assert deleted == {"id": "123"}
