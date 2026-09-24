"""Generated card text — docs/protocol/i18n.md §10.

A card without an explicit ``card.<id>.text`` in a locale gets one built from its definition:
its row restriction, armour and innate statuses, then its abilities grouped by trigger, each
ability one sentence rendered from an ``ability.<action>…`` template of that locale. The
templates are ordinary ``opengwt.i18n/1`` messages in ``data/i18n/<locale>/abilities.yaml``;
the phrases a sentence is made of — who it targets, which rows, which cards of which zone — are
rendered first, from their own keys, and inserted as parameters. Nothing here is language
specific: word order, articles, cases and plural forms all live in the tables.

One grammatical twin is optional. An action names its target either as its direct *object*
(``Boost {target} by 2``) or as its *recipient* (``Deal 2 damage to {target}``). The target
phrases are ``ability.target.…``; a locale whose grammar marks the recipient differently —
Russian puts it in the dative — also defines ``ability.target-to.…`` twins, which recipient
templates use. A locale without them uses the plain phrases.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace

from opengwt.core.model import (
    DEFAULT_RULES,
    NO_CONDITIONS,
    NO_FILTER,
    Ability,
    Action,
    CardDef,
    CardSource,
    ChargeTarget,
    Conditions,
    Kind,
    Library,
    Row,
    RowEffectKind,
    RowPick,
    RowTarget,
    Rules,
    Side,
    Status,
    Trigger,
    Units,
    Where,
)
from opengwt.i18n import BASE_LOCALE, Param, Renderer

PREFIX = "ability."
TARGET = "target."
TARGET_TO = "target-to."

# Actions whose target is the recipient of what they give or deal, not their direct object.
RECIPIENT_ACTIONS = frozenset(
    {Action.DAMAGE, Action.ADD_ARMOR, Action.RAISE_BASE_POWER, Action.DRAIN}
)
RECIPIENT_STATUSES = frozenset({Status.SHIELDED, Status.IMMUNE})
# Unit selectors that name exactly one unit; any other names several, or none.
SINGLE_UNITS = frozenset(
    {Units.CHOSEN, Units.STRONGEST, Units.WEAKEST, Units.THIS, Units.TRIGGER_UNIT}
)
SIDED_UNITS = frozenset(
    {Units.CHOSEN, Units.CHOSEN_ROW, Units.ALL, Units.RANDOM, Units.STRONGEST, Units.WEAKEST}
)
COUNTED_ROW_EFFECTS = frozenset({RowEffectKind.DAMAGE_RANDOM, RowEffectKind.BOOST_RANDOM})
DEFAULT_OFFER = 3


def _word(value: str) -> str:
    """A vocabulary id as it appears inside a key: underscores written as hyphens (§2)."""
    return value.replace("_", "-")


class _Ref(str):
    """A parameter that is a reference to another key (``@card.<id>.name``), passed as is."""


def _param(value: Param) -> Param:
    """A rendered phrase passed on as a parameter, protected from being read as a reference."""
    if isinstance(value, str) and not isinstance(value, _Ref) and value.startswith("@"):
        return "@" + value
    return value


@dataclass
class _Text:
    """Renders ``ability.…`` keys of one locale and remembers the ones missing everywhere."""

    renderer: Renderer
    tables: Mapping[str, Mapping[str, str]]
    locale: str
    missing: list[str] = field(default_factory=list)

    def __call__(self, key: str, **params: Param) -> str:
        full = PREFIX + key
        count = params.get("count")
        found = self.renderer.lookup(self.locale, full, count if isinstance(count, int) else None)
        if found is None and full not in self.missing:
            self.missing.append(full)
        return self.renderer.render(
            self.locale, full, {name: _param(value) for name, value in params.items()}
        )

    def own(self, key: str) -> bool:
        """Whether this locale itself — not its fallback — defines ``key`` or a variant of it."""
        full = PREFIX + key
        return any(_plural_base(k) == full for k in self.tables.get(self.locale, {}))

    def join(self, items: Sequence[str], last: str = "join.list") -> str:
        """``a, b, c`` with ``last`` between the final two (``join.or``, ``join.and``)."""
        if not items:
            return ""
        head = items[0]
        for item in items[1:-1]:
            head = self("join.list", a=head, b=item)
        if len(items) > 1:
            head = self(last, a=head, b=items[-1])
        return head

    def sentences(self, items: Sequence[str]) -> str:
        out = ""
        for item in items:
            out = item if not out else self("join.sentences", a=out, b=item)
        return out


# --- filters -------------------------------------------------------------------------------------


def _single_row(rows: Sequence[Row] | None, rules: Rules) -> Row | None:
    """The one row a restriction leaves, or None when it leaves every row of ``rules``."""
    if not rows:
        return None
    allowed = [r for r in rules.rows if r in rows]
    return allowed[0] if len(allowed) == 1 and len(rules.rows) > 1 else None


def _qualifiers(
    t: _Text,
    where: Where,
    rules: Rules,
    rows: Sequence[Row] | None = None,
    default_kind: tuple[Kind, ...] | None = None,
) -> list[str]:
    items: list[str] = []
    row = _single_row(rows, rules)
    if row is not None:
        items.append(t(f"where.row.{row.value}"))
    if where.kind is not None and set(where.kind) != set(default_kind or ()):
        items.append(t.join([t(f"where.kind.{k.value}") for k in where.kind], "join.or"))
    if where.color is not None:
        items.append(t(f"where.color.{where.color.value}"))
    if where.tags_any:
        items.append(t("where.tags-any", tags=_tags(t, where.tags_any)))
    if where.tags_none:
        items.append(t("where.tags-none", tags=_tags(t, where.tags_none)))
    if where.statuses_any:
        items.append(t("where.statuses-any", statuses=_states(t, where.statuses_any)))
    if where.statuses_none:
        items.append(t("where.statuses-none", statuses=_states(t, where.statuses_none)))
    if where.same_id_as_this:
        items.append(t("where.same-id"))
    if where.power_at_least is not None:
        items.append(t("where.power-at-least", count=where.power_at_least))
    if where.power_at_most is not None:
        items.append(t("where.power-at-most", count=where.power_at_most))
    if where.stronger_than_this:
        items.append(t("where.stronger-than-this"))
    if where.boosted:
        items.append(t("where.boosted"))
    if where.damaged:
        items.append(t("where.damaged"))
    return items


def _filter(
    t: _Text,
    where: Where,
    rules: Rules,
    rows: Sequence[Row] | None = None,
    default_kind: tuple[Kind, ...] | None = None,
) -> str:
    """The ``{filter}`` parameter: the qualifiers, wrapped, or nothing at all."""
    items = _qualifiers(t, where, rules, rows, default_kind)
    return t("where.wrap", list=t.join(items)) if items else ""


def _tags(t: _Text, tags: Sequence[str]) -> str:
    return t.join([t.renderer.render(t.locale, f"tag.{tag}.name") for tag in tags], "join.or")


def _states(t: _Text, statuses: Sequence[Status]) -> str:
    return t.join([t(f"state.{_word(s.value)}") for s in statuses], "join.or")


def _predicates(t: _Text, where: Where) -> list[str]:
    """What the acting card must be, for ``if.this`` (§6.2): ``same_id_as_this`` always holds
    and ``stronger_than_this`` never does, so neither says anything."""
    items: list[str] = []
    if where.kind is not None:
        items.append(t.join([t(f"is.kind.{k.value}") for k in where.kind], "join.or"))
    if where.color is not None:
        items.append(t(f"is.color.{where.color.value}"))
    if where.tags_any:
        items.append(t("is.tags-any", tags=_tags(t, where.tags_any)))
    if where.tags_none:
        items.append(t("is.tags-none", tags=_tags(t, where.tags_none)))
    if where.statuses_any:
        items.append(t("is.statuses-any", statuses=_states(t, where.statuses_any)))
    if where.statuses_none:
        items.append(t("is.statuses-none", statuses=_states(t, where.statuses_none)))
    if where.power_at_least is not None:
        items.append(t("is.power-at-least", count=where.power_at_least))
    if where.power_at_most is not None:
        items.append(t("is.power-at-most", count=where.power_at_most))
    if where.boosted:
        items.append(t("is.boosted"))
    if where.damaged:
        items.append(t("is.damaged"))
    return items


# --- selectors -----------------------------------------------------------------------------------


def _target(
    t: _Text,
    defn: CardDef,
    ability: Ability,
    previous: Ability | None,
    recipient: bool,
    rules: Rules,
) -> str:
    target = ability.target
    if target is None:
        return ""
    units = target.units
    params: dict[str, Param] = {}
    if units is not Units.THIS:
        params["filter"] = _filter(t, target.where, rules, target.rows, (Kind.UNIT,))
    if units in SIDED_UNITS:
        side = (target.side or Side.OPPONENT).value
        if units is Units.ALL and target.side in (Side.SELF, Side.BOTH) and defn.placed:
            side += "-other"
        key = f"{_word(units.value)}.{side}"
        if units is Units.RANDOM:
            params["count"] = target.count
    else:
        key = _word(units.value)
        if units is Units.PREVIOUS_TARGETS:
            params["count"] = 1 if _names_one_unit(previous) else 2
    if recipient and t.own(TARGET_TO + key):
        return t(TARGET_TO + key, **params)
    return t(TARGET + key, **params)


def _names_one_unit(ability: Ability | None) -> bool:
    target = ability.target if ability is not None else None
    if target is None:
        return True
    return target.units in SINGLE_UNITS or (target.units is Units.RANDOM and target.count == 1)


def _rows(t: _Text, row_target: RowTarget | None, rules: Rules) -> str:
    if row_target is None or row_target.pick is RowPick.THIS:
        return t("rows.this")
    side = (row_target.side or Side.SELF).value
    row = _single_row(row_target.rows, rules)
    if row_target.pick is RowPick.CHOSEN and row is None:
        return t(f"rows.chosen.{side}")
    if row_target.pick is RowPick.CHOSEN and row_target.side is Side.BOTH and row is not None:
        return t(f"rows.chosen.both.{row.value}")
    return t(f"rows.all.{side}" + (f".{row.value}" if row is not None else ""))


def _cards(t: _Text, source: CardSource | None, rules: Rules) -> str:
    """A zone selector as a noun phrase: the pick, the noun for the kind of card, the filter."""
    if source is None:
        return ""
    where = source.where
    if where.same_id_as_this:
        noun, rest = "copy", replace(where, same_id_as_this=False, kind=None)
    elif where.kind is not None and len(where.kind) == 1:
        noun, rest = where.kind[0].value, replace(where, kind=None)
    else:
        noun, rest = "card", where
    params: dict[str, Param] = {"filter": _filter(t, rest, rules)}
    if source.pick.value == "chosen":
        pick = "offer" if source.offer else "chosen"
        if source.offer:
            params["count"] = source.offer
    elif source.pick.value == "all":
        pick = "all" if source.count is None else "up-to"
        if source.count is not None:
            params["count"] = source.count
    else:
        pick = source.pick.value
        params["count"] = source.count or 1
    return t(f"cards.{pick}.{noun}", **params)


def _place(t: _Text, row: Row | None, side: Side) -> str:
    """Where a summoned or new card lands (cards.md §8)."""
    if row is not None:
        return t(f"place.{row.value}.{side.value}")
    return t("place.opponent" if side is Side.OPPONENT else "place.here")


# --- sentences -----------------------------------------------------------------------------------


def _effect(
    t: _Text, defn: CardDef, ability: Ability, previous: Ability | None, rules: Rules
) -> str:
    """One ability as one sentence."""
    do = ability.do
    word = _word(do.value)
    amount = ability.amount

    def target(recipient: bool) -> str:
        return _target(t, defn, ability, previous, recipient, rules)

    if do in (Action.DAMAGE, Action.ADD_ARMOR, Action.RAISE_BASE_POWER, Action.DRAIN):
        return t(f"{word}.text", target=target(True), amount=amount, count=amount)
    if do is Action.BOOST:
        return t("boost.text", target=target(False), amount=amount, count=amount)
    if do is Action.ADD_STATUS and ability.status is not None:
        status = ability.status
        key = f"add-status.{_word(status.value)}"
        tgt = target(status in RECIPIENT_STATUSES)
        if ability.turns is not None:
            return t(f"{key}.timed.text", target=tgt, count=ability.turns)
        return t(f"{key}.text", target=tgt)
    if do is Action.REMOVE_STATUSES:
        if ability.statuses is None:
            return t("remove-statuses.all.text", target=target(False))
        names = [t(f"status.{_word(s.value)}") for s in ability.statuses]
        return t("remove-statuses.text", target=target(False), statuses=t.join(names, "join.and"))
    if do is Action.DRAW:
        side = ".opponent" if ability.side is Side.OPPONENT else ""
        return t(f"draw{side}.text", count=ability.count or 1)
    if do in (
        Action.DISCARD,
        Action.PLAY_FROM_DECK,
        Action.PLAY_FROM_GRAVEYARD,
        Action.SUMMON_FROM_DECK,
    ):
        source = ability.cards
        zone = {Action.DISCARD: "hand", Action.PLAY_FROM_GRAVEYARD: "graveyard"}.get(do, "deck")
        side = source.side.value if source is not None else "self"
        params: dict[str, Param] = {
            "cards": _cards(t, source, rules),
            "from": t(f"from.{zone}.{side}"),
        }
        if do is Action.SUMMON_FROM_DECK:
            params["place"] = _place(t, ability.row, Side.SELF)
        return t(f"{word}.text", **params)
    if do is Action.PLACE_NEW_CARD:
        return t(
            "place-new-card.text",
            count=ability.count or 1,
            card=_Ref(f"@card.{ability.card}.name"),
            place=_place(t, ability.row, ability.side),
        )
    if do is Action.CREATE:
        pool = ability.pool or NO_FILTER
        kinds = pool.kind or ()
        noun = kinds[0].value if len(kinds) == 1 else "card"
        rest = replace(pool, kind=None) if len(kinds) == 1 else pool
        return t(
            f"create.{noun}.text",
            count=ability.offer or DEFAULT_OFFER,
            filter=_filter(t, rest, rules),
        )
    if do is Action.ADD_CHARGES:
        to = (ability.to or ChargeTarget.THIS).value
        return t(f"add-charges.{to}.text", count=amount)
    if do is Action.SET_ROW_EFFECT and ability.effect is not None:
        effect = ability.effect
        counted = effect in COUNTED_ROW_EFFECTS
        return t(
            f"set-row-effect.{_word(effect.value)}.text",
            rows=_rows(t, ability.row_target, rules),
            amount=amount,
            count=(ability.count or 1) if counted else amount,
        )
    if do is Action.CLEAR_ROW_EFFECT:
        only = f".{ability.only.value}" if ability.only is not None else ""
        return t(f"clear-row-effect{only}.text", rows=_rows(t, ability.row_target, rules))
    if do is Action.CONTINUOUS_BOOST and ability.scope is not None:
        return t(f"continuous-boost.{ability.scope.value}.text", amount=amount, count=amount)
    # heal, reset_power, destroy, banish, move_to_other_row, return_to_hand, take_control,
    # duel, consume: a target and nothing else
    return t(f"{word}.text", target=target(False))


def _condition(t: _Text, cond: Conditions, rules: Rules) -> str:
    parts: list[str] = []
    if cond.on_row is not None:
        parts.append(t(f"if.on-row.{cond.on_row.value}"))
    if cond.this is not None:
        predicates = _predicates(t, cond.this)
        if predicates:
            parts.append(t("if.this", state=t.join(predicates, "if.and")))
    if cond.hand_at_most is not None:
        parts.append(t("if.hand-at-most", count=cond.hand_at_most))
    if cond.units_at_least is not None:
        at_least = cond.units_at_least
        parts.append(
            t(
                f"if.units-at-least.{at_least.side.value}",
                count=at_least.count,
                filter=_filter(t, at_least.where, rules, at_least.rows, (Kind.UNIT,)),
            )
        )
    if cond.starting_deck_without_neutral:
        parts.append(t("if.starting-deck-without-neutral"))
    return t.join(parts, "if.and")


def _activation_clause(t: _Text, defn: CardDef, body: str) -> str:
    activation = defn.activation
    charges = activation.charges if activation is not None else 1
    cooldown = activation.cooldown if activation is not None else 0
    effect = body
    if charges is None:
        return t("activate.cooldown", count=cooldown, effect=effect)
    if cooldown:
        return t("activate.charges-cooldown", count=charges, cooldown=cooldown, effect=effect)
    return t("activate.charges", count=charges, effect=effect)


def _group(
    t: _Text,
    defn: CardDef,
    when: Trigger,
    trigger_unit: Where | None,
    abilities: Sequence[Ability],
    rules: Rules,
) -> list[str]:
    parts: list[str] = []
    runs: list[tuple[Conditions, list[str]]] = []
    previous: Ability | None = None
    for ability in abilities:
        cond = replace(ability.cond, trigger_unit=None)
        sentence = _effect(t, defn, ability, previous, rules)
        if runs and runs[-1][0] == cond:
            runs[-1][1].append(sentence)
        else:
            runs.append((cond, [sentence]))
        previous = ability
    for cond, sentences in runs:
        body = t.sentences(sentences)
        if cond != NO_CONDITIONS:
            body = t("if.text", condition=_condition(t, cond, rules), effect=body)
        parts.append(body)
    body = t.sentences(parts)
    if when is Trigger.WHILE_ON_BOARD or (when is Trigger.ON_PLAY and defn.kind is Kind.SPECIAL):
        return [body]
    if when is Trigger.ON_ACTIVATE:
        out = [_activation_clause(t, defn, body)]
        if defn.activation is not None and defn.activation.ready_on_play and defn.placed:
            out.append(t("activate.ready-on-play"))
        return out
    params: dict[str, Param] = {"effect": body}
    if when is Trigger.ON_ALLY_PLAYED:
        params["filter"] = _filter(t, trigger_unit or NO_FILTER, rules, None, (Kind.UNIT,))
    return [t(f"when.{_word(when.value)}", **params)]


def _card_sentences(t: _Text, defn: CardDef, rules: Rules) -> list[str]:
    out: list[str] = []
    row = _single_row(defn.rows, rules)
    if defn.kind is Kind.STRATAGEM and defn.rows:
        out.append(t(f"card.stratagem-row.{defn.rows[0].value}"))
    elif defn.placed and row is not None:
        out.append(t(f"card.row-only.{row.value}"))
    if defn.kind is Kind.UNIT and defn.side is Side.OPPONENT:
        out.append(t("card.opponent-side"))
    if defn.armor:
        out.append(t("card.armor", count=defn.armor))
    out.extend(t(f"card.status.{_word(s.value)}") for s in defn.statuses)
    if defn.kind is Kind.LEADER and defn.provision_bonus:
        out.append(t("card.provision-bonus", count=defn.provision_bonus))
    groups: dict[tuple[Trigger, Where | None], list[Ability]] = {}
    for ability in defn.abilities:
        groups.setdefault((ability.when, ability.cond.trigger_unit), []).append(ability)
    for (when, trigger_unit), abilities in groups.items():
        out.extend(_group(t, defn, when, trigger_unit, abilities, rules))
    return out


# --- public API ----------------------------------------------------------------------------------


class CardText:
    """Builds card texts from the templates of a set of translation tables."""

    def __init__(
        self, tables: Mapping[str, Mapping[str, str]], rules: Rules = DEFAULT_RULES
    ) -> None:
        self.tables = tables
        self.rules = rules
        self.renderer = Renderer(tables)

    def text(self, locale: str, defn: CardDef) -> tuple[str, list[str]]:
        """The generated text of ``defn`` in ``locale``, and the template keys it needed that
        no table defines — not even the base locale's."""
        t = _Text(self.renderer, self.tables, locale)
        return t.sentences(_card_sentences(t, defn, self.rules)), t.missing


def fill_card_texts(
    lib: Library, tables: Mapping[str, Mapping[str, str]], rules: Rules = DEFAULT_RULES
) -> tuple[dict[str, dict[str, str]], list[str]]:
    """``tables`` with ``card.<id>.text`` added wherever a locale lacks it (i18n.md §10), and
    the problems found: template keys missing from every table, and locales whose recipient
    twins are incomplete. An explicit text always wins."""
    out = {locale: dict(table) for locale, table in tables.items()}
    problems = check_templates(tables)
    generator = CardText(tables, rules)
    missing: dict[str, list[str]] = {}
    for locale in sorted(out):
        for cid, defn in lib.items():
            key = f"card.{cid}.text"
            if key in out[locale]:
                continue
            text, lacking = generator.text(locale, defn)
            out[locale][key] = text
            for k in lacking:
                missing.setdefault(k, []).append(cid)
    for key, cards in sorted(missing.items()):
        problems.append(f"{BASE_LOCALE}: {key} (card text of {', '.join(sorted(set(cards)))})")
    return out, problems


def check_templates(tables: Mapping[str, Mapping[str, str]]) -> list[str]:
    """A locale that defines any recipient twin (``ability.target-to.…``) defines all of them,
    so that no sentence mixes the twin of one selector with the plain phrase of another."""
    problems: list[str] = []
    for locale, table in sorted(tables.items()):
        bases = {_plural_base(k) for k in table}
        twins = {k for k in bases if k.startswith(PREFIX + TARGET_TO)}
        if not twins:
            continue
        plain = {k for k in bases if k.startswith(PREFIX + TARGET)}
        for key in sorted(plain):
            twin = PREFIX + TARGET_TO + key[len(PREFIX + TARGET) :]
            if twin not in twins:
                problems.append(f"{locale}: {twin} (a locale with recipient twins needs all)")
    return problems


def _plural_base(key: str) -> str:
    head, _, tail = key.rpartition(".")
    return head if tail in ("zero", "one", "two", "few", "many", "other") else key


__all__ = ["CardText", "check_templates", "fill_card_texts"]
