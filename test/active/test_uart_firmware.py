"""UART generation limits, independent construction, and default listings."""

from pathlib import Path
import subprocess
import sys
import pytest
from firmware.uart import transmit, receive, echo
from tools.assembler import assemble_image
from tools.isa import IsaError

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("module", [transmit, receive, echo])
@pytest.mark.parametrize(
    "clock,baud",
    [
        (50_000_000, 1_000_000),
        (50_000_000, 250_000),
        (50_000_000, 115_200),
        (50_000_000, 9_600),
        (25_000_000, 500_000),
    ],
)
def test_supported_timing(module, clock, baud):
    image = module.generate(clock_hz=clock, baud=baud)
    assert len(image.words) <= 256
    assert assemble_image(image.disassemble()).words == image.words


@pytest.mark.parametrize("module", [transmit, receive, echo])
@pytest.mark.parametrize(
    "clock,baud",
    [(0, 1), (-1, 1), (50_000_000, 0), (50_000_000, -1), (50_000_000, 2_000_000)],
)
def test_bad_timing(module, clock, baud):
    with pytest.raises(ValueError):
        module.generate(clock_hz=clock, baud=baud)


@pytest.mark.parametrize("payload", [b"", bytes(65)])
def test_tx_payload_bounds(payload):
    with pytest.raises(ValueError):
        transmit.generate(payload=payload)


@pytest.mark.parametrize(
    "payload", [b"\x00", b"\xff", bytes(range(64)), bytes([255]) * 64]
)
def test_arbitrary_ram_payload(payload):
    assert len(transmit.generate(payload=payload).words) <= 256


@pytest.mark.parametrize("pin", [-1, 8])
def test_bad_tx_pin(pin):
    with pytest.raises(ValueError):
        transmit.generate(tx_pin=pin)


@pytest.mark.parametrize("capacity", [0, -1, 241])
def test_bad_capacity(capacity):
    with pytest.raises(ValueError):
        receive.generate(capacity=capacity)


@pytest.mark.parametrize("capacity", [1, 128, 240])
def test_valid_capacity(capacity):
    assert len(receive.generate(capacity=capacity).words) <= 256


@pytest.mark.parametrize("module", [transmit, receive, echo])
def test_default_listing(module):
    source = ROOT / "firmware/uart" / f"{module.__name__.split('.')[-1]}.asm"
    image = module.generate()
    checked = assemble_image(source.read_text())
    assert checked.words == image.words and checked.symbols == image.symbols


@pytest.mark.parametrize("module", [transmit, receive, echo])
def test_no_artifact_or_predecessor_reads(module, monkeypatch):
    expected = module.generate().words

    def forbid(*args, **kwargs):
        raise AssertionError("firmware generation must not read prior source/artifacts")

    monkeypatch.setattr(Path, "read_text", forbid)
    assert module.generate().words == expected


@pytest.mark.parametrize("name", ["transmit", "receive", "echo"])
@pytest.mark.parametrize("style", ["file", "module"])
def test_cli(name, style, tmp_path):
    target = tmp_path / f"{name}.asm"
    args = (
        [sys.executable, "-m", f"firmware.uart.{name}"]
        if style == "module"
        else [sys.executable, str(ROOT / f"firmware/uart/{name}.py")]
    )
    result = subprocess.run(
        [*args, "--baud", "115200", "-o", str(target)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert len(assemble_image(target.read_text()).words) <= 256


@pytest.mark.parametrize("module", [transmit, receive, echo])
def test_program_capacity_is_enforced(module):
    # Very slow rates would need more timing/qualification instructions than RAM.
    with pytest.raises(IsaError):
        module.generate(baud=1000)


def test_slow_baud_payload_capacity():
    assert len(transmit.generate(baud=9_600, payload=bytes(50)).words) == 256
    with pytest.raises(IsaError):
        transmit.generate(baud=9_600, payload=bytes(51))
