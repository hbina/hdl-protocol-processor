"""Cycle-counted typed fragments for the generated study firmware.

A ``Fragment`` is a typed program piece plus the clocks it takes on its normal
path. ``choose`` balances both arms of a conditional branch so that either arm
takes the same time, which is how the generated protocol loops keep fixed bit
periods without protocol-specific hardware.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import ClassVar

import isa_variants  # noqa: F401  # pyright: ignore[reportUnusedImport]  (sets sys.path)

from tools.isa import (
    JMP,
    LDI,
    LOAD,
    NOP,
    STORE,
    WAIT,
    Instruction,
    Label,
    Reg,
    r0,
    r1,
)
from tools.program import Item, Program

type Piece = Fragment | Program | Item | Iterable[Item]


class Fragment:
    """Typed replacement for the former text ``Block`` builder."""

    serial: ClassVar[int] = 0
    program: Program
    cycles: int

    def __init__(self, items: Piece = (), cycles: int | None = None) -> None:
        measured: int
        if isinstance(items, Fragment):
            self.program = items.program.copy()
            measured = items.cycles
        else:
            self.program = Program() + items
            measured = self.program.cycles()
        self.cycles = measured if cycles is None else cycles

    def add(self, other: Piece) -> Fragment:
        piece = other if isinstance(other, Fragment) else Fragment(other)
        self.program += piece.program
        self.cycles += piece.cycles
        return self

    @classmethod
    def delay(cls, cycles: int) -> Fragment:
        assert cycles >= 0, cycles
        block = cls()
        while cycles:
            step = min(256, cycles)
            block.add(NOP() if step == 1 else WAIT(step - 1))
            cycles -= step
        return block

    @classmethod
    def choose(
        cls,
        branch: Callable[[Label], Instruction],
        yes: Piece,
        no: Piece = (),
    ) -> Fragment:
        """Run ``yes`` when ``branch`` is taken, else ``no``; both take equal time."""

        yes = yes if isinstance(yes, cls) else cls(yes)
        no = no if isinstance(no, cls) else cls(no)
        cls.serial += 1
        label = f"balance_{cls.serial}"
        taken, end = Label(f"{label}_yes"), Label(f"{label}_end")
        longest = max(yes.cycles, no.cycles + 1)
        result = cls(branch(taken))
        result.add(no).add(cls.delay(longest - no.cycles - 1)).add(JMP(end))
        result.add(taken).add(yes).add(cls.delay(longest - yes.cycles))
        result.add(end)
        # The linear listing contains both arms; only one executes at runtime.
        result.cycles = longest + 1
        return result


def put(address: int, value: int) -> Fragment:
    return Fragment([LDI(r1, address), LDI(r0, value), STORE(r0, r1)])


def load(address: int, reg: Reg = r0) -> Fragment:
    return Fragment([LDI(r1, address), LOAD(reg, r1)])
