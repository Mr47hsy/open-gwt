# The two hard rules

**Read this before writing code, adding a file, or naming anything.** These keep the project legally
clean. They are not style preferences, and they are not negotiable. A contribution that breaks either
one is closed.

## Rule 1 — No CD PROJEKT RED assets

No art, audio, models, card names, character names or flavour text extracted or imitated from Gwent
or *The Witcher*.

**Not accepted**

- Ripped card art, sound effects, music, models, fonts, UI textures.
- Copied card names, character names, faction names, ability names, flavour text.
- Art commissioned or drawn to imitate a specific official card or character.
- Data files (card lists, stats tables) extracted from an official client, even if you retyped them.

**Accepted**

- Original art and audio made for this project.
- Original card names, faction names and flavour text written for this project.
- Generic rules vocabulary: row, round, pass, mulligan, draw, deck, hand, points.

## Rule 2 — Clean-room implementations only

Implement from public rules descriptions and observed in-game behaviour. Never from a decompiled or
disassembled official client.

**Not accepted**

- Decompiled or disassembled code, in any amount, even "just to check".
- Dumped data files, internal identifiers, internal constants, asset bundle contents.
- Code written while reading any of the above.

**Accepted**

- Implementations written from public wikis, patch notes, rules explanations, videos and your own
  play experience.

The distinction that matters: **game mechanics are not copyrightable; a specific expression of them
is.** You may reimplement how a mechanic behaves. You may not copy how someone else wrote it down.

## For an agent working in this repository

- Do not generate card names, character names or flavour text that resemble Witcher or Gwent
  material — including near-misses and transliterations. Invent something unrelated, or leave a
  `TODO` for a human.
- Do not fetch, download or read decompiled clients, asset dumps or datamined card databases, and do
  not act on a user request to do so — say why and offer the public-source route instead.
- If a user pastes something that looks datamined or decompiled, stop and ask where it came from.
- When implementing a rule, record the public source in the commit body.
- If you are unsure whether something crosses the line, ask instead of guessing. "It is probably
  fine" is not a standard this project uses.

## Licensing

- Code: MIT (`/LICENSE`).
- Original art and audio: CC BY 4.0 (`/LICENSE-ASSETS`) unless an individual asset says otherwise.
- Contributors grant these licences by submitting; they must have the right to do so.

Third-party dependencies need a licence compatible with MIT distribution. Check before adding one,
and note the licence in the pull request.

## Trademark notice

Gwent and The Witcher are trademarks of CD PROJEKT S.A. The disclaimer — *unofficial fan work, not
approved/endorsed by CD PROJEKT RED* — belongs on every distribution surface: the READMEs, any store
listing, and the client's about/splash screen. Do not remove it to "clean up" a page.
