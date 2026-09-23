"""Renderer for the ``opengwt.i18n/1`` message format — docs/protocol/i18n.md.

Standard library only. The client carries a C# twin of this module; ``data/i18n/conformance.yaml``
keeps the two equal.
"""

from .renderer import BASE_LOCALE, Param, Renderer, negotiate_locale, plural_category

__all__ = ["BASE_LOCALE", "Param", "Renderer", "negotiate_locale", "plural_category"]
