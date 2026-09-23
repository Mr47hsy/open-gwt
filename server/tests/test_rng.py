from opengwt.core.rng import Pcg32

# First outputs of the reference pcg32 demo for pcg32_srandom_r(&rng, 42u, 54u).
REFERENCE = [0xA15C02B7, 0x7B47F409, 0xBA1D3330, 0x83D2F293, 0xBFA4784B, 0xCBED606E]


def test_matches_reference_stream() -> None:
    rng = Pcg32(42, 54)
    assert [rng.next_u32() for _ in REFERENCE] == REFERENCE


def test_state_round_trip_continues_the_stream() -> None:
    a = Pcg32(7)
    a.next_u32()
    b = Pcg32.from_state(a.state, a.inc)
    assert [a.next_u32() for _ in range(5)] == [b.next_u32() for _ in range(5)]


def test_below_stays_in_range_and_is_deterministic() -> None:
    a, b = Pcg32(3), Pcg32(3)
    xs = [a.below(7) for _ in range(500)]
    assert xs == [b.below(7) for _ in range(500)]
    assert set(xs) == set(range(7))


def test_shuffle_is_a_permutation_and_seed_dependent() -> None:
    items = list(range(20))
    one, two = list(items), list(items)
    Pcg32(1).shuffle(one)
    Pcg32(2).shuffle(two)
    assert sorted(one) == items and sorted(two) == items
    assert one != two
