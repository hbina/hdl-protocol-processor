"""Fixed 20-byte header checksum generator/checker; no packet parsing or state.

The first network byte occupies header[159:152]. The checksum field is at
bytes 10:11. Generation ignores that field; validation includes it. The full
header must be present at once. IPv4 options, streaming, and framing are excluded.
"""

from collections.abc import Sequence

from combhdl import (
    Add,
    Bit,
    BitNot,
    CompileError,
    Component,
    Const,
    Eq,
    Expr,
    Input,
    Output,
    Slice,
    Truncate,
    ZeroExtend,
)


def wide_sum(words: Sequence[Expr]) -> Expr:
    """Construct a balanced adder tree with enough bits to preserve every carry."""
    if not words or any(word.width != words[0].width for word in words):
        raise CompileError("wide_sum requires nonempty, equal-width words")
    width = words[0].width + (len(words) - 1).bit_length()
    level = [ZeroExtend(word, width) for word in words]
    while len(level) > 1:
        level = [
            Add(level[i], level[i + 1]) if i + 1 < len(level) else level[i]
            for i in range(0, len(level), 2)
        ]
    return level[0]


def fold_sum16(total: Expr) -> Expr:
    """Fold a 16..32-bit unsigned sum into a 16-bit one's-complement sum."""
    if not 16 <= total.width <= 32:
        raise CompileError("fold_sum16 requires a 16..32-bit sum")
    if total.width == 16:
        return total
    # The first fold is at most 0x1fffe, so one final end-around carry suffices.
    first = Add(
        ZeroExtend(Truncate(total, 16), 17),
        ZeroExtend(Slice(total, 16, total.width - 16), 17),
    )
    return Add(Truncate(first, 16), ZeroExtend(Bit(first, 16), 16))


header = Input("header", 160)
words = [Slice(header, 16 * (9 - index), 16) for index in range(10)]
# This exact node is reused by generation and validation. It is not storage.
shared_sum = wide_sum(words[:5] + words[6:])
checksum = BitNot(fold_sum16(shared_sum))
with_checksum = Add(shared_sum, ZeroExtend(words[5], shared_sum.width))
valid = Eq(fold_sum16(with_checksum), Const(0xFFFF, 16))
component = Component(
    "ipv4_checksum",
    [header],
    [Output("checksum", checksum), Output("valid", valid)],
)
