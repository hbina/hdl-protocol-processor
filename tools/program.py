"""Build programs from typed instructions and link them into machine words.

A ``Program`` is a sequence of instructions, labels and comments. Labels are
objects, so fragments can create private labels without name mangling, and a
reference to a label that is never placed is a link error rather than a typo
discovered in generated text.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import overload

from tools.isa import (
    BASE,
    Call,
    CondJump,
    Halt,
    Imm,
    Instruction,
    IsaConfig,
    IsaError,
    Jump,
    Label,
    Nop,
    RegImm,
    RegPin,
    RegReg,
    Ret,
    Target,
    Unary,
    WaitPin,
    cycles,
    decode,
    encode,
    format_instruction,
)

INSTRUCTION_TYPES = (
    Nop,
    Halt,
    RegImm,
    RegReg,
    Unary,
    Imm,
    Jump,
    CondJump,
    RegPin,
    WaitPin,
    Call,
    Ret,
)


@dataclass(frozen=True)
class Comment:
    """A listing-only line; it occupies no program word."""

    text: str


type Item = Instruction | Label | Comment


def is_instruction(item: Item) -> bool:
    return isinstance(item, INSTRUCTION_TYPES)


@dataclass(frozen=True)
class Image:
    """Linked machine words plus the address of every named label."""

    words: list[int]
    symbols: dict[str, int]
    config: IsaConfig = BASE

    def disassemble(self) -> str:
        names: dict[int, list[str]] = {}
        for name, address in self.symbols.items():
            names.setdefault(address, []).append(name)
        digits = (self.config.word_bits + 3) // 4
        lines: list[str] = []
        for address, word in enumerate(self.words):
            lines += [f"{name}:" for name in names.get(address, [])]
            text = format_instruction(decode(word, self.config))
            lines.append(f"    {text:<24} # {address:4d}: {word:0{digits}x}")
        lines += [f"{name}:" for name in names.get(len(self.words), [])]
        return "\n".join(lines) + "\n"


type Items = Item | Iterable[Item] | Program


def _items(value: Items) -> list[Item]:
    if isinstance(value, str):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError(f"assembly text is not a program item: {value!r}")
    if isinstance(value, Program):
        return list(value.items)
    if isinstance(value, (Label, Comment, *INSTRUCTION_TYPES)):
        return [value]  # pyright: ignore[reportReturnType]
    return list(value)  # pyright: ignore[reportArgumentType]


def place(
    instructions: Mapping[int, Instruction],
    size: int,
    filler: Instruction | None = None,
) -> Program:
    """A ``size``-word image with each instruction at its address, ``filler`` elsewhere."""

    for address in instructions:
        if not 0 <= address < size:
            raise IsaError(f"address {address} is outside a {size}-word image")
    fill = filler if filler is not None else Halt()
    return Program([instructions.get(address, fill) for address in range(size)])


def concat(parts: Iterable[Items]) -> Program:
    """Join program pieces in order, like ``"".join`` for assembly text."""

    result = Program()
    for part in parts:
        result.extend(part)
    return result


@dataclass
class Program:
    """An editable item sequence.

    ``add``/``extend``/``+=``/``mark``/``pad_to`` build a program in place.
    The sequence operations (``+``, slicing, ``find``, ``index``, ``count``,
    ``replace``, ``split``) mirror ``str`` but act on whole items, and return
    new programs, so firmware derived from an earlier generation can be
    expressed as typed edits of that generation.
    """

    items: list[Item] = field(default_factory=lambda: [])
    origins: list[str | None] = field(
        default_factory=lambda: [], compare=False, repr=False
    )

    def __post_init__(self) -> None:
        self.items = list(self.items)
        if len(self.origins) != len(self.items):
            self.origins = [None] * len(self.items)
        else:
            self.origins = list(self.origins)

    def add(self, item: Item, origin: str | None = None) -> Program:
        self.items.append(item)
        self.origins.append(origin)
        return self

    def extend(self, items: Items) -> Program:
        if isinstance(items, Program):
            self.items += items.items
            self.origins += items.origins
        else:
            for item in _items(items):
                self.add(item)
        return self

    def __iadd__(self, other: Items) -> Program:
        return self.extend(other)

    # --- str-like sequence operations ---------------------------------------

    def copy(self) -> Program:
        return Program(self.items, self.origins)

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self) -> Iterator[Item]:
        return iter(self.items)

    @overload
    def __getitem__(self, index: int) -> Item: ...
    @overload
    def __getitem__(self, index: slice) -> Program: ...
    def __getitem__(self, index: int | slice) -> Item | Program:
        if isinstance(index, slice):
            return Program(self.items[index], self.origins[index])
        return self.items[index]

    def __add__(self, other: Items) -> Program:
        return self.copy().extend(other)

    def __radd__(self, other: Iterable[Item]) -> Program:
        return Program(_items(other)).extend(self)

    def __mul__(self, count: int) -> Program:
        return Program(self.items * count, self.origins * count)

    def find(self, sub: Items, start: int = 0, end: int | None = None) -> int:
        needle = _items(sub)
        stop = len(self.items) if end is None else end
        for position in range(start, stop - len(needle) + 1):
            if self.items[position : position + len(needle)] == needle:
                return position
        return -1

    def index(self, sub: Items, start: int = 0, end: int | None = None) -> int:
        position = self.find(sub, start, end)
        if position < 0:
            raise ValueError(
                f"subsequence not found: {Program(_items(sub)).to_asm()!r}"
            )
        return position

    def rfind(self, sub: Items) -> int:
        needle = _items(sub)
        for position in range(len(self.items) - len(needle), -1, -1):
            if self.items[position : position + len(needle)] == needle:
                return position
        return -1

    def __contains__(self, sub: object) -> bool:
        return self.find(sub) >= 0  # pyright: ignore[reportArgumentType]

    def count(self, sub: Items) -> int:
        needle = _items(sub)
        if not needle:
            raise ValueError("empty subsequence")
        total, position = 0, self.find(needle)
        while position >= 0:
            total += 1
            position = self.find(needle, position + len(needle))
        return total

    def replace(self, old: Items, new: Items, count: int = -1) -> Program:
        needle, replacement = _items(old), _items(new)
        if not needle:
            raise ValueError("empty subsequence")
        result = Program()
        position = 0
        while count != 0:
            found = self.find(needle, position)
            if found < 0:
                break
            result.extend(self[position:found]).extend(replacement)
            position = found + len(needle)
            count -= 1
        return result.extend(self[position:])

    def split(self, sep: Items, maxsplit: int = -1) -> list[Program]:
        needle = _items(sep)
        parts: list[Program] = []
        position = 0
        while maxsplit != 0:
            found = self.find(needle, position)
            if found < 0:
                break
            parts.append(self[position:found])
            position = found + len(needle)
            maxsplit -= 1
        parts.append(self[position:])
        return parts

    def removeprefix(self, prefix: Items) -> Program:
        return self[len(_items(prefix)) :] if self.startswith(prefix) else self.copy()

    def removesuffix(self, suffix: Items) -> Program:
        needle = _items(suffix)
        if needle and self.endswith(needle):
            return self[: -len(needle)]
        return self.copy()

    def startswith(self, prefix: Items) -> bool:
        needle = _items(prefix)
        return self.items[: len(needle)] == needle

    def endswith(self, suffix: Items) -> bool:
        needle = _items(suffix)
        return not needle or self.items[-len(needle) :] == needle

    def map_labels(self, rename: Callable[[Label], Label]) -> Program:
        """Return a copy with every label definition and reference renamed."""

        def target(value: Target) -> Target:
            return rename(value) if isinstance(value, Label) else value

        items: list[Item] = []
        for item in self.items:
            match item:
                case Label():
                    items.append(rename(item))
                case Jump() | CondJump() | Call():
                    items.append(dataclasses.replace(item, target=target(item.target)))
                case _:
                    items.append(item)
        return Program(items, self.origins)

    def comment_index(self, prefix: str, start: int = 0) -> int:
        """Position of the first comment at or after ``start`` that begins with ``prefix``."""

        for position in range(start, len(self.items)):
            item = self.items[position]
            if isinstance(item, Comment) and item.text.startswith(prefix):
                return position
        raise ValueError(f"no comment starts with {prefix!r}")

    def replace_comment_text(self, old: str, new: str) -> Program:
        """Return a copy with ``old`` replaced by ``new`` inside every comment."""

        items = [
            Comment(item.text.replace(old, new)) if isinstance(item, Comment) else item
            for item in self.items
        ]
        return Program(items, self.origins)

    def labels(self) -> list[Label]:
        return [item for item in self.items if isinstance(item, Label)]

    def without_comments(self) -> Program:
        keep = [i for i, item in enumerate(self.items) if not isinstance(item, Comment)]
        return Program([self.items[i] for i in keep], [self.origins[i] for i in keep])

    def mark(self, label: Label) -> Program:
        return self.add(label)

    def instructions(self) -> list[Instruction]:
        return [item for item in self.items if isinstance(item, INSTRUCTION_TYPES)]

    @property
    def size(self) -> int:
        return len(self.instructions())

    def cycles(self) -> int:
        return sum(cycles(insn) for insn in self.instructions())

    def pad_to(self, address: int, filler: Instruction | None = None) -> Program:
        """Append filler instructions until the next instruction is at ``address``."""

        if address < self.size:
            raise IsaError(
                f"cannot pad to {address}: program already has {self.size} words"
            )
        for _ in range(address - self.size):
            self.add(filler if filler is not None else Nop())
        return self

    def _addresses(self) -> dict[Label, int]:
        addresses: dict[Label, int] = {}
        names: set[str] = set()
        address = 0
        for item, origin in zip(self.items, self.origins):
            if isinstance(item, Label):
                if item in addresses or (item.name is not None and item.name in names):
                    where = f"{origin}: " if origin else ""
                    raise IsaError(f"{where}duplicate label {item.name!r}")
                addresses[item] = address
                if item.name is not None:
                    names.add(item.name)
            elif not isinstance(item, Comment):
                address += 1
        return addresses

    def link(self, cfg: IsaConfig = BASE) -> Image:
        size = self.size
        if size > cfg.program_words:
            raise IsaError(
                f"program contains {size} words; maximum is {cfg.program_words}"
            )
        addresses = self._addresses()

        def resolve(label: Label) -> int:
            if label not in addresses:
                raise IsaError(f"undefined label {label.name or repr(label)}")
            return addresses[label]

        words: list[int] = []
        for item, origin in zip(self.items, self.origins):
            if isinstance(item, (Label, Comment)):
                continue
            try:
                words.append(encode(item, cfg, resolve))
            except IsaError as exc:
                if str(exc).startswith("line "):
                    raise
                where = origin or f"word {len(words)} ({format_instruction(item)})"
                raise IsaError(f"{where}: {exc}") from exc
        symbols = {
            label.name: address for label, address in addresses.items() if label.name
        }
        return Image(words, symbols, cfg)

    def to_asm(self) -> str:
        """Return assembly text that the text assembler parses back to this program."""

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
                lines.append(f"{label_name(item)}:")
            elif isinstance(item, Comment):
                lines.append(f"# {item.text}" if item.text else "#")
            else:
                lines.append(format_instruction(item, label_name))
        return "\n".join(lines) + "\n"
