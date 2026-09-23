"""Build the client's font files from the Noto variable fonts (client/Assets/OpenGwt/Fonts/README.md).

    uv run --with fonttools python server/scripts/fonts.py --src <downloads> --out client/Assets/OpenGwt/Fonts --data data

Static instances are cut from the variable fonts and subset to the scripts the game uses; the CJK
fonts keep GB 2312 plus every character that appears in data/i18n/zh-CN. Nothing else about the
fonts is changed; the OFL licence files are copied next to the output.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

LATIN_CYRILLIC = [
    (0x0000, 0x024F),  # Basic Latin, Latin-1, Latin Extended A and B
    (0x02B0, 0x02FF),  # spacing modifier letters
    (0x0370, 0x03FF),  # Greek
    (0x0400, 0x052F),  # Cyrillic and Cyrillic Supplement
    (0x1E00, 0x1EFF),  # Latin Extended Additional
    (0x2000, 0x206F),  # general punctuation: … – — quotes
    (0x20A0, 0x20CF),  # currency
    (0x2100, 0x214F),  # letterlike: ™ №
    (0x2190, 0x21FF),  # arrows: →
    (0x2200, 0x22FF),  # mathematical operators
    (0x2500, 0x25FF),  # box drawing, blocks, geometric shapes
    (0x2600, 0x27BF),  # miscellaneous symbols and dingbats: ♥ ★ ✓
    (0xFE00, 0xFE0F),  # variation selectors
    (0xFFFD, 0xFFFD),
]
CJK_EXTRA = [
    (0x0020, 0x007E),  # ASCII, so the CJK fonts can stand alone if ever used as primary
    (0x2000, 0x206F),
    (0x3000, 0x303F),  # CJK symbols and punctuation
    (0xFF00, 0xFFEF),  # fullwidth forms
    (0xFFFD, 0xFFFD),
]


def gb2312() -> set[int]:
    """Every character of GB 2312: rows 0xA1–0xF7, columns 0xA1–0xFE."""
    chars: set[int] = set()
    for row in range(0xA1, 0xF8):
        for col in range(0xA1, 0xFF):
            try:
                chars.add(ord(bytes([row, col]).decode("gb2312")))
            except UnicodeDecodeError:
                continue
    return chars


def used_in(data_dir: Path, locale: str) -> set[int]:
    chars: set[int] = set()
    for path in (data_dir / "i18n" / locale).glob("*.yaml"):
        chars.update(ord(c) for c in path.read_text(encoding="utf-8"))
    return chars


def expand(ranges: list[tuple[int, int]]) -> set[int]:
    out: set[int] = set()
    for lo, hi in ranges:
        out.update(range(lo, hi + 1))
    return out


def build(src: Path, out: Path, axes: dict[str, float], unicodes: set[int]) -> int:
    font = TTFont(src)
    if "fvar" in font:
        font = instancer.instantiateVariableFont(font, axes, updateFontNames=True)
    options = subset.Options()
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.notdef_outline = True
    options.hinting = False
    options.desubroutinize = True
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=sorted(unicodes))
    subsetter.subset(font)
    font.save(out)
    return out.stat().st_size


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    latin = expand(LATIN_CYRILLIC)
    cjk = expand(CJK_EXTRA) | gb2312() | used_in(args.data, "zh-CN")
    jobs = [
        ("NotoSans-VF.ttf", "NotoSans-Regular.ttf", {"wght": 400, "wdth": 100}, latin),
        ("NotoSans-VF.ttf", "NotoSans-Bold.ttf", {"wght": 700, "wdth": 100}, latin),
        ("NotoSerif-VF.ttf", "NotoSerif-Regular.ttf", {"wght": 400, "wdth": 100}, latin),
        ("NotoSerif-VF.ttf", "NotoSerif-Bold.ttf", {"wght": 700, "wdth": 100}, latin),
        ("NotoSansSC-VF.ttf", "NotoSansSC-Regular.ttf", {"wght": 400}, cjk),
        ("NotoSerifSC-VF.ttf", "NotoSerifSC-Regular.ttf", {"wght": 400}, cjk),
    ]
    for source, target, axes, unicodes in jobs:
        size = build(args.src / source, args.out / target, axes, unicodes)
        print(f"{target:26} {size / 1024 / 1024:6.2f} MB  ({len(unicodes)} code points requested)")
    for licence in sorted(args.src.glob("OFL-*.txt")):
        shutil.copy(licence, args.out / licence.name)
        print(f"{licence.name:26} copied")


if __name__ == "__main__":
    main()
