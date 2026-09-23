"""Reference vectors for the core's random streams (ADR 0010). They pin the label strings, the
block layout and the instance-id length: changing any of them breaks every replay record."""

import pytest

from opengwt.core.rng import (
    INSTANCE_ID_HEX,
    LABEL_BOT,
    LABEL_ENGINE,
    LABEL_IDS,
    Stream,
    bot_stream,
    engine_stream,
    instance_id,
    parse_seed,
    seed_from_int,
)

SEED = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"

# SHA-256(label || seed || n), n as 8 big-endian bytes, read as eight big-endian 32-bit words.
ENGINE_BLOCK_0 = [
    0xA9BF8CFA,
    0xE180E4DA,
    0x4070647C,
    0x50994DB9,
    0x5A3F5DA1,
    0xB718791F,
    0x254B7B83,
    0x785AABC0,
]
ENGINE_BLOCK_1_START = [0xFA2F858A, 0x98AB171A]
BOT_17_START = [0xF8300DBE, 0x4D31372F, 0x53F1348C]


def test_labels_and_id_length_are_pinned() -> None:
    assert LABEL_ENGINE == b"opengwt/engine"
    assert LABEL_IDS == b"opengwt/ids"
    assert LABEL_BOT == b"opengwt/bot/"
    assert INSTANCE_ID_HEX == 12


def test_engine_stream_matches_reference_vectors() -> None:
    rng = engine_stream(SEED)
    assert [rng.next_u32() for _ in range(10)] == ENGINE_BLOCK_0 + ENGINE_BLOCK_1_START


def test_instance_ids_match_reference_vectors() -> None:
    assert instance_id(SEED, 0) == "c470f8889f170"
    assert instance_id(SEED, 1) == "cbd482bf7044e"


def test_bot_stream_is_labelled_with_the_decision_index() -> None:
    rng = bot_stream(SEED, 17)
    assert [rng.next_u32() for _ in range(3)] == BOT_17_START
    assert bot_stream(SEED, 0).next_u32() != bot_stream(SEED, 1).next_u32()


def test_streams_with_other_labels_are_unrelated() -> None:
    engine = engine_stream(SEED)
    other = Stream(SEED, b"opengwt/other")
    assert [engine.next_u32() for _ in range(8)] != [other.next_u32() for _ in range(8)]


def test_state_round_trip_continues_the_stream() -> None:
    a = engine_stream(SEED)
    for _ in range(11):
        a.next_u32()
    b = engine_stream(SEED, a.block, a.pos)
    assert (a.block, a.pos) == (1, 3)
    assert [a.next_u32() for _ in range(20)] == [b.next_u32() for _ in range(20)]


def test_below_stays_in_range_and_is_deterministic() -> None:
    a, b = engine_stream(SEED), engine_stream(SEED)
    xs = [a.below(7) for _ in range(500)]
    assert xs == [b.below(7) for _ in range(500)]
    assert set(xs) == set(range(7))
    with pytest.raises(ValueError):
        a.below(0)


def test_shuffle_is_a_permutation_and_seed_dependent() -> None:
    items = list(range(20))
    one, two = list(items), list(items)
    engine_stream(seed_from_int(1)).shuffle(one)
    engine_stream(seed_from_int(2)).shuffle(two)
    assert sorted(one) == items and sorted(two) == items
    assert one != two


@pytest.mark.parametrize("bad", ["", "00" * 31, "0" * 63 + "G", "0" * 63 + "A", "0" * 65])
def test_seeds_are_64_lowercase_hex_characters(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_seed(bad)
    assert len(parse_seed(SEED)) == 32
    assert seed_from_int(1) == "0" * 63 + "1"
