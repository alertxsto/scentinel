"""Shared pytest fixtures: a Qt application and an offscreen-safe main window."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def translator():
    from scentinel.ui.i18n import Translator

    return Translator("en")
