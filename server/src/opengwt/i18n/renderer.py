from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

BASE_LOCALE = "en"
Param = int | str

_NAME = re.compile(r"[a-z][a-z0-9_]*")


def plural_category(locale: str, count: int) -> str:
    """CLDR plural category of an integer for the supported locales (docs/protocol/i18n.md §5)."""
    n = abs(count)
    if locale == "en":
        return "one" if n == 1 else "other"
    if locale == "zh-CN":
        return "other"
    if locale == "ru":
        if n % 10 == 1 and n % 100 != 11:
            return "one"
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return "few"
        return "many"
    return "other"


def _check_params(params: Mapping[str, Param]) -> None:
    for name, value in params.items():
        if isinstance(value, bool) or not isinstance(value, int | str):
            raise ValueError(f"parameter {name!r} must be an integer or a string")
    count = params.get("count")
    if count is not None and (isinstance(count, bool) or not isinstance(count, int)):
        raise ValueError("parameter 'count' must be an integer")


class Renderer:
    """Renders keys with parameters; see the protocol document for every rule implemented here."""

    def __init__(self, tables: Mapping[str, Mapping[str, str]], base: str = BASE_LOCALE) -> None:
        self._tables = {locale: dict(table) for locale, table in tables.items()}
        self._base = base

    @property
    def locales(self) -> tuple[str, ...]:
        return tuple(sorted(self._tables))

    def has(self, locale: str) -> bool:
        return locale in self._tables

    def lookup(self, locale: str, key: str, count: int | None = None) -> str | None:
        """Locale-major lookup with plural variants (§6); None when the key is missing."""
        candidates = [key]
        if count is not None:
            candidates = [f"{key}.{plural_category(locale, count)}", f"{key}.other", key]
        for loc in (locale, self._base):
            table = self._tables.get(loc)
            if table is None:
                continue
            for candidate in candidates:
                message = table.get(candidate)
                if message is not None:
                    return message
        return None

    def render(self, locale: str, key: str, params: Mapping[str, Param] | None = None) -> str:
        params = dict(params or {})
        _check_params(params)
        count = params.get("count")
        message = self.lookup(locale, key, count if isinstance(count, int) else None)
        if message is None:
            return key
        return self._format(locale, message, params)

    def _format(self, locale: str, message: str, params: Mapping[str, Param]) -> str:
        out: list[str] = []
        i = 0
        while i < len(message):
            if message.startswith("{{", i):
                out.append("{")
                i += 2
                continue
            if message.startswith("}}", i):
                out.append("}")
                i += 2
                continue
            if message[i] == "{":
                end = message.find("}", i)
                name = message[i + 1 : end] if end != -1 else ""
                if _NAME.fullmatch(name) and name in params:
                    out.append(self._param(locale, params[name]))
                    i = end + 1
                    continue
            out.append(message[i])
            i += 1
        return "".join(out)

    def _param(self, locale: str, value: Param) -> str:
        if isinstance(value, int):
            return str(value)
        if value.startswith("@@"):
            return value[1:]
        if value.startswith("@"):
            ref = value[1:]
            message = self.lookup(locale, ref)
            return ref if message is None else message
        return value


def negotiate_locale(
    supported: Sequence[str],
    preferred: str | None = None,
    accept_language: str | None = None,
    base: str = BASE_LOCALE,
) -> str:
    """Profile locale, then the best ``Accept-Language`` match, then the base (§8)."""
    by_lower = {s.lower(): s for s in supported}
    if preferred and preferred.lower() in by_lower:
        return by_lower[preferred.lower()]
    for tag in _accept_language_tags(accept_language):
        if tag in by_lower:
            return by_lower[tag]
        prefix = tag.split("-")[0]
        for lowered, original in by_lower.items():
            if lowered.split("-")[0] == prefix:
                return original
    return base


def _accept_language_tags(header: str | None) -> list[str]:
    """Language tags of an Accept-Language header, best quality first, lower-cased."""
    if not header:
        return []
    weighted: list[tuple[float, int, str]] = []
    for index, part in enumerate(header.split(",")):
        piece = part.strip()
        if not piece:
            continue
        tag, _, rest = piece.partition(";")
        quality = 1.0
        rest = rest.strip()
        if rest.startswith("q="):
            try:
                quality = float(rest[2:])
            except ValueError:
                quality = 0.0
        if quality > 0 and tag.strip() != "*":
            weighted.append((-quality, index, tag.strip().lower()))
    return [tag for _, _, tag in sorted(weighted)]
