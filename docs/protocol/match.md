# Match protocol — v1

The wire contract between a client and the server: a small HTTP API for everything outside a
match, and one WebSocket per player per match. Companion to
[ADR 0001](../adr/0001-python-server-unity-thin-client.md): the client renders what it receives and
sends intents; every decision is made on the server.

Messages are JSON. Field names are `snake_case`. Ids are strings. Every message that can be
rendered to a human carries keys or codes, never sentences ([ADR 0006](../adr/0006-i18n-keys-and-unity-localization.md)).

## 1. Versioning

The server announces `protocol: 1` and the content pack hash in the WebSocket `hello` message. A
client built for another protocol version disconnects and tells the player to update. A client
whose cached pack hash differs re-fetches the pack before rendering.

Breaking changes bump the version. Adding an optional field or a new event type does not; clients
ignore unknown fields and unknown event types.

## 2. HTTP API

All routes except `/health` and `/auth/guest` require `Authorization: Bearer <token>`.

| Method and path | Body → Response | Notes |
| --- | --- | --- |
| `GET /health` | → `{status}` | Liveness. |
| `POST /auth/guest` | `{display_name?}` → `{token, player_id}` | MVP sign-in. Real accounts come later behind the same token. |
| `GET /content/pack` | → the content pack | `ETag` is the pack hash; supports `If-None-Match`. |
| `GET /decks` | → `[{deck_id, name, faction, cards}]` | The caller's decks. |
| `PUT /decks/{deck_id}` | `{name, faction, leader?, cards}` → the deck | Validated against the pack and the rules core's deck legality. |
| `DELETE /decks/{deck_id}` | → `204` | |
| `POST /matches` | `{mode: "bot" \| "room", deck_id}` → `{match_id, room_code?, ws_url}` | `bot` starts immediately against a server-hosted bot. `room` waits for a second player. |
| `POST /matches/join` | `{room_code, deck_id}` → `{match_id, ws_url}` | Second player of a room. |
| `GET /matches/{match_id}/replay` | → replay record (section 9) | Only after the match ended; only for its players in the MVP. |

Errors are `{error: {code, message_key, details?}}` with the appropriate HTTP status.

## 3. WebSocket session

`GET <ws_url>` with the bearer token in the `Authorization` header, or `?token=` where headers are
not available. One connection per player per match; a second connection for the same player
replaces the first.

On connect the server sends, in order:

1. `hello` — `{type: "hello", protocol: 1, pack_hash, match_id, player_id, seat}`;
2. `view` — the full current view for this player (section 7);
3. nothing more until something happens.

From then on the server pushes `events` batches, each followed by the `view` they lead to, and the
client sends `intent` messages when it is this player's turn or a choice is pending.

## 4. Server → client messages

| `type` | Fields | Meaning |
| --- | --- | --- |
| `hello` | see above | Once, on connect. |
| `view` | `{seq, view}` | Full per-player snapshot after all events up to `seq`. Always safe to render from scratch. |
| `events` | `{from_seq, events: [...]}` | Ordered events since the last batch; `from_seq` is the `seq` of the first. |
| `error` | `{code, message_key, intent_id?, details?}` | The intent named by `intent_id` was rejected; the view is unchanged. |
| `match_over` | `{seq, result}` | Final; `result` is `{winner: seat \| null, rounds: [...]}`. The socket closes shortly after. |

`seq` is a per-match counter over events. A client that renders `view` after every `events` batch
needs no other bookkeeping; a client that animates events may skip the `view` and only use it to
resynchronise.

## 5. Client → server messages

| `type` | Fields | Meaning |
| --- | --- | --- |
| `intent` | `{intent_id, intent}` | Ask to perform an intent (section 6). `intent_id` is a client-generated string echoed in errors. |
| `resync` | `{since_seq}` | Ask for all events after `since_seq` followed by a `view`. Used after reconnecting. |
| `ping` | `{}` | Keep-alive; the server answers `pong`. |

## 6. Intents

Exactly what the rules core accepts; the server only adds authentication and routing.

| `kind` | Fields | When legal |
| --- | --- | --- |
| `mulligan` | `{cards: [card_instance_id]}` | During the mulligan phase; may be empty to keep the hand. |
| `play_card` | `{card: card_instance_id, row?: "melee" \| "ranged" \| "siege"}` | On this player's turn. `row` is required when the card allows more than one row. |
| `use_leader` | `{}` | On this player's turn, once per match. |
| `pass` | `{}` | On this player's turn. |
| `choose` | `{option: index}` | Only while a choice is pending for this player. Every other intent is illegal until the choice is made. |

The view carries `legal_intents`: the exact set the server would accept now, in the same shape.
The client enables controls from that list and never derives legality itself.

## 7. View

The per-player projection produced by the rules core. Hidden information is removed *before*
serialisation; it does not exist in the message.

```json
{
  "match_id": "…", "seq": 42, "protocol": 1,
  "phase": "mulligan" | "playing" | "choosing" | "round_over" | "match_over",
  "round": 1, "turn": "me" | "opponent" | null,
  "me": {
    "seat": 0, "score": 17, "rounds_won": 0, "passed": false,
    "hand": [ { "instance": "c17", "card": "u-0001" } ],
    "deck_count": 12, "discard": [ { "instance": "c03", "card": "s-0002" } ],
    "leader": { "card": "l-0001", "used": false },
    "rows": {
      "melee":  { "effect": null,           "units": [ { "instance": "c09", "card": "u-0001", "power": 5, "base": 5 } ] },
      "ranged": { "effect": "power_to_one", "units": [] },
      "siege":  { "effect": null,           "units": [] }
    }
  },
  "opponent": { "seat": 1, "score": 12, "rounds_won": 0, "passed": false,
                "hand_count": 8, "deck_count": 13, "discard": [], "leader": {…}, "rows": {…} },
  "legal_intents": [ { "kind": "pass" }, { "kind": "play_card", "card": "c17", "row": "melee" } ],
  "pending_choice": { "prompt_key": "choice.return_from_discard", "options": [ { "instance": "c03", "card": "s-0002" } ] } | null
}
```

`power` is effective power; `base` is current power before row effects and passives. `opponent`
never contains a `hand` array or any deck order; only counts.

## 8. Events

Each event is `{seq, type, ...}`. Events are what the client animates. The set is open-ended by
adding types; the fields of an existing type are only ever extended.

| `type` | Fields | Notes |
| --- | --- | --- |
| `turn_started` | `{seat}` | |
| `card_drawn` | `{seat, instance?, card?}` | `instance` and `card` only for the receiving player's own draws. |
| `mulligan_done` | `{seat, count}` | |
| `card_played` | `{seat, instance, card, row?, side}` | `side` is where the unit landed (`self` or `opponent` relative to `seat`). |
| `leader_used` | `{seat, card}` | |
| `unit_summoned` | `{seat, instance, card, row}` | From deck or discard. |
| `unit_returned` | `{seat, instance, card, to: "hand"}` | |
| `unit_destroyed` | `{seat, instance, card, row}` | |
| `power_changed` | `{seat, instance, from, to, reason}` | Effective power; `reason` names the action or row effect. |
| `row_effect_applied` | `{seat, row, effect}` | |
| `row_effect_cleared` | `{seat, row}` | |
| `choice_requested` | `{seat, prompt_key, option_count}` | The options themselves are only in that player's view. |
| `choice_made` | `{seat, option}` | |
| `player_passed` | `{seat}` | |
| `round_ended` | `{round, winner: seat \| null, scores: [a, b]}` | `null` is a draw. |
| `match_ended` | `{winner: seat \| null, rounds}` | |

## 9. Replay record and reconnect

The server stores, per match: `seed`, both decks (as played, with instance ids), and the ordered
list of **accepted** intents with the seat and `seq` they were applied at. Replaying that record
through the rules core reproduces every event and view. The replay endpoint returns exactly that
record plus the result; a replay viewer streams it through the same `events`/`view` messages.

Reconnect: the client opens a new socket, receives `hello` and a full `view`, then optionally
sends `resync {since_seq}` to receive the events it missed for animation. If the client cannot
animate a gap it simply renders the `view`.

A player who stays disconnected keeps their turn until the match's turn timeout, a server setting,
after which the server passes for them.

## 10. Errors

| `code` | Meaning |
| --- | --- |
| `illegal_intent` | Not in `legal_intents`; `details.reason` is a key. |
| `not_your_turn` | |
| `choice_pending` | A `choose` intent is required first. |
| `unknown_instance` | The card instance id does not exist in this player's visible zones. |
| `match_over` | |
| `protocol_version` | Client and server protocol versions differ. |
| `unauthorised` | Token invalid, or not a player of this match. |

## 11. Security notes

- The opponent's hand, either deck's order and upcoming draws exist only in the rules core state
  held by the server. Views are produced by the core's `view(state, player)`; nothing else
  serialises state for a client.
- A `choice_requested` event for the other player reveals the *number* of options, not the options.
- Tokens identify a player, not a match; the server checks the player is seated in the match on
  every socket message.
- The server rate-limits intents per socket; a burst is closed, not queued.
