"""End-to-end tests over the HTTP and WebSocket API with the memory backends and SQLite."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import WebSocketTestSession

from opengwt.bots import RandomBot
from opengwt.core.engine import apply, legal_intents, new_match
from opengwt.core.intents import (
    CancelChoice,
    Choose,
    EndMulligan,
    EndTurn,
    Intent,
    Mulligan,
    Pass,
    PlayCard,
    UseOrder,
)
from opengwt.core.model import Kind, MatchState, Phase, Row, Rules, Side
from opengwt.core.replay import record_from_dict, replay
from opengwt.core.rng import bot_stream
from opengwt.core.serialize import state_from_dict, state_hash
from opengwt.data import load_data
from opengwt.server import app as app_module
from opengwt.server.app import create_app
from opengwt.server.backends import (
    InlineTaskRunner,
    MemoryEventBus,
    MemoryMatchStore,
    VersionConflict,
)
from opengwt.server.config import ConfigError, Settings
from opengwt.server.db.models import DeckRow, MatchRow
from opengwt.server.db.session import alembic_config, make_engine, session_scope
from opengwt.server.routers import ws as ws_router
from opengwt.server.services import matches as match_service
from opengwt.server.services.auth import create_token
from opengwt.server.services.content import load_content
from opengwt.server.services.matches import MatchService

REPO = Path(__file__).resolve().parents[2]
PINNED_SEED = "0123456789abcdef" * 4


SECRET = "test-secret-long-enough-for-hmac-sha256-keys"


def _settings(tmp_path: Path, **overrides: Any) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        data_dir=REPO / "data",
        auth_secret=SECRET,
        **overrides,
    )


@pytest.fixture(autouse=True)
def _scripts_play_faster_than_people(monkeypatch: pytest.MonkeyPatch) -> None:
    """A scripted client plays a whole match within a second, redraws included; the rate limit
    is for people and would close its socket (4429)."""
    monkeypatch.setattr(ws_router, "INTENTS_PER_SECOND", 10_000)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(tmp_path))) as test_client:
        yield test_client


def _guest(client: TestClient, name: str = "guest") -> tuple[dict[str, str], str]:
    response = client.post("/auth/guest", json={"display_name": name})
    assert response.status_code == 200, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['token']}"}, body["token"]


class Scripted:
    """A scripted client: redraws once in each mulligan, then plays the first legal card at the
    left end of its row, otherwise passes; never sees more than its view, and asserts on every
    message that hidden information stayed hidden."""

    def __init__(self, ws: WebSocketTestSession, seat: int) -> None:
        self.ws = ws
        self.seat = seat
        self.seq = 0
        self.view: dict[str, Any] | None = None
        self.result: dict[str, Any] | None = None
        self.sent = 0
        self.events: list[dict[str, Any]] = []
        self.messages: list[dict[str, Any]] = []
        self.redrew_in_round = 0

    def receive(self) -> dict[str, Any]:
        message: dict[str, Any] = self.ws.receive_json()
        self.messages.append(message)
        assert '"seed"' not in json.dumps(message)
        kind = message["type"]
        if kind == "view":
            self.view = message["view"]
            self.seq = message["seq"]
            assert "hand" not in self.view["opponent"]
            assert self.view["me"]["seat"] == self.seat
        elif kind == "events":
            for event in message["events"]:
                self.events.append(event)
                private = event["type"] in ("card_drawn", "card_redrawn")
                if private and event["seat"] != self.seat:
                    assert "card" not in event and "instance" not in event
                if event["type"] == "choice_requested" and event["seat"] != self.seat:
                    assert "options" not in event
        elif kind == "match_over":
            self.result = message["result"]
        elif kind == "error":
            raise AssertionError(f"server error: {message}")
        return message

    def my_move(self) -> dict[str, Any] | None:
        view = self.view
        if view is None or view["phase"] == "match_over":
            return None
        legal = view["legal_intents"]
        if not legal:
            return None
        if view["phase"] == "mulligan":
            redraws = [i for i in legal if i["kind"] == "mulligan"]
            if redraws and self.redrew_in_round != view["round"]:
                self.redrew_in_round = view["round"]
                return redraws[0]
            return {"kind": "end_mulligan"}
        if view["phase"] == "choosing":
            return legal[0]
        if {"kind": "end_turn"} in legal:
            return {"kind": "end_turn"}
        plays = [i for i in legal if i["kind"] == "play_card"]
        if not plays:
            return {"kind": "pass"}
        play = dict(plays[0])
        if "row" in play:
            play["position"] = 0
        return play

    def step(self) -> None:
        """Act on the current view if it is this seat's move, then wait for the next view."""
        move = self.my_move()
        if move is not None:
            self.send(move)
        while True:
            message = self.receive()
            if message["type"] in ("view", "match_over"):
                return

    def send(self, intent: dict[str, Any]) -> None:
        self.sent += 1
        self.ws.send_json(
            {"type": "intent", "intent_id": f"s{self.seat}-{self.sent}", "intent": intent}
        )


def _handshake(ws: WebSocketTestSession, expect_view: bool = True) -> tuple[int, dict[str, Any]]:
    hello = ws.receive_json()
    assert hello["type"] == "hello" and hello["protocol"] == 2
    if not expect_view:
        return hello["seat"], hello
    view = ws.receive_json()
    assert view["type"] == "view"
    return hello["seat"], view


def test_health_pack_and_i18n(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    pack = client.get("/content/pack")
    assert pack.status_code == 200 and pack.json()["schema"] == "opengwt.pack/2"
    assert pack.json()["rules"]["row_capacity"] == 9
    decks = {d["id"]: d for d in pack.json()["decks"]}
    assert decks["starter-a"]["provisions"] == {"used": 163, "budget": 165}
    assert decks["starter-b"]["provisions"] == {"used": 165, "budget": 165}
    etag = pack.headers["etag"]
    assert client.get("/content/pack", headers={"If-None-Match": etag}).status_code == 304
    locales = client.get("/content/i18n").json()
    assert locales["locales"] == ["en", "ru", "zh-CN"] and locales["pack_hash"] == etag.strip('"')
    table = client.get("/content/i18n/zh-CN").json()
    assert table["card.u-1001.name"] == "占位 A 单位 1"
    missing = client.get("/content/i18n/fr")
    assert missing.status_code == 404
    error = missing.json()["error"]
    assert error["code"] == "locale_unsupported" and error["params"] == {"locale": "fr"}
    assert error["message"] == "The locale fr is not supported."


def test_errors_are_rendered_in_the_negotiated_locale(client: TestClient) -> None:
    body = client.get("/me", headers={"Accept-Language": "ru, en;q=0.5"}).json()["error"]
    assert body["code"] == "unauthorised"
    assert body["message_key"] == "error.unauthorised"
    assert body["message"] == "Войдите, чтобы сделать это."
    headers, _ = _guest(client)
    assert client.patch("/me", headers=headers, json={"locale": "zh-CN"}).status_code == 200
    body = client.get("/matches/nope", headers={**headers, "Accept-Language": "ru"}).json()
    assert body["error"]["message"] == "对局不存在。"  # the profile locale wins over the header
    assert client.patch("/me", headers=headers, json={"locale": "fr"}).status_code == 422


def _starter_body(starter: str = "starter-a", **changes: Any) -> dict[str, Any]:
    """A ``PUT /decks`` body with a starter deck's leader, stratagem and cards."""
    deck = yaml.safe_load((REPO / "data" / "decks" / f"{starter}.deck.yaml").read_text())
    body = {
        "name": starter,
        "faction": deck["faction"],
        "leader": deck["leader"],
        "stratagem": deck["stratagem"],
        "cards": deck["cards"],
    }
    return {**body, **changes}


def _with_count(cards: list[dict[str, Any]], card: str, count: int) -> list[dict[str, Any]]:
    return [{**c, "count": count} if c["id"] == card else c for c in cards]


def _db(client: TestClient, work: Callable[[AsyncSession], Awaitable[Any]]) -> Any:
    """Run ``work`` on the app's own database, inside its event loop, and commit."""
    assert client.portal is not None
    sessions = client.app.state.sessions  # type: ignore[attr-defined]

    async def run() -> Any:
        async with session_scope(sessions) as session:
            return await work(session)

    return client.portal.call(run)


def test_decks_are_validated_by_the_rules(client: TestClient) -> None:
    """Every broken rule is reported at once, each as its key, the card it is about and the
    parameters its message takes (match.md §10)."""
    headers, _ = _guest(client)
    assert client.get("/decks", headers=headers).json() == []
    bad = client.put(
        "/decks/mine",
        headers=headers,
        json={
            "name": "x",
            "faction": "placeholder-a",
            "leader": "l-1001",
            "stratagem": "g-0002",
            "cards": [{"id": "u-1001", "count": 3}, {"id": "u-2001", "count": 1}],
        },
    )
    assert bad.status_code == 422
    error = bad.json()["error"]
    assert error["code"] == "deck_illegal" and error["message"] == "This deck is not legal."
    assert error["details"]["problems"] == [
        {
            "key": "error.deck.wrong-faction",
            "card": "u-2001",
            "params": {"card": "@card.u-2001.name"},
        },
        {"key": "error.deck.too-few-cards", "params": {"count": 4, "min": 25}},
        {"key": "error.deck.too-few-units", "params": {"count": 4, "min": 13}},
        {
            "key": "error.deck.too-many-copies",
            "card": "u-1001",
            "params": {"card": "@card.u-1001.name", "count": 3, "limit": 2},
        },
    ]
    unknown = client.put(
        "/decks/mine", headers=headers, json=_starter_body(leader="@l-0000", stratagem="g-0001x")
    )
    assert unknown.json()["error"]["details"]["problems"] == [
        {"key": "error.deck.unknown-card", "card": "@l-0000", "params": {"card": "@@l-0000"}},
        {"key": "error.deck.unknown-card", "card": "g-0001x", "params": {"card": "g-0001x"}},
    ]
    no_leader = client.put(
        "/decks/mine",
        headers=headers,
        json={"name": "x", "faction": "placeholder-a", "cards": [{"id": "u-1001", "count": 25}]},
    )
    assert no_leader.status_code == 422  # a deck names its leader and its stratagem
    good = client.put("/decks/mine", headers=headers, json=_starter_body(name="mine"))
    assert good.status_code == 200 and good.json()["deck_id"] == "mine"
    saved = client.get("/decks", headers=headers).json()
    assert [d["deck_id"] for d in saved] == ["mine"]
    assert saved[0]["provisions"] == {"used": 163, "budget": 165} and saved[0]["problems"] == []
    assert saved[0] == good.json()
    other, _ = _guest(client, "other")
    assert client.delete("/decks/mine", headers=other).status_code == 404
    assert client.delete("/decks/mine", headers=headers).status_code == 204


def test_the_server_judges_decks_by_the_rules_it_plays_with(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One ``Rules`` value: the pack publishes it, saving a deck and starting a match judge by
    it, and a match stores it. A budget of 151 + 15 takes a deck of 166 provisions, which the
    default rules would refuse, and refuses one of 167 against that budget."""
    rules = replace(Rules(), provision_base=151)
    monkeypatch.setattr(app_module, "load_content", lambda data_dir: load_content(data_dir, rules))
    with TestClient(create_app(_settings(tmp_path))) as client:
        assert client.get("/content/pack").json()["rules"]["provision_base"] == 151
        headers, _ = _guest(client)
        body = _starter_body()
        # 163 - 4 - 5 + 6 + 6: u-1001 and u-1002 out, a second u-1005 and u-1006 in
        cards = _with_count(_with_count(body["cards"], "u-1005", 2), "u-1006", 2)
        body["cards"] = [c for c in cards if c["id"] not in ("u-1001", "u-1002")]
        saved = client.put("/decks/dear", headers=headers, json=body)
        assert saved.status_code == 200, saved.text
        assert saved.json()["provisions"] == {"used": 166, "budget": 166}
        body["cards"] = _with_count(_with_count(body["cards"], "u-1003", 1), "u-1004", 2)
        refused = client.put("/decks/dearer", headers=headers, json=body)
        assert refused.status_code == 422
        assert refused.json()["error"]["details"]["problems"] == [
            {"key": "error.deck.over-budget", "params": {"used": 167, "budget": 166}}
        ]
        started = client.post("/matches", headers=headers, json={"mode": "bot", "deck_id": "dear"})
        assert started.status_code == 201
        room = client.post(
            "/matches", headers=headers, json={"mode": "room", "deck_id": "starter-a"}
        )
        match_id = room.json()["match_id"]

        async def stored_rules(session: AsyncSession) -> Any:
            row = await session.get(MatchRow, match_id)
            assert row is not None
            return row.rules

        assert _db(client, stored_rules)["provision_base"] == 151


def test_a_saved_deck_the_rules_now_refuse_is_shown_and_cannot_start_a_match(
    client: TestClient,
) -> None:
    """A deck saved under older rules stays saved: ``GET /decks`` shows what it breaks, a match
    refuses it with the same problems, and saving it again fixes it (match.md §2)."""
    headers, _ = _guest(client)
    body = _starter_body(name="old")
    assert client.put("/decks/old", headers=headers, json=body).status_code == 200
    three = _with_count(body["cards"], "u-1003", 3)

    async def break_it(session: AsyncSession) -> None:
        row = await session.get(DeckRow, "old")
        assert row is not None
        row.cards = three

    _db(client, break_it)
    problem = {
        "key": "error.deck.too-many-copies",
        "card": "u-1003",
        "params": {"card": "@card.u-1003.name", "count": 3, "limit": 2},
    }
    over = {"key": "error.deck.over-budget", "params": {"used": 167, "budget": 165}}
    listed = client.get("/decks", headers=headers).json()
    assert listed[0]["problems"] == [problem, over]
    assert listed[0]["provisions"] == {"used": 167, "budget": 165}
    refused = client.post("/matches", headers=headers, json={"mode": "bot", "deck_id": "old"})
    assert refused.status_code == 422
    assert refused.json()["error"]["details"] == {"problems": [problem, over]}
    assert client.put("/decks/old", headers=headers, json=body).status_code == 200
    started = client.post("/matches", headers=headers, json={"mode": "bot", "deck_id": "old"})
    assert started.status_code == 201


def test_joining_a_room_whose_deck_the_rules_now_refuse_is_refused(client: TestClient) -> None:
    """A room keeps the deck it was made with; if deck building tightened since, the join is
    refused with the problems and the seat whose deck has them, and the room keeps waiting."""
    h0, _ = _guest(client, "a")
    h1, _ = _guest(client, "b")
    room = client.post("/matches", headers=h0, json={"mode": "room", "deck_id": "starter-a"}).json()

    async def break_it(session: AsyncSession) -> None:
        row = await session.get(MatchRow, room["match_id"])
        assert row is not None
        deck = dict(row.decks[0])
        deck["cards"] = [*deck["cards"], deck["cards"][0], deck["cards"][0]]
        row.decks = [deck]

    _db(client, break_it)
    joined = client.post(
        "/matches/join", headers=h1, json={"room_code": room["room_code"], "deck_id": "starter-b"}
    )
    assert joined.status_code == 422
    details = joined.json()["error"]["details"]
    assert details["seat"] == 0
    assert [p["key"] for p in details["problems"]] == [
        "error.deck.too-many-copies",
        "error.deck.over-budget",
    ]
    status = client.get(f"/matches/{room['match_id']}", headers=h0).json()
    assert status["status"] == "waiting"


def test_full_match_against_the_bot_and_its_replay(client: TestClient) -> None:
    headers, token = _guest(client)
    created = client.post("/matches", headers=headers, json={"mode": "bot", "deck_id": "starter-a"})
    assert created.status_code == 201, created.text
    match_id = created.json()["match_id"]
    assert created.json()["ws_url"].endswith(f"/ws/matches/{match_id}")

    with client.websocket_connect(f"/ws/matches/{match_id}?token={token}") as ws:
        seat, first = _handshake(ws)
        me = Scripted(ws, seat)
        me.view, me.seq = first["view"], first["seq"]
        for _ in range(400):
            if me.result is not None:
                break
            me.step()
        assert me.result is not None, "the match did not finish"
        assert me.result["winner"] in (0, 1, None)

    status = client.get(f"/matches/{match_id}", headers=headers).json()
    assert status["status"] == "finished" and status["seat"] == seat
    replay_body = client.get(f"/matches/{match_id}/replay", headers=headers).json()
    record = record_from_dict(replay_body["record"])
    library = load_data(REPO / "data").library
    final, _ = replay(library, record)
    assert state_hash(final) == replay_body["result"]["final_hash"]
    assert any(seat_ != seat for seat_, _ in record.intents), "the bot's intents are in the record"
    stranger, _ = _guest(client, "stranger")
    assert client.get(f"/matches/{match_id}/replay", headers=stranger).status_code == 403


def test_the_seed_reaches_no_client_before_the_match_ends(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the seed and the open-source shuffle a client rebuilds both decks' order, so no
    message may carry it while the match runs, resync from the first event included (match.md
    §11). The replay record, served only after the end, is where it belongs."""
    monkeypatch.setattr(match_service, "new_seed", lambda: PINNED_SEED)
    headers, token = _guest(client)
    created = client.post("/matches", headers=headers, json={"mode": "bot", "deck_id": "starter-a"})
    match_id = created.json()["match_id"]

    with client.websocket_connect(f"/ws/matches/{match_id}?token={token}") as ws:
        seat, first = _handshake(ws)
        me = Scripted(ws, seat)
        me.view, me.seq = first["view"], first["seq"]
        ws.send_json({"type": "resync", "since_seq": 0})
        while me.receive()["type"] != "view":
            pass
        assert me.events[0]["seq"] == 1 and me.events[0]["type"] == "match_started"
        for _ in range(400):
            if me.result is not None:
                break
            me.step()
        assert me.result is not None, "the match did not finish"

    for message in [created.json(), first, *me.messages]:
        text = json.dumps(message)
        assert '"seed"' not in text and PINNED_SEED not in text, message
    record = client.get(f"/matches/{match_id}/replay", headers=headers).json()["record"]
    assert record["seed"] == PINNED_SEED


def _play_bot_match(client: TestClient) -> tuple[dict[str, str], str, Scripted]:
    headers, token = _guest(client)
    created = client.post("/matches", headers=headers, json={"mode": "bot", "deck_id": "starter-a"})
    match_id = created.json()["match_id"]
    with client.websocket_connect(f"/ws/matches/{match_id}?token={token}") as ws:
        seat, first = _handshake(ws)
        me = Scripted(ws, seat)
        me.view, me.seq = first["view"], first["seq"]
        for _ in range(400):
            if me.result is not None:
                break
            me.step()
        assert me.result is not None, "the match did not finish"
    return headers, match_id, me


def test_the_bot_draws_from_its_own_stream_for_each_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR 0010: decision ``i`` of the intent log is made by a fresh bot on the stream labelled
    ``i``, so the bot keeps no state between calls and its choices are not the match's stream."""
    monkeypatch.setattr(match_service, "new_seed", lambda: PINNED_SEED)
    with TestClient(create_app(_settings(tmp_path, bot="random"))) as client:
        headers, match_id, me = _play_bot_match(client)
        body = client.get(f"/matches/{match_id}/replay", headers=headers).json()
    record = record_from_dict(body["record"])
    library = load_data(REPO / "data").library
    state, _ = new_match(library, record.decks, record.seed, record.rules)
    bot_decisions = 0
    for index, (seat, intent) in enumerate(record.intents):
        if seat != me.seat:
            bot = RandomBot(bot_stream(PINNED_SEED, index))
            assert intent == bot.choose(library, state, seat, legal_intents(library, state, seat))
            bot_decisions += 1
        state, _ = apply(library, state, seat, intent)
    assert bot_decisions > 5 and state_hash(state) == body["result"]["final_hash"]


def test_matches_from_before_phase_b_stay_as_history(tmp_path: Path) -> None:
    """Migration 0002 turns ``matches.seed`` into text; a v1 match keeps its decimal seed and is
    served as its ``opengwt.record/1`` data."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    v1_deck = {"faction": "placeholder-a", "leader": "a-l-0001", "cards": ["a-u-0001"]}

    async def old_database() -> str:
        engine = make_engine(url)
        config = alembic_config()

        def upgrade(revision: str) -> Any:
            def run(connection: Any) -> None:
                config.attributes["connection"] = connection
                command.upgrade(config, revision)

            return run

        async with engine.begin() as connection:
            await connection.run_sync(upgrade("0001"))
            await connection.execute(
                text(
                    "INSERT INTO players (id, display_name, locale, created_at) "
                    "VALUES ('p1', 'old', NULL, '2026-09-01 00:00:00')"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO matches (id, mode, status, room_code, seed, seat0_player_id, "
                    "seat1_player_id, decks, rules, result, created_at, finished_at) VALUES "
                    "('m1', 'bot', 'finished', NULL, 1234567, 'p1', 'bot', :decks, :rules, "
                    ":result, '2026-09-01 00:00:00', '2026-09-01 00:10:00')"
                ),
                {
                    "decks": json.dumps([v1_deck, v1_deck]),
                    "rules": json.dumps({"hand_size": 10, "lives": 2}),
                    "result": json.dumps({"winner": 0}),
                },
            )
            await connection.execute(
                text(
                    'INSERT INTO match_intents (match_id, "index", seat, intent) '
                    "VALUES ('m1', 0, 0, :intent)"
                ),
                {"intent": json.dumps({"kind": "pass"})},
            )
        async with engine.begin() as connection:
            await connection.run_sync(upgrade("head"))
            seed = (await connection.execute(text("SELECT seed FROM matches"))).scalar_one()
        await engine.dispose()
        return str(seed)

    assert asyncio.run(old_database()) == "1234567"
    token = create_token("p1", SECRET, 600)
    headers = {"Authorization": f"Bearer {token}"}
    with TestClient(create_app(_settings(tmp_path))) as client:
        assert client.get("/matches/m1", headers=headers).json()["status"] == "finished"
        body = client.get("/matches/m1/replay", headers=headers).json()
    assert body["record"] == {
        "schema": "opengwt.record/1",
        "seed": 1234567,
        "rules": {"hand_size": 10, "lives": 2},
        "decks": [v1_deck, v1_deck],
        "intents": [{"seat": 0, "intent": {"kind": "pass"}}],
    }


def test_two_clients_play_through_a_room_and_one_reconnects(client: TestClient) -> None:
    h0, t0 = _guest(client, "a")
    h1, t1 = _guest(client, "b")
    room = client.post("/matches", headers=h0, json={"mode": "room", "deck_id": "starter-a"}).json()
    match_id, code = room["match_id"], room["room_code"]
    assert (
        client.post(
            "/matches/join", headers=h0, json={"room_code": code, "deck_id": "starter-b"}
        ).status_code
        == 409
    )
    joined = client.post(
        "/matches/join", headers=h1, json={"room_code": code, "deck_id": "starter-b"}
    )
    assert joined.status_code == 200 and joined.json()["match_id"] == match_id
    assert (
        client.post(
            "/matches/join", headers=h1, json={"room_code": code, "deck_id": "starter-b"}
        ).status_code
        == 409
    )

    with client.websocket_connect(f"/ws/matches/{match_id}?token={t0}") as ws0:
        s0, v0 = _handshake(ws0)
        a = Scripted(ws0, s0)
        a.view, a.seq = v0["view"], v0["seq"]
        with client.websocket_connect(f"/ws/matches/{match_id}?token={t1}") as ws1:
            s1, v1 = _handshake(ws1)
            b = Scripted(ws1, s1)
            b.view, b.seq = v1["view"], v1["seq"]
            assert {s0, s1} == {0, 1}
            players = {s0: a, s1: b}
            # play twelve moves, whoever is up
            for _ in range(12):
                actor = next((p for p in players.values() if p.my_move() is not None), None)
                assert actor is not None
                move = actor.my_move()
                assert move is not None
                actor.send(move)
                for p in players.values():
                    # each player receives the events batch and the view of that move
                    while True:
                        message = p.receive()
                        if message["type"] == "view":
                            break
            assert a.seq == b.seq > 0
            last_seq = a.seq

        # b's socket is gone; a reconnects and gets the same view back
        with client.websocket_connect(f"/ws/matches/{match_id}?token={t0}") as ws0b:
            s, again = _handshake(ws0b)
            assert s == s0 and again["seq"] == last_seq
            assert again["view"] == a.view
            ws0b.send_json({"type": "resync", "since_seq": 0})
            got_events = False
            while True:
                message = ws0b.receive_json()
                if message["type"] == "events":
                    got_events = True
                if message["type"] == "view" and message["seq"] == last_seq:
                    break
            assert got_events
            ws0b.send_json({"type": "ping"})
            assert ws0b.receive_json() == {"type": "pong"}


def test_illegal_intent_over_the_socket_is_an_error_message(client: TestClient) -> None:
    headers, token = _guest(client)
    match_id = client.post(
        "/matches", headers=headers, json={"mode": "bot", "deck_id": "starter-b"}
    ).json()["match_id"]
    with client.websocket_connect(f"/ws/matches/{match_id}?token={token}") as ws:
        _handshake(ws)
        ws.send_json({"type": "intent", "intent_id": "x1", "intent": {"kind": "pass"}})
        message = ws.receive_json()
        assert message["type"] == "error" and message["intent_id"] == "x1"
        assert message["code"] in ("illegal_intent", "not_your_turn")
        assert message["message"]
        ws.send_json({"type": "nonsense"})
        assert ws.receive_json()["code"] == "unknown_message"


def test_socket_rejects_strangers(client: TestClient) -> None:
    headers, _ = _guest(client)
    _, stranger_token = _guest(client, "stranger")
    match_id = client.post(
        "/matches", headers=headers, json={"mode": "bot", "deck_id": "starter-a"}
    ).json()["match_id"]
    with (
        pytest.raises(Exception),  # noqa: B017 - the close code is what matters
        client.websocket_connect(f"/ws/matches/{match_id}?token={stranger_token}") as ws,
    ):
        ws.receive_json()
    with (
        pytest.raises(Exception),  # noqa: B017
        client.websocket_connect(f"/ws/matches/{match_id}?token=garbage") as ws,
    ):
        ws.receive_json()


def test_the_turn_timer_plays_for_a_player_who_never_moves(tmp_path: Path) -> None:
    """match.md §9: a player who does not move within the turn timeout has their mulligan ended
    and their turns passed by the server, so a match against the bot still runs to its end."""
    with TestClient(create_app(_settings(tmp_path, turn_timeout_seconds=0.05))) as client:
        headers, _ = _guest(client)
        created = client.post(
            "/matches", headers=headers, json={"mode": "bot", "deck_id": "starter-a"}
        )
        match_id = created.json()["match_id"]
        give_up = time.monotonic() + 30
        while (status := client.get(f"/matches/{match_id}", headers=headers).json())[
            "status"
        ] != "finished":
            assert time.monotonic() < give_up, "the turn timer did not finish the match"
            time.sleep(0.05)
        body = client.get(f"/matches/{match_id}/replay", headers=headers).json()
    record = record_from_dict(body["record"])
    mine = [intent for seat, intent in record.intents if seat == status["seat"]]
    assert EndMulligan() in mine and Pass() in mine
    assert all(i in (EndMulligan(), CancelChoice(), Choose(0), Pass()) for i in mine), mine
    final, _ = replay(load_data(REPO / "data").library, record)
    assert state_hash(final) == body["result"]["final_hash"]


class _Room:
    """A room match between two guests, moved and timed out through ``MatchService`` directly
    so a test decides exactly which timer fires when."""

    def __init__(
        self, client: TestClient, decks: tuple[str, str] = ("starter-a", "starter-b")
    ) -> None:
        h0, _ = _guest(client, "a")
        h1, _ = _guest(client, "b")
        room = client.post("/matches", headers=h0, json={"mode": "room", "deck_id": decks[0]})
        self.match_id: str = room.json()["match_id"]
        joined = client.post(
            "/matches/join",
            headers=h1,
            json={"room_code": room.json()["room_code"], "deck_id": decks[1]},
        )
        assert joined.status_code == 200
        self.service: MatchService = client.app.state.matches  # type: ignore[attr-defined]
        assert client.portal is not None
        self.portal = client.portal

    def state(self) -> MatchState:
        loaded = self.portal.call(self.service.store.load, self.match_id)
        assert loaded is not None
        return state_from_dict(loaded[0]["state"])

    def legal(self, seat: int) -> list[Intent]:
        return legal_intents(self.service.content.library, self.state(), seat)

    def move(self, seat: int, intent: Intent) -> None:
        self.portal.call(self.service.apply, self.match_id, seat, intent)

    def timer(self, seat: int) -> Any:
        return self.service._deadlines.get((self.match_id, seat))

    def time_out(self, seat: int, timer: Any) -> None:
        self.portal.call(self.service.timeout_move, self.match_id, seat, timer.wait)


def test_a_timer_set_before_the_players_move_does_nothing(tmp_path: Path) -> None:
    """The opponent has passed, so the player's next turn follows their own. The timer set before
    they played a card and ended the turn must not pass on that next turn; only the one their
    moves re-armed may."""
    with TestClient(create_app(_settings(tmp_path, turn_timeout_seconds=3600))) as client:
        room = _Room(client)
        starter = room.state().starter
        player = 1 - starter
        room.move(starter, EndMulligan())
        room.move(player, EndMulligan())
        room.move(starter, Pass())
        stale = room.timer(player)
        assert stale is not None and room.timer(starter) is None

        play = next(i for i in room.legal(player) if isinstance(i, PlayCard) and i.row is not None)
        room.move(player, replace(play, position=0))
        room.move(player, EndTurn())
        after = room.state()
        assert after.turn == player and not after.played
        fresh = room.timer(player)
        assert fresh is not None and fresh != stale

        room.time_out(player, stale)
        assert room.state().seq == after.seq and not room.state().players[player].passed

        room.time_out(player, fresh)
        history = room.portal.call(room.service.history, room.match_id, after.seq)
        passed = [e for p in history for e in p["events"] if e["type"] == "player_passed"]
        assert [e["seat"] for e in passed] == [player]


def test_a_timeout_after_the_turns_card_ends_the_turn(tmp_path: Path) -> None:
    """match.md §9: once the card is played the turn waits for end_turn, and the timer ends it."""
    with TestClient(create_app(_settings(tmp_path, turn_timeout_seconds=3600))) as client:
        room = _Room(client)
        starter = room.state().starter
        room.move(starter, EndMulligan())
        room.move(1 - starter, EndMulligan())
        play = next(i for i in room.legal(starter) if isinstance(i, PlayCard) and i.row is not None)
        room.move(starter, replace(play, position=0))
        assert room.state().turn == starter and room.legal(starter)[0] == EndTurn()

        room.time_out(starter, room.timer(starter))
        after = room.state()
        assert after.turn == 1 - starter and not after.players[starter].passed


def test_a_timeout_after_an_activated_ability_plays_a_card(tmp_path: Path) -> None:
    """cards.md §11.4: after an activated ability the turn needs its card, so the timer cannot
    pass; it plays the first card at the right end of its row. Both decks are starter-a, whose
    stratagem needs no target, so whoever starts can use it on their first turn."""
    with TestClient(create_app(_settings(tmp_path, turn_timeout_seconds=3600))) as client:
        room = _Room(client, ("starter-a", "starter-a"))
        starter = room.state().starter
        room.move(starter, EndMulligan())
        room.move(1 - starter, EndMulligan())
        order = next(i for i in room.legal(starter) if isinstance(i, UseOrder))
        room.move(starter, order)
        state = room.state()
        assert state.ordered and not state.played and Pass() not in room.legal(starter)

        room.time_out(starter, room.timer(starter))
        after = room.state()
        assert after.played and after.turn == starter and not after.players[starter].passed


def _order_waiting_on_a_cancellable_choice(room: _Room) -> int:
    """Both decks are starter-b: the starter plays a unit, the other player passes, and the
    starter's stratagem — boost an ally — is ready. Returns the starter's seat."""
    lib = room.service.content.library
    starter = room.state().starter
    room.move(starter, EndMulligan())
    room.move(1 - starter, EndMulligan())
    hand = {c.instance: lib[c.card] for c in room.state().players[starter].hand}
    play = next(
        i
        for i in room.legal(starter)
        if isinstance(i, PlayCard)
        and i.row is Row.MELEE
        and hand[i.card].kind is Kind.UNIT
        and hand[i.card].side is Side.SELF
    )
    room.move(starter, replace(play, position=0))
    while room.state().pending is not None:
        room.move(starter, Choose(0))
    room.move(starter, EndTurn())
    room.move(1 - starter, Pass())
    return starter


def test_using_an_order_and_cancelling_it_does_not_restart_the_clock(tmp_path: Path) -> None:
    """match.md §9: a cancelled activated ability leaves the match as it was, so it cannot buy
    the player a fresh turn timer."""
    with TestClient(create_app(_settings(tmp_path, turn_timeout_seconds=3600))) as client:
        room = _Room(client, ("starter-b", "starter-b"))
        starter = _order_waiting_on_a_cancellable_choice(room)
        clock = room.timer(starter)
        assert clock is not None
        for _ in range(3):
            order = next(i for i in room.legal(starter) if isinstance(i, UseOrder))
            room.move(starter, order)
            pending = room.state().pending
            assert pending is not None and pending.cancellable
            assert room.timer(starter).at == clock.at
            room.move(starter, CancelChoice())
            assert room.timer(starter).at == clock.at


def test_a_timeout_on_a_cancellable_choice_cancels_it_and_moves_on(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path, turn_timeout_seconds=3600))) as client:
        room = _Room(client, ("starter-b", "starter-b"))
        starter = _order_waiting_on_a_cancellable_choice(room)
        before = room.state().seq
        order = next(i for i in room.legal(starter) if isinstance(i, UseOrder))
        room.move(starter, order)
        room.time_out(starter, room.timer(starter))
        history = room.portal.call(room.service.history, room.match_id, before)
        types = [e["type"] for p in history for e in p["events"]]
        assert "choice_cancelled" in types
        assert types.index("player_passed") > types.index("choice_cancelled")


def test_both_players_mulligan_on_their_own_clock(tmp_path: Path) -> None:
    """Both players mulligan at once (match.md §6), so each has a timer from the start of the
    mulligan: the other player's redraws neither restart it nor cancel it, and ending one
    mulligan stops only that player's timer."""
    with TestClient(create_app(_settings(tmp_path, turn_timeout_seconds=3600))) as client:
        room = _Room(client)
        starter = room.state().starter
        other = 1 - starter
        clocks = {seat: room.timer(seat) for seat in (0, 1)}
        assert clocks[0] is not None and clocks[0] == clocks[1]

        redraw = next(i for i in room.legal(other) if isinstance(i, Mulligan))
        room.move(other, redraw)
        assert {seat: room.timer(seat) for seat in (0, 1)} == clocks

        room.time_out(starter, clocks[starter])
        players = room.state().players
        assert players[starter].mulligan is not None and players[starter].mulligan.done
        assert players[other].mulligan is not None and not players[other].mulligan.done
        assert room.timer(starter) is None and room.timer(other) == clocks[other]

        room.time_out(other, clocks[other])
        state = room.state()
        assert state.phase is Phase.PLAYING and state.turn == starter
        assert room.timer(starter) is not None and room.timer(other) is None


def _timer_service(monkeypatch: pytest.MonkeyPatch, timeout_move: Any) -> MatchService:
    """A ``MatchService`` for driving ``run_timers`` alone, with its move replaced."""
    service = MatchService(
        content=cast(Any, None),
        store=MemoryMatchStore(),
        bus=MemoryEventBus(),
        sessions=cast(Any, None),
        tasks=InlineTaskRunner(),
        settings=Settings(),
    )
    monkeypatch.setattr(service, "timeout_move", timeout_move)
    return service


def _due(seq: int) -> Any:
    return match_service._Deadline(0.0, ("seq", seq))


async def _until(condition: Callable[[], bool], within: float = 5.0) -> None:
    give_up = asyncio.get_running_loop().time() + within
    while not condition():
        assert asyncio.get_running_loop().time() < give_up, "timed out"
        await asyncio.sleep(0.001)


async def test_the_timer_loop_outlives_a_failing_match(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """One loop serves every match on the worker: a store conflict or a bot that never yields in
    one match is logged, and the others still time out."""
    failures = {"conflict": VersionConflict("stale"), "runaway": RuntimeError("no yield")}
    moved: list[str] = []

    async def timeout_move(match_id: str, seat: int, wait: Any) -> None:
        moved.append(match_id)
        if match_id in failures:
            raise failures[match_id]

    service = _timer_service(monkeypatch, timeout_move)
    for match_id in ("conflict", "runaway", "fine"):
        service._deadlines[(match_id, 0)] = _due(1)
    loop = asyncio.create_task(service.run_timers(0.001))
    try:
        await _until(lambda: "fine" in moved)
        service._deadlines[("later", 0)] = _due(1)
        await _until(lambda: "later" in moved)
        assert not loop.done()
    finally:
        loop.cancel()
    assert moved == ["conflict", "runaway", "fine", "later"]
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert errors == ["timer for conflict failed", "timer for runaway failed"]


async def test_a_timer_re_armed_while_the_loop_runs_is_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """While the loop moves for one match, a player's move on another re-arms that match's
    timer. The loop listed the old timer before; it must skip it and keep the new one."""
    moved: list[tuple[str, Any]] = []
    fresh = match_service._Deadline(asyncio.get_running_loop().time() + 3600, ("seq", 7))

    async def timeout_move(match_id: str, seat: int, wait: Any) -> None:
        moved.append((match_id, wait))
        if match_id == "first":
            service._deadlines[("second", 1)] = fresh

    service = _timer_service(monkeypatch, timeout_move)
    service._deadlines[("first", 0)] = _due(1)
    service._deadlines[("second", 1)] = _due(3)
    loop = asyncio.create_task(service.run_timers(0.001))
    try:
        await _until(lambda: bool(moved))
        await asyncio.sleep(0.02)
    finally:
        loop.cancel()
    assert moved == [("first", ("seq", 1))]
    assert service._deadlines == {("second", 1): fresh}


def test_settings_layers_and_deployment_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("port: 9000\nbot: random\n")
    monkeypatch.setenv("OPENGWT_CONFIG", str(config))
    monkeypatch.setenv("OPENGWT_PORT", "9100")
    settings = Settings()
    assert (
        settings.port == 9100 and settings.bot == "random"
    )  # env beats the file, file beats defaults
    with pytest.raises(ConfigError):
        Settings(workers=2).validate_deployment()
    Settings(
        workers=2, match_store_url="redis://x", event_bus_url="redis://x"
    ).validate_deployment()
    with pytest.raises(ConfigError):
        Settings(env="prod").validate_deployment()


@pytest.mark.skipif(
    not os.environ.get("OPENGWT_TEST_POSTGRES_URL"), reason="set OPENGWT_TEST_POSTGRES_URL to run"
)
async def test_migrations_run_on_postgres() -> None:
    from sqlalchemy import inspect

    from opengwt.server.db.models import Base
    from opengwt.server.db.session import make_engine, upgrade_to_head

    engine = make_engine(os.environ["OPENGWT_TEST_POSTGRES_URL"])
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
        await upgrade_to_head(engine)
        async with engine.connect() as connection:
            tables = await connection.run_sync(lambda c: inspect(c).get_table_names())
        assert {"players", "decks", "matches", "match_intents"} <= set(tables)
    finally:
        await engine.dispose()
