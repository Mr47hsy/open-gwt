---
name: licensing-split
description: Code is MIT, original art and audio are CC BY 4.0; contributors grant both on submission.
metadata:
  type: project
---

Decided 2026-09-22: source code is released under the MIT License (`/LICENSE`, "Copyright (c) 2026
the open-gwt contributors"), and original art, audio, models and other non-code assets under CC BY
4.0 (`/LICENSE-ASSETS`), unless an individual asset states otherwise. `CONTRIBUTING` contains the
clause by which contributors grant both licences on submission.

**Why:** a single licence does not fit both halves — MIT is the right fit for code and a poor fit for
artwork, where attribution is the thing contributors actually care about. Keeping the split explicit
also makes it obvious that no third-party asset can be dropped in silently.

**How to apply:** new third-party dependencies need a licence compatible with MIT distribution —
check and note it in the pull request. Assets contributed under something other than CC BY 4.0 must
say so per file. See [[legal-red-lines]].
