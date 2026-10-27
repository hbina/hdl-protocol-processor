"""Python generators link typed values; pre-conversion images remain identical."""

import ast
import hashlib
import json
from pathlib import Path
import pytest
from firmware.uart import transmit, receive, echo
from tools import assembler

ROOT = Path(__file__).resolve().parents[2]
BASELINE = json.loads((ROOT / "test/golden/uart_profiles.json").read_text())
MODULES = {"transmit": transmit, "receive": receive, "echo": echo}


@pytest.mark.parametrize(
    "profile",
    BASELINE["profiles"],
    ids=lambda p: p["generator"] + "-" + str(p["arguments"]),
)
def test_pre_conversion_profile(profile):
    kwargs = dict(profile["arguments"])
    if "payload_hex" in kwargs:
        kwargs["payload"] = bytes.fromhex(kwargs.pop("payload_hex"))
    expected = profile["expected"]
    if "error" in expected:
        with pytest.raises(ValueError) as caught:
            MODULES[profile["generator"]].generate(**kwargs)
        assert type(caught.value).__name__ == expected["error_type"]
        assert str(caught.value) == expected["error"]
    else:
        image = MODULES[profile["generator"]].generate(**kwargs)
        encoded = b"".join(word.to_bytes(2, "little") for word in image.words)
        assert len(image.words) == expected["words"]
        assert hashlib.sha256(encoded).hexdigest() == expected["words_sha256"]
        assert image.symbols == expected["symbols"]


@pytest.mark.parametrize("module", MODULES.values())
def test_generator_does_not_call_text_parser(module, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Python firmware construction must use typed instructions")

    for name in ["parse", "assemble", "assemble_image"]:
        monkeypatch.setattr(assembler, name, forbidden)
    assert module.generate().words


def test_construction_modules_do_not_import_text_assembler():
    paths = [*ROOT.glob("firmware/**/*.py"), ROOT / "test/pin_core_checks.py"]
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert node.module != "tools.assembler", path
            elif isinstance(node, ast.Import):
                assert all(alias.name != "tools.assembler" for alias in node.names), (
                    path
                )
