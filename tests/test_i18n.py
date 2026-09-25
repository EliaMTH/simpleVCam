import ast
import string
from pathlib import Path

import pytest

from simplevcam import i18n
from simplevcam.i18n import ITALIAN, set_language, tr

SOURCES = Path(__file__).resolve().parents[1] / "simplevcam"


def texts_in_code() -> dict[str, str]:
    """Literal first arguments of every tr(...) call in the app -> where they are."""
    found = {}
    for path in SOURCES.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr":
                first = node.args[0] if node.args else None
                assert isinstance(first, ast.Constant) and isinstance(first.value, str), \
                    f"{path.name}:{node.lineno}: tr() needs a literal string"
                found[first.value] = f"{path.relative_to(SOURCES)}:{node.lineno}"
    return found


def placeholders(text: str) -> set[str]:
    return {field for _, field, _, _ in string.Formatter().parse(text) if field}


@pytest.fixture(autouse=True)
def restore_language():
    yield
    set_language("en")


def test_every_text_has_an_italian_translation():
    missing = {text: where for text, where in texts_in_code().items() if text not in ITALIAN}
    assert not missing, f"missing Italian translations: {missing}"


def test_no_unused_translations():
    unused = set(ITALIAN) - set(texts_in_code())
    assert not unused, f"translations no longer used in the code: {unused}"


def test_placeholders_match():
    wrong = {text: it for text, it in ITALIAN.items() if placeholders(text) != placeholders(it)}
    assert not wrong, f"placeholders differ: {wrong}"


def test_tr_switches_language_and_fills_placeholders():
    assert tr("Preset saved: {path}", path="a.json") == "Preset saved: a.json"
    set_language("it")
    assert i18n.language() == "it"
    assert tr("Preset saved: {path}", path="a.json") == "Preset salvato: a.json"
    assert tr("●  Start camera") == "●  Avvia camera"
    set_language("xx")  # unknown -> English
    assert i18n.language() == "en"
