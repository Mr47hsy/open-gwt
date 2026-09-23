"""End-to-end tests over the HTTP and WebSocket API with the memory backends and SQLite."""

from __future__ import annotations

import json
import os
import secrets
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from opengwt.core.replay import record_from_dict, replay
from opengwt.core.serialize import state_hash
from opengwt.data import load_data
from opengwt.server.app import create_app
from opengwt.server.config import ConfigError, Settings

REPO = Path(__file__).resolve().parents[2]
PINNED_SEED = 1_234_567_890


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        data_dir=REPO / "data",
        auth_secret="test-secret-long-enough-for-hmac-sha256-keys",
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _guest(client: TestClient, name: str = "guest") -> tuple[dict[str, str], str]:
    response = client.post("/auth/guest", json={"display_name": name})
    assert response.status_code == 200, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['token']}"}, body["token"]


class Scripted:
    """A scripted client: plays the first legal card, otherwise passes; never sees more than
    its view, and asserts on every message that hidden information stayed hidden."""

    def __init__(self, ws: WebSocketTestSession, seat: int) -> None:
        self.ws = ws
        self.seat = seat
        self.seq = 0
        self.view: dict[str, Any] | None = None
        self.result: dict[str, Any] | None = None
        self.sent = 0
        self.events: list[dict[str, Any]] = []
        self.messages: list[dict[str, Any]] = []

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
                if event["type"] == "card_drawn" and event["seat"] != self.seat:
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
            return {"kind": "mulligan", "cards": [c["instance"] for c in view["me"]["hand"][:1]]}
        if view["phase"] == "choosing":
            return legal[0]
        plays = [i for i in legal if i["kind"] == "play_card"]
        return plays[0] if plays else {"kind": "pass"}

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
    assert hello["type"] == "hello" and hello["protocol"] == 1
    if not expect_view:
        return hello["seat"], hello
    view = ws.receive_json()
    assert view["type"] == "view"
    return hello["seat"], view


def test_health_pack_and_i18n(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    pack = client.get("/content/pack")
    assert pack.status_code == 200 and pack.json()["schema"] == "opengwt.pack/1"
    etag = pack.headers["etag"]
    assert client.get("/content/pack", headers={"If-None-Match": etag}).status_code == 304
    locales = client.get("/content/i18n").json()
    assert locales["locales"] == ["en", "ru", "zh-CN"] and locales["pack_hash"] == etag.strip('"')
    table = client.get("/content/i18n/zh-CN").json()
    assert table["card.a-u-0001.name"] == "占位 A 单位 1"
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


def test_decks_are_validated_by_the_rules(client: TestClient) -> None:
    headers, _ = _guest(client)
    assert client.get("/decks", headers=headers).json() == []
    bad = client.put(
        "/decks/mine",
        headers=headers,
        json={"name": "x", "faction": "placeholder-a", "cards": [{"id": "a-u-0001", "count": 3}]},
    )
    assert bad.status_code == 422
    assert "error.deck.too-few-units" in bad.json()["error"]["details"]["problems"]
    good = client.put(
        "/decks/mine",
        headers=headers,
        json={
            "name": "mine",
            "faction": "placeholder-a",
            "leader": "a-l-0001",
            "cards": [{"id": "a-u-0001", "count": 22}, {"id": "n-s-0009", "count": 1}],
        },
    )
    assert good.status_code == 200 and good.json()["deck_id"] == "mine"
    assert [d["deck_id"] for d in client.get("/decks", headers=headers).json()] == ["mine"]
    other, _ = _guest(client, "other")
    assert client.delete("/decks/mine", headers=other).status_code == 404
    assert client.delete("/decks/mine", headers=headers).status_code == 204


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
    monkeypatch.setattr(secrets, "randbits", lambda bits: PINNED_SEED)
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
        assert '"seed"' not in text and str(PINNED_SEED) not in text, message
    record = client.get(f"/matches/{match_id}/replay", headers=headers).json()["record"]
    assert record["seed"] == PINNED_SEED


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
