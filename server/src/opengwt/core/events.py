"""Domain events: what happened, in order. The client animates them; the server broadcasts them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Event:
    seq: int
    type: str
    data: dict[str, Any]


def event_to_dict(event: Event) -> dict[str, Any]:
    return {"seq": event.seq, "type": event.type, **event.data}


def event_from_dict(d: dict[str, Any]) -> Event:
    data = {k: v for k, v in d.items() if k not in ("seq", "type")}
    return Event(int(d["seq"]), str(d["type"]), data)


def event_for_seat(event: Event, seat: int) -> Event:
    """The event as ``seat`` may see it: another player's draws lose their card identity."""
    if event.type == "card_drawn" and event.data.get("seat") != seat:
        data = {k: v for k, v in event.data.items() if k not in ("instance", "card")}
        return Event(event.seq, event.type, data)
    return event
