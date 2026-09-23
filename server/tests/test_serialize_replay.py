import json
from pathlib import Path

from opengwt.bots import RandomBot
from opengwt.core.engine import acting_seat, apply, legal_intents, new_match
from opengwt.core.model import Deck, Library, Phase
from opengwt.core.replay import record_from_dict, record_to_dict, replay
from opengwt.core.serialize import canonical_json, state_from_dict, state_hash, state_to_dict
from opengwt.sim.cli import run_match

GOLDEN = Path(__file__).parent / "replays" / "random-vs-random-seed-1.json"


def _random_play(lib: Library, decks: tuple[Deck, Deck], seed: int, steps: int):  # type: ignore[no-untyped-def]
    state, _ = new_match(lib, decks, seed)
    bots = (RandomBot(seed), RandomBot(seed + 100))
    for _ in range(steps):
        if state.phase is Phase.MATCH_OVER:
            break
        seat = acting_seat(state)
        assert seat is not None
        intent = bots[seat].choose(lib, state, seat, legal_intents(lib, state, seat))
        state, _ = apply(lib, state, seat, intent)
    return state


def test_state_round_trips_canonically(library: Library, starter_decks: tuple[Deck, Deck]) -> None:
    state = _random_play(library, starter_decks, seed=21, steps=25)
    once = canonical_json(state_to_dict(state))
    again = canonical_json(state_to_dict(state_from_dict(json.loads(once))))
    assert once == again
    assert state_hash(state) == state_hash(state_from_dict(json.loads(once)))


def test_apply_does_not_mutate_its_input(
    library: Library, starter_decks: tuple[Deck, Deck]
) -> None:
    state = _random_play(library, starter_decks, seed=4, steps=6)
    before = state_hash(state)
    seat = acting_seat(state)
    assert seat is not None
    apply(library, state, seat, legal_intents(library, state, seat)[0])
    assert state_hash(state) == before


def test_replay_reproduces_random_matches(
    library: Library, starter_decks: tuple[Deck, Deck]
) -> None:
    hashes = set()
    for seed in range(1, 6):
        bots = (RandomBot(seed), RandomBot(seed + 100))
        record, final, _ = run_match(library, starter_decks, seed, bots)
        again, _ = replay(library, record_from_dict(record_to_dict(record)))
        assert state_hash(again) == state_hash(final)
        hashes.add(state_hash(final))
    assert len(hashes) == 5


def test_golden_record_still_replays(library: Library) -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    record = record_from_dict(golden["record"])
    final, _ = replay(library, record)
    assert final.phase is Phase.MATCH_OVER
    assert state_hash(final) == golden["final_hash"], (
        "the rules changed in a way that breaks replay of an existing record; "
        "if that is intended, regenerate the golden file and call it out in the pull request"
    )
