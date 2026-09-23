import json
from pathlib import Path

from opengwt.core.engine import acting_seat, apply, legal_intents, new_match
from opengwt.core.model import Deck, Library, MatchState, Phase
from opengwt.core.replay import record_from_dict, record_to_dict, replay
from opengwt.core.rng import seed_from_int
from opengwt.core.serialize import canonical_json, state_from_dict, state_hash, state_to_dict
from opengwt.core.view import player_view
from opengwt.sim.cli import run_match, sim_bot

GOLDEN = Path(__file__).parent / "replays" / "random-vs-random-seed-1.json"
SEED_A = "5eed" * 16


def _random_play(lib: Library, decks: tuple[Deck, Deck], n: int, steps: int) -> MatchState:
    state, _ = new_match(lib, decks, seed_from_int(n))
    bots = (sim_bot("random", n * 2 + 1), sim_bot("random", n * 2 + 2))
    for _ in range(steps):
        if state.phase is Phase.MATCH_OVER:
            break
        seat = acting_seat(state)
        assert seat is not None
        intent = bots[seat].choose(lib, state, seat, legal_intents(lib, state, seat))
        state, _ = apply(lib, state, seat, intent)
    return state


def test_state_round_trips_canonically(library: Library, starter_decks: tuple[Deck, Deck]) -> None:
    for n, steps in ((21, 25), (22, 60), (23, 400)):
        state = _random_play(library, starter_decks, n, steps)
        once = canonical_json(state_to_dict(state))
        again = canonical_json(state_to_dict(state_from_dict(json.loads(once))))
        assert once == again
        assert state_hash(state) == state_hash(state_from_dict(json.loads(once)))


def test_apply_does_not_mutate_its_input(
    library: Library, starter_decks: tuple[Deck, Deck]
) -> None:
    state = _random_play(library, starter_decks, 4, 30)
    before = state_hash(state)
    seat = acting_seat(state)
    assert seat is not None
    apply(library, state, seat, legal_intents(library, state, seat)[0])
    assert state_hash(state) == before


def test_replay_reproduces_random_matches(
    library: Library, starter_decks: tuple[Deck, Deck]
) -> None:
    hashes = set()
    for n in range(1, 6):
        bots = (sim_bot("random", n * 2 + 1), sim_bot("random", n * 2 + 2))
        record, final, _ = run_match(library, starter_decks, seed_from_int(n), bots)
        again, _ = replay(library, record_from_dict(record_to_dict(record)))
        assert state_hash(again) == state_hash(final)
        hashes.add(state_hash(final))
    assert len(hashes) == 5


def test_golden_record_still_replays(library: Library) -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert golden["record"]["schema"] == "opengwt.record/2"
    record = record_from_dict(golden["record"])
    final, _ = replay(library, record)
    assert final.phase is Phase.MATCH_OVER
    assert state_hash(final) == golden["final_hash"], (
        "the rules changed in a way that breaks replay of an existing record; "
        "if that is intended, regenerate the golden file and call it out in the pull request"
    )


def test_no_event_view_or_record_of_a_running_match_carries_the_seed(
    library: Library, starter_decks: tuple[Deck, Deck]
) -> None:
    """ADR 0010: the seed stays on the server until the match is over."""
    record, _, _ = run_match(
        library, starter_decks, SEED_A, (sim_bot("random", 1), sim_bot("random", 2))
    )
    state, events = new_match(library, record.decks, record.seed, record.rules)
    assert events[0].type == "match_started"
    texts = [canonical_json(e.data) for e in events]
    for seat, intent in record.intents:
        state, more = apply(library, state, seat, intent)
        texts.extend(canonical_json(e.data) for e in more)
        texts.extend(canonical_json(player_view(library, state, s)) for s in (0, 1))
    for text in texts:
        assert SEED_A not in text and '"seed"' not in text
    assert record_to_dict(record)["seed"] == SEED_A


def test_instance_ids_are_opaque(library: Library, starter_decks: tuple[Deck, Deck]) -> None:
    """Ids come from the id stream: neither deck-list order nor draw order shows in them."""
    state, _ = new_match(library, starter_decks, SEED_A)
    ids = [c.instance for p in state.players for c in p.deck + p.hand]
    assert len(set(ids)) == len(ids)
    assert all(len(i) == 13 and i.startswith("c") for i in ids)
    assert ids != sorted(ids)
