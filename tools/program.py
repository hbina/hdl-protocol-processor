"""Small typed program and label linker for the pin processor."""

from __future__ import annotations
from collections.abc import Iterable
from dataclasses import dataclass, field
from tools.isa import (
    BASE,
    Instruction,
    IsaConfig,
    IsaError,
    Label,
    Nop,
    cycles,
    decode,
    encode,
    format_instruction,
)


@dataclass(frozen=True)
class Comment:
    text: str


type Item = Instruction | Label | Comment


@dataclass(frozen=True)
class Image:
    words: list[int]
    symbols: dict[str, int]
    config: IsaConfig = BASE

    def disassemble(self) -> str:
        names: dict[int, list[str]] = {}
        for name, address in self.symbols.items():
            names.setdefault(address, []).append(name)
        lines: list[str] = []
        for address, word in enumerate(self.words):
            lines.extend(f"{name}:" for name in names.get(address, []))
            lines.append(
                f"    {format_instruction(decode(word, self.config)):<24} # {address:3d}: {word:04x}"
            )
        lines.extend(f"{name}:" for name in names.get(len(self.words), []))
        return "\n".join(lines) + "\n"


@dataclass
class Program:
    """An explicit list of instructions, comments and labels; no patch pipeline."""

    items: list[Item] = field(default_factory=lambda: [])
    origins: list[str | None] = field(default_factory=lambda: [], repr=False)

    def __post_init__(self) -> None:
        self.items = list(self.items)
        if not self.origins:
            self.origins = [None] * len(self.items)
        if len(self.origins) != len(self.items):
            raise IsaError("origin count must match item count")

    def add(self, item: Item, origin: str | None = None) -> Program:
        self.items.append(item)
        self.origins.append(origin)
        return self

    def extend(self, items: Iterable[Item]) -> Program:
        for item in items:
            self.add(item)
        return self

    def mark(self, label: Label) -> Program:
        return self.add(label)

    def instructions(self) -> list[Instruction]:
        return [item for item in self.items if not isinstance(item, (Label, Comment))]

    @property
    def size(self) -> int:
        return len(self.instructions())

    def cycles(self) -> int:
        """Sum minimum instruction costs, without following control flow."""
        return sum(cycles(insn) for insn in self.instructions())

    def pad_to(self, address: int) -> Program:
        if not self.size <= address <= 256:
            raise IsaError("padding address must be between current size and 256")
        return self.extend([Nop()] * (address - self.size))

    def link(self, cfg: IsaConfig = BASE) -> Image:
        if self.size > 256:
            raise IsaError(f"program contains {self.size} words; maximum is 256")
        addresses: dict[Label, int] = {}
        address = 0
        for item in self.items:
            if isinstance(item, Label):
                if item in addresses:
                    raise IsaError(f"duplicate label {item.name!r}")
                addresses[item] = address
            elif not isinstance(item, Comment):
                address += 1

        def resolve(label: Label) -> int:
            if label not in addresses:
                raise IsaError(f"undefined label {label.name!r}")
            return addresses[label]

        words: list[int] = []
        for item, origin in zip(self.items, self.origins):
            if isinstance(item, (Label, Comment)):
                continue
            try:
                words.append(encode(item, cfg, resolve))
            except IsaError as exc:
                raise IsaError(f"{origin or f'word {len(words)}'}: {exc}") from exc
        return Image(
            words,
            {label.name: addr for label, addr in addresses.items() if label.name},
            cfg,
        )

    def to_asm(self) -> str:
        names: dict[Label, str] = {}
        taken = {
            item.name for item in self.items if isinstance(item, Label) and item.name
        }

        def label_name(label: Label) -> str:
            if label.name is not None:
                return label.name
            if label not in names:
                serial = len(names)
                while f"_L{serial}" in taken:
                    serial += 1
                names[label] = f"_L{serial}"
                taken.add(names[label])
            return names[label]

        lines: list[str] = []
        for item in self.items:
            if isinstance(item, Label):
                lines.append(label_name(item) + ":")
            elif isinstance(item, Comment):
                lines.append("# " + item.text)
            else:
                lines.append(format_instruction(item, label_name))
        return "\n".join(lines) + "\n"
