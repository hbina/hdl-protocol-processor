"""Every checked-in program keeps its exact encoding under every ISA variant."""

import json

import pytest

from tools.snapshot_isa import GOLDEN, ROOT, snapshot

EXPECTED = json.loads(GOLDEN.read_text())
ACTUAL = snapshot()


def test_snapshot_covers_the_same_sources():
    assert sorted(ACTUAL) == sorted(EXPECTED)


@pytest.mark.parametrize("source", sorted(EXPECTED))
def test_source_encoding_is_unchanged(source):
    assert (ROOT / source).exists()
    assert ACTUAL[source] == EXPECTED[source]
