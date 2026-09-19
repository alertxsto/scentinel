from __future__ import annotations

import pytest

from scentinel.ui.i18n import Translator


def test_missing_key_falls_back_to_the_key(qapp):
    translator = Translator("en")
    assert translator.t("no.such.key") == "no.such.key"


def test_unknown_locale_falls_back_to_english(qapp):
    translator = Translator("xx")
    assert translator.t("action.run") == "Run Simulation"


def test_switching_locale_translates_and_notifies(qapp):
    translator = Translator("en")
    seen = []
    translator.changed.connect(lambda: seen.append(translator.locale))

    translator.set_locale("id")

    assert seen == ["id"]
    assert translator.t("action.run") == "Jalankan Simulasi"


def test_setting_the_same_locale_is_a_no_op(qapp):
    translator = Translator("en")
    seen = []
    translator.changed.connect(lambda: seen.append(translator.locale))
    translator.set_locale("en")
    assert seen == []


def test_keyword_formatting(qapp):
    translator = Translator("en")
    assert translator.t("status.sensors", count=3) == "3 sensor(s)"
