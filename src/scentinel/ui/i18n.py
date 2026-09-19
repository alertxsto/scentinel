"""Runtime language switching for the Scentinel UI.

Strings live in ``resources/locales/<code>.json`` as a flat ``key -> text`` map.
Missing keys fall back to :data:`DEFAULT_LOCALE`, then to the key itself, so a
gap in a translation never breaks a panel.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QObject, Signal

LOCALES_DIR = Path(__file__).resolve().parent.parent / "resources" / "locales"
DEFAULT_LOCALE = "en"

#: Locale code -> language name shown in the View > Language menu.
LANGUAGES = {"en": "English", "id": "Bahasa Indonesia"}


class Translator(QObject):
    """Holds the active string table and notifies widgets when it changes."""

    changed = Signal()

    def __init__(self, locale: str = DEFAULT_LOCALE, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._locale = locale
        self._fallback = self._load(DEFAULT_LOCALE)
        self._strings = self._load(locale)

    @property
    def locale(self) -> str:
        return self._locale

    def set_locale(self, locale: str) -> None:
        if locale == self._locale:
            return
        self._locale = locale
        self._strings = self._load(locale)
        self.changed.emit()

    def t(self, key: str, **kwargs: object) -> str:
        text = self._strings.get(key) or self._fallback.get(key) or key
        return text.format(**kwargs) if kwargs else text

    @staticmethod
    def _load(locale: str) -> dict[str, str]:
        path = LOCALES_DIR / f"{locale}.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
