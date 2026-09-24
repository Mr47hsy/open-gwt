# Match protocol — v2

The wire contract between a client and the server: a small HTTP API for everything outside a
match, and one WebSocket per player per match. Companion to
[ADR 0001](../adr/0001-python-server-unity-thin-client.md): the client renders what it receives and
sends intents; every decision is made on the server. Version 2 carries the two-row ruleset of
[ADR 0009](../adr/0009-two-row-standalone-ruleset.md), whose rules are defined in
[`cards.md`](cards.md).

> **Transition.** Since ADR 0009 phase B the server speaks protocol 2: views, intents and events
> come from the v2 rules core; phase C completed it — activated abilities of every kind,
> `end_turn`, and choices of every kind — while no client spoke it yet, so protocol 2 changed in
> place; phase D changed it in place again — the deck-building problems of `deck_illegal` became
> objects, and decks carry their provisions and problems (sections 2 and 10). The Unity client on
> `develop` still speaks protocol 1 (`git show b68be93:docs/protocol/match.md`) until phase E;
> between the two it cannot play, by the owner's decision.

Messages are JSON. Field names are `snake_case`. Ids are strings. Every message that can be
rendered to a human carries keys or codes, never sentences ([ADR 0006](../adr/0006-i18n-keys-and-unity-localization.md)).

## 1. Versioning

The server announces `protocol: 2` and the content pack hash in the WebSocket `hello` message. A
client built for another protocol version disconnects and tells the player to update. A client
whose cached pack hash differs re-fetches the pack before rendering.

Breaking changes bump the version. Adding an optional field or a new event type does not; clients
ignore unknown fields and unknown event types.

What changed from protocol 1: two rows, positions on a row and artifacts; the `use_order`,
`end_turn`, `cancel_choice` and `end_mulligan` intents, one-card `mulligan`, and `use_leader`
folded into `use_order`; a turn that goes on after its card until the player ends it; a
generalised `pending_choice`; power, armour, statuses and readiness in the view; tied rounds
with several winners; the events of section 8.

## 2. HTTP API

All routes except `/health` and `/auth/guest` require `Authorization: Bearer <token>`.

| Method and path | Body → Response | Notes |
| --- | --- | --- |
| `GET /health` | → `{status}` | Liveness. |
| `POST /auth/guest` | `{display_name?}` → `{token, player_id}` | MVP sign-in. Real accounts come later behind the same token. |
| `GET /content/pack` | → the content pack | `ETag` is the pack hash; supports `If-None-Match`. The pack carries the `Rules` in force (`cards.md` §14). |
| `GET /content/i18n` | → `{locales, pack_hash}` | Supported locales. |
| `GET /content/i18n/{locale}` | → flat map key → message | All domains merged; `ETag` is the pack hash. See `i18n.md`. |
| `PATCH /me` | `{display_name?, locale?}` → profile | `locale` drives server-rendered fallback text. |
| `GET /decks` | → `[{deck_id, name, faction, leader, stratagem, cards, provisions, problems}]` | The caller's decks, judged by the `Rules` the server plays with (the pack's): `provisions` is `{used, budget}` (`cards.md` §12) and `problems` the deck-building rules the deck breaks, as in section 10 — empty for a deck saved now, but a deck saved earlier breaks rules that have tightened or content that changed since (a deck from before ADR 0011, with no stratagem, reports it as an unknown card with an empty id). |
| `PUT /decks/{deck_id}` | `{name, faction, leader, stratagem, cards}` → the deck, as `GET /decks` lists it | Creates or replaces the caller's deck of that id. Validated against the pack and the rules core's deck legality (`cards.md` §12); an illegal deck is refused with `deck_illegal` and is not saved. `leader` and `stratagem` are required. |
| `DELETE /decks/{deck_id}` | → `204` | The caller's deck of that id; `deck_not_found` if they have none. |
| `POST /matches` | `{mode: "bot" \| "room", deck_id}` → `{match_id, room_code?, ws_url}` | `bot` starts immediately against a server-hosted bot. `room` waits for a second player. `deck_id` is a saved deck of the caller or a starter deck of the pack; a saved deck the rules refuse is refused with `deck_illegal`. |
| `POST /matches/join` | `{room_code, deck_id}` → `{match_id, ws_url}` | Second player of a room. Both decks are judged by the rules the room was made with, which its match is played with; if either breaks one, the join is refused with `deck_illegal` and `details.seat`, and the room keeps waiting. The joiner's own deck (seat 1) comes with its `problems`; the room's (seat 0) does not, since they would show the joiner the other player's cards. |
| `GET /matches/{match_id}` | → `{match_id, mode, status, seat, room_code, result}` | `status` is `waiting`, `playing` or `finished`; `seat` is the caller's seat or null. |
| `GET /matches/{match_id}/replay` | → replay record (section 9) | Only after the match ended; only for its players in the MVP. |

A `deck_id` is the caller's own name for a deck: two players may each keep a deck `mine`, and no
route reads, replaces or deletes another player's deck.

Errors are `{error: {code, message_key, params, message, details?}}` with the appropriate HTTP
status. `message` is `message_key` rendered on the server with `params` in the negotiated locale
(player profile, then `Accept-Language`, then `en`; see [`i18n.md`](i18n.md)). A client that knows
the key renders it itself and uses `message` only as a fallback.

## 3. WebSocket session

`GET <ws_url>` with the bearer token in the `Authorization` header, or `?token=` where headers are
not available. One connection per player per match; a second connection for the same player
replaces the first.

Close codes the server uses: `4000` this connection was replaced by a newer one of the same
player; `4401` the token is missing or invalid; `4403` the match does not exist or the caller is
not seated in it; `4429` more than twenty intents arrived within one second. A normal close after
`match_over` uses `1000`.

On connect the server sends, in order:

1. `hello` — `{type: "hello", protocol: 2, pack_hash, match_id, player_id, seat, locale}`;
2. `view` — the full current view for this player (section 7);
3. nothing more until something happens.

From then on the server pushes `events` batches, each followed by the `view` they lead to, and the
client sends `intent` messages when it is this player's turn, during the mulligan, or while a
choice of theirs is pending.

## 4. Server → client messages

| `type` | Fields | Meaning |
| --- | --- | --- |
| `hello` | see above | Once, on connect. |
| `view` | `{seq, view}` | Full per-player snapshot after all events up to `seq`. Always safe to render from scratch. |
| `events` | `{from_seq, events: [...]}` | Ordered events since the last batch; `from_seq` is the `seq` of the first. |
| `error` | `{code, message_key, params, message, intent_id?, details?}` | The intent named by `intent_id` was rejected; the view is unchanged. `message` as in section 2. |
| `match_over` | `{seq, result}` | Final; `result` is `{winner: seat \| null, rounds: [{round, winners, scores}]}`. The socket closes shortly after. |

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
| `mulligan` | `{card: instance}` | During the mulligan, while this player has redraws left, cards in their deck and has not ended their mulligan: return this card from hand and draw a replacement into its place (`cards.md` §11.5). |
| `end_mulligan` | `{}` | During the mulligan, until this player's mulligan is over. It ends by itself when the redraws run out. |
| `play_card` | `{card: instance, row?, position?}` | On this player's turn, with no choice pending, once per turn. `row` (`melee` or `ranged`) and `position` are required for a unit or an artifact and absent for a special. `position` is the index the card is inserted at, from `0` (left end) to the number of cards on that row-side (right end). Playing a card does not end the turn (`end_turn`). |
| `use_order` | `{instance}` | On this player's turn, with no choice pending, before or after the turn's card, for a card of theirs on the board or their leader whose activated ability is ready (`cards.md` §6.3). Does not end the turn; once one is used, the turn needs its card. |
| `end_turn` | `{}` | On this player's turn, with no choice pending, once the turn's card is played. The turn never ends by itself (`cards.md` §11.4). |
| `pass` | `{}` | On this player's turn, with no choice pending, instead of playing a card: not once the card is played, and not after an activated ability while a card can still be played. |
| `choose` | `{option: index}` | Only while a choice is pending for this player. Every other intent except `cancel_choice` is illegal until the choice is made. |
| `cancel_choice` | `{}` | Only while a choice of this player is pending and `cancellable`. |

Both players mulligan at the same time; the server applies their intents in the order it
accepts them, and that order is what the replay record keeps.

The view carries `legal_intents`: the exact set the server would accept now, in the same shape,
with two compressions to keep it short. A `play_card` entry lists a legal `card` and `row` without
`position`: every position from `0` to the number of cards on that row-side is legal. And every
card in hand has one `mulligan` entry while redraws are left. The client enables controls from
that list and never derives legality itself.

## 7. View

The per-player projection produced by the rules core. Hidden information is removed *before*
serialisation; it does not exist in the message.

```json
{
  "protocol": 2, "match_id": "…", "seq": 42,
  "phase": "playing",
  "round": 2, "turn": "me", "winner": null,
  "me": {
    "seat": 0, "faction": "placeholder-a",
    "score": 17, "rounds_won": 1, "passed": false,
    "hand": [ { "instance": "c17", "card": "u-0002" } ],
    "hand_count": 1, "deck_count": 12,
    "graveyard": [ { "instance": "c03", "card": "s-0001" } ],
    "banished": [],
    "leader": { "instance": "c29", "card": "l-0001",
                "order": { "ready": true, "charges": 1, "cooldown": 0 } },
    "mulligan": null,
    "rows": {
      "melee": {
        "effect": null,
        "cards": [
          { "instance": "c09", "card": "u-0003", "owner": 0,
            "power": 6, "base": 4, "aura": 1, "armor": 2,
            "statuses": [ { "status": "bleeding", "turns": 2 }, { "status": "shielded" } ],
            "order": null },
          { "instance": "c11", "card": "a-0001", "owner": 0,
            "statuses": [],
            "order": { "ready": false, "charges": 2, "cooldown": 1 } }
        ]
      },
      "ranged": { "effect": { "effect": "damage_weakest", "amount": 2 }, "cards": [] }
    }
  },
  "opponent": { "seat": 1, "faction": "placeholder-b", "score": 12, "rounds_won": 1,
                "passed": false, "hand_count": 8, "deck_count": 13, "graveyard": [],
                "banished": [], "leader": {…}, "mulligan": null, "rows": {…} },
  "legal_intents": [ { "kind": "pass" },
                     { "kind": "play_card", "card": "c17", "row": "melee" },
                     { "kind": "use_order", "instance": "c29" } ],
  "pending_choice": null
}
```

Instance ids are opaque strings ([ADR 0010](../adr/0010-unpredictable-random-stream.md)); `c17`
and the like are shortened for the examples, and a client never parses them.

| Field | Meaning |
| --- | --- |
| `phase` | `mulligan`, `playing`, `choosing` (a choice is pending) or `match_over`. |
| `turn` | `me`, `opponent`, or `null` during the mulligan and after the match. |
| `winner` | After the match: `me`, `opponent` or `draw`; otherwise `null`. |
| `hand` | Own hand only. `opponent` never has a `hand` array or any deck order — only counts. |
| `graveyard`, `banished` | Public zones, oldest first. |
| `leader` | The leader's instance and card, and its `order` (below); `null` for a deck without one. |
| `mulligan` | During the mulligan `{remaining, done}` — redraws left and whether that player has finished; otherwise `null`. |
| `rows` | One entry per row in `Rules.rows`: the row-side's `effect` (`{effect, amount, count?}` or `null`) and its `cards`, left to right; a card's position is its index. The starter's stratagem is one of these cards until it is used or round one ends, with its `order`. |

A card on the board:

| Field | Meaning |
| --- | --- |
| `instance`, `card`, `owner` | Instance id, card id, and the seat of the owner (the controller is the side it is listed under). |
| `power`, `base`, `aura`, `armor` | Units only: `power` is the current power plus `aura` (`cards.md` §11.1); the unit is boosted when `power − aura` is above `base` and damaged when it is below. Armour apart. |
| `statuses` | In order of arrival: `{status}` or `{status, turns}` for a timed one. |
| `order` | `null` for a card without an activated ability; otherwise `{ready, charges, cooldown}`, where `charges` is `null` when unlimited and `ready` follows `cards.md` §6.3 — so it is only ever `true` for this player's cards on their turn. |

`pending_choice` is `null` unless a choice of **this** player is pending:

```json
{
  "kind": "unit",
  "prompt_key": "choice.damage",
  "source": { "instance": "c21", "card": "u-0002" },
  "cancellable": false,
  "options": [
    { "side": "opponent", "row": "melee", "position": 0, "instance": "c40", "card": "u-0101" },
    { "side": "opponent", "row": "ranged", "position": 2, "instance": "c44", "card": "u-0010" }
  ]
}
```

| `kind` | Asks for | Option shape |
| --- | --- | --- |
| `unit` | a card on the board (`units: chosen`) | `{side, row, position, instance, card}` |
| `row` | a row-side (`units: chosen_row`, `row_target.pick: chosen`) | `{side, row}` |
| `place` | where to put a card played by an ability | `{side, row, position}` |
| `card` | a card from a deck or graveyard (`cards.pick: chosen`) | `{instance, card}` |

`side` is `me` or `opponent`. `source` is the card whose ability asks. `prompt_key` is
`choice.<action>` with the action's underscores as hyphens (`choice.play-from-deck`), or
`choice.place` for a placement; a placement also carries `card: {instance, card}`, the card being
placed. A card `create` offers has no instance yet: its option is `{card}`. `cancellable` is
`true` only for the first choice of a `use_order`, before anything has changed, and only when
the options show nothing hidden and took no random draw — a unit, a row-side, or a card from a
graveyard without an offer (`cards.md` §6.3). Options from a deck or a hand are listed by card
id, then instance id; a graveyard keeps its order. The answer is `choose {option}`, the option's
index.

## 8. Events

Each event is `{seq, type, ...}`. Events are what the client animates. The set is open-ended by
adding types; the fields of an existing type are only ever extended.

`seat` is the player an event concerns: the acting player for intents, choices and passes and
for a card played or summoned, the controller — the side it stands on — for any other event about
a card on the board. `side` is `self` or `opponent` relative to `seat`: where a played or summoned
card landed. `reason` names what caused a change: an action (`damage`), a status
(`bleeding`, `growing`), a row effect (`damage_weakest`), or `aura`. `source` is the instance
whose ability caused it, or `null` for a status or a row effect.

| `type` | Fields | Notes |
| --- | --- | --- |
| `match_started` | `{starter}` | Never carries the seed (section 11). |
| `stratagem_placed` | `{seat, instance, card, row, position}` | The starter's stratagem starts on their board (ADR 0011). |
| `round_started` | `{round, starter}` | |
| `card_drawn` | `{seat, instance?, card?}` | `instance` and `card` only for the receiving player's own draws. |
| `draw_skipped` | `{seat, reason, count}` | `reason` is `hand_full` or `deck_empty`; `count` draws of one draw action did not happen. |
| `mulligan_started` | `{round, redraws: [n0, n1]}` | Both players at once; the redraws include those for draws a full hand prevented. |
| `card_redrawn` | `{seat, instance?, card?}` | A card went back into the deck; its replacement follows as `card_drawn`. Identity for the owner only. |
| `mulligan_done` | `{seat, count}` | |
| `turn_started` | `{seat}` | |
| `turn_ended` | `{seat}` | |
| `card_played` | `{seat, instance, card, from, row?, position?, side?}` | `from` is `hand`, `deck`, `graveyard` or `created`; `row`, `position`, `side` for a unit or artifact. |
| `order_used` | `{seat, instance, card, charges, cooldown}` | When the order's first ability starts to act (after its choice, if it asks one): remaining charges (`null` when unlimited) and the new cooldown. Replaces protocol 1's `leader_used`. |
| `card_summoned` | `{seat, instance, card, from, row, position, side}` | Onto the board without being played; `from` is `deck` or `created`. |
| `card_moved` | `{seat, instance, card, from_row, to_row, position}` | |
| `card_returned` | `{seat, instance, card}` | From the board to its owner's hand. |
| `control_changed` | `{seat, instance, card, from_seat, row, position, source}` | By `take_control`; `seat` is the new controller. |
| `card_discarded` | `{seat, instance, card}` | From `seat`'s hand to the owner's graveyard. |
| `card_destroyed` | `{seat, instance, card, row, banished, source}` | `banished` is `true` when `banish_on_leave` sent it away instead of to the graveyard; `source` is `null` for the destruction check (`cards.md` §11.2). |
| `card_banished` | `{seat, instance, card}` | Removed from the board by `banish`, or by `banish_on_leave` when it was returned or cleared at round end. |
| `unit_damaged` | `{seat, instance, card, amount, power, reason, source}` | `amount` reached power past armour; `power` is the new value. |
| `damage_blocked` | `{seat, instance, card, amount, reason, source}` | A shield blocked it; `status_removed` follows. |
| `unit_boosted` | `{seat, instance, card, amount, power, reason, source}` | |
| `unit_healed` | `{seat, instance, card, amount, power, source}` | By `heal`; `amount` of damage undone. |
| `base_power_changed` | `{seat, instance, card, from, to, power, source}` | |
| `armor_changed` | `{seat, instance, card, from, to, reason, source}` | Gained, or used up absorbing damage. |
| `power_changed` | `{seat, instance, card, from, to, reason, source}` | Any other change of power: `reset_power`, or `aura` right after the change that started or ended an aura — a card entering, leaving, moving, locked or unlocked (`source` `null`). |
| `status_added` | `{seat, instance, card, status, turns?, reason, source}` | `turns` is the timer after the addition. |
| `status_reduced` | `{seat, instance, card, status, turns, reason, source}` | A timer shortened: `bleeding` and `growing` cancelling each other. |
| `status_removed` | `{seat, instance, card, status, reason, source}` | `reason` is an action, `expired`, `blocked` (a shield used up), `cancelled` (`bleeding` against `growing`) or `kept` (`kept_at_round_end` used). |
| `charges_changed` | `{seat, instance, card, from, to, source}` | By `add_charges`. |
| `row_effect_set` | `{seat, row, effect, amount, count?, source}` | Replaces any previous one; no `row_effect_cleared` precedes it. |
| `row_effect_cleared` | `{seat, row, effect, source}` | By `clear_row_effect`. The end of a round removes row effects without this event (`board_cleared`). |
| `choice_requested` | `{seat, kind, prompt_key, option_count, source, cancellable}` | The options themselves are only in that player's view. |
| `choice_made` | `{seat, option?}` | `option` for the chooser only: the other player never saw the options, and the index of one among cards from a hidden zone would tell something of them. |
| `choice_cancelled` | `{seat}` | The match is back where it was before the `use_order`. |
| `player_passed` | `{seat, auto}` | `auto` is `true` for an automatic pass (`cards.md` §11.4). |
| `round_ended` | `{round, winners: [seat...], scores: [a, b]}` | Two winners for a tie under `both_win`, none under `neither_wins`. |
| `board_cleared` | `{round, kept: [instance...]}` | Every other card left the board; row effects are gone. |
| `match_ended` | `{winner: seat \| null, rounds: [{round, winners, scores}]}` | `null` is a draw. |

## 9. Replay record and reconnect

The server stores, per match, a record of schema `opengwt.record/2`: the `seed` — 256 bits as 64
lowercase hex characters (ADR 0010) — the `Rules` values the match was played with, both decks,
and the ordered list of **accepted** intents with the seat that sent each. Replaying that record
through the rules core reproduces every event and view. The replay endpoint returns exactly that
record plus the result; a replay viewer streams it through the same `events`/`view` messages. A
match finished before ADR 0009 phase B is returned as the `opengwt.record/1` data it was stored
with — an integer seed and v1 rules and decks — which the current core does not replay.

Reconnect: the client opens a new socket, receives `hello` and a full `view`, then optionally
sends `resync {since_seq}` to receive the events it missed for animation. If the client cannot
animate a gap it simply renders the `view`.

A player who stays disconnected keeps their turn until the match's turn timeout, a server setting,
after which the server moves for them: during the mulligan it ends their mulligan; while a choice
is pending it cancels it if it can or picks the first option; once the turn's card is played it
ends the turn; otherwise it passes — or, after an activated ability, when a pass is refused, plays
the first legal card at the right end of its row. A timeout that cancels a choice makes that next
move too, in the same timeout. In the mulligan each player has
their own timeout, from the start of the mulligan: neither player's redraws restart it. Otherwise
the timeout restarts with every change to the match — except a `use_order` that stops on a
cancellable choice and the `cancel_choice` of it, which leave the match as it was: the player's
timer runs on through them.

`resync` is answered from the match's event log. In a multi-worker deployment that log is shared
(ADR 0008), so a reconnecting client may land on any worker and still receive the same events.

## 10. Errors

| `code` | Meaning |
| --- | --- |
| `illegal_intent` | Not in `legal_intents`; `details.reason` is a key (below). |
| `not_your_turn` | |
| `choice_pending` | A `choose` (or `cancel_choice`) intent is required first. |
| `unknown_instance` | The card instance id does not exist in this player's visible zones. |
| `match_over` | |
| `match_not_started` | The room still waits for its second player. |
| `protocol_version` | Client and server protocol versions differ. |
| `unauthorised` | Token invalid, or not a player of this match. |
| `not_a_player` | The caller is not seated in the match (replay, status). |
| `deck_not_found`, `deck_illegal` | Deck lookup and validation; `details.problems` lists the deck-building rules the caller's deck breaks (below); when joining a room, `details.seat` says whose deck it is, and only seat 1's — the caller's — comes with `problems`. |
| `room_not_found`, `room_full`, `own_room` | Joining a room. |
| `locale_unsupported`, `invalid_request`, `unknown_message` | Request shape and content. |

Each deck problem is `{key, card?, params}`, one per rule and card, in the order of `cards.md`
§12. `key` is the rule's key and its message's (`error.deck.<rule>`); `card` is the id of the
card it is about, for the rules that concern one card; `params` is what the message is rendered
with. Its `card` refers to the card's name (`@card.<id>.name`); for a card the pack does not
have, it is the id itself, with one more `@` in front when the id starts with `@` (`i18n.md`
§4). Its numbers are the rule's: `count` and `min` (`too-few-cards`, `too-few-units`), `count`
and `max` (`too-many-cards`), `count` and `limit` (`too-many-copies`), `used` and `budget`
(`over-budget`); `count` selects the message's plural form (`i18n.md` §5).

```json
{ "code": "deck_illegal", "message_key": "error.deck-illegal", "params": {},
  "message": "This deck is not legal.",
  "details": { "problems": [
    { "key": "error.deck.too-many-copies", "card": "u-1003",
      "params": { "card": "@card.u-1003.name", "count": 3, "limit": 2 } },
    { "key": "error.deck.over-budget", "params": { "used": 167, "budget": 165 } } ] } }
```

Reason keys of `illegal_intent` new in protocol 2: `error.play.row-full`,
`error.play.position-out-of-range`, `error.play.position-required`,
`error.play.card-already-played`, `error.pass.card-played`, `error.pass.order-used`,
`error.end-turn.no-card-played`, `error.order.not-ready`, `error.choice.not-cancellable`,
`error.mulligan.none-left`, `error.mulligan.over`. Protocol 1's keys for playing, passing and
choosing keep their meaning.

## 11. Security notes

- The opponent's hand, either deck's order and upcoming draws exist only in the rules core state
  held by the server. Views are produced by the core's `view(state, player)`; nothing else
  serialises state for a client.
- The seed and the random stream's state never reach a client while the match runs — not in an
  event, a view, an error detail or a log: with them and the open-source shuffle, a client could
  rebuild both decks' order. The seed is only in the replay record, served after the match ended.
  It is 256 bits wide and the stream is SHA-256 in counter mode (ADR 0010), so it cannot be
  searched for from what a player is shown either.
- Options drawn from a hidden zone are listed by card id and instance id, never in zone order;
  instance ids are opaque (`cards.md` §5), so neither reveals a position.
- A `choice_requested` event for the other player reveals the kind, the number of options and
  the source card — which is public — never the options; its `choice_made` carries no option.
- A card that chooses from the opponent's deck or hand shows its candidates to the chooser, by
  design of that card (`cards.md` §7.3).
- Random picks — `random` targets, offers, tie breaks, mulligan insertion — are drawn on the
  server with the seeded PRNG; a client never supplies randomness. A server-hosted bot draws from
  its own stream (ADR 0010), so its choices say nothing about the match's.
- Tokens identify a player, not a match; the server checks the player is seated in the match on
  every socket message.
- The server rate-limits intents per socket; a burst is closed, not queued.
