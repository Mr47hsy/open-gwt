export const meta = {
  name: 'ability-to-vocabulary',
  description: 'Draft opengwt.cards/2 abilities from natural-language card designs, verify each against its text, and report the vocabulary gaps',
  whenToUse: 'The owner has original card designs whose abilities are written in plain language (a spreadsheet CSV, YAML, JSON or a Markdown table) and wants an importable card set plus the list of mechanics the vocabulary cannot express yet. args: {source, set, locale?, out?, batch?}',
  phases: [
    { title: 'Guard', detail: 'check the input is original, normalise it, split it into batches' },
    { title: 'Translate', detail: 'one agent per batch writes the draft abilities and the unmapped phrases' },
    { title: 'Verify', detail: 'an independent agent per batch checks the drafts with opengwt-data check-set and fixes misreadings' },
    { title: 'Assemble', detail: 'merge the drafts into one card set, dry-run the import, write the gap report' },
  ],
}

// args: {source: path to the designs, set: set id, locale: language of the ability text (default
// zh-CN), out: output directory (default .drafts/<set>), batch: cards per batch (default 8)}.
// Paths are relative to the repository root; every agent works from there.
const A = args || {}
if (!A.source || !A.set) {
  throw new Error('args needs {source, set}; optional {locale, out, batch}')
}
const SET = A.set
const LOCALE = A.locale || 'zh-CN'
const OUT = A.out || `.drafts/${SET}`
const BATCH = A.batch || 8

const GROUND = `Work from the repository root (\`cd "$(git rev-parse --show-toplevel)"\`). The card vocabulary is opengwt.cards/2: read docs/protocol/cards.md (triggers §6.1, conditions §6.2, activation §6.3, selectors §7, actions §8, statuses §9, row effects §10, turn and resolution §11, decks §12) and docs/protocol/cards.schema.json, which is normative. The card-set format the drafts are written in is docs/protocol/import.md (opengwt.cardset/1). Never edit anything under data/, docs/ or server/; write only under ${OUT}/.`

const LEGAL = `Legal rules, non-negotiable (.agent/context/04-legal.md): the input must be the owner's ORIGINAL design. Stop, write nothing, and report why if it contains official card or character names, official flavour text, official card/art/audio ids, a game version, links to card-database sites, or if the set as a whole reproduces the official game's cards (names, stats and texts matching official ones). Official keyword shorthand in an otherwise original design is not by itself a reason to stop, but list it in notes: the drafts never carry it, since card text is generated from the vocabulary.`

const GUARD = {
  type: 'object',
  properties: {
    ok: { type: 'boolean' },
    reason: { type: 'string' },
    count: { type: 'integer' },
    batches: { type: 'array', items: { type: 'string' } },
    notes: { type: 'string' },
  },
  required: ['ok', 'reason', 'count', 'batches'],
}

const UNMAPPED = {
  type: 'object',
  properties: {
    phrase: { type: 'string', description: 'the words of the design the vocabulary cannot express' },
    why: { type: 'string' },
    layer: { type: 'string', enum: ['trigger', 'condition', 'activation', 'selector', 'filter', 'action', 'status', 'row_effect', 'card_field', 'rules', 'engine'] },
    proposal_id: { type: 'string', description: 'a descriptive snake_case id for the missing word; never an official keyword' },
    semantics: { type: 'string', description: 'what the new word would do, precisely, with its parameters' },
  },
  required: ['phrase', 'why', 'layer', 'proposal_id', 'semantics'],
}

const TRANSLATED = {
  type: 'object',
  properties: {
    draft: { type: 'string', description: 'path of the draft file written' },
    cards: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          key: { type: 'string' },
          status: { type: 'string', enum: ['mapped', 'partial', 'unmapped'] },
          unmapped: { type: 'array', items: UNMAPPED },
          assumptions: { type: 'array', items: { type: 'string' } },
        },
        required: ['key', 'status', 'unmapped', 'assumptions'],
      },
    },
  },
  required: ['draft', 'cards'],
}

const VERIFIED = {
  type: 'object',
  properties: {
    clean: { type: 'boolean', description: 'check-set reports no problem for the batch after your fixes' },
    cards: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          key: { type: 'string' },
          verdict: { type: 'string', enum: ['faithful', 'fixed', 'lossy'] },
          note: { type: 'string' },
          generated_text: { type: 'string' },
          extra_unmapped: { type: 'array', items: UNMAPPED },
        },
        required: ['key', 'verdict', 'note', 'generated_text', 'extra_unmapped'],
      },
    },
  },
  required: ['clean', 'cards'],
}

const ASSEMBLED = {
  type: 'object',
  properties: {
    cardset: { type: 'string' },
    report: { type: 'string' },
    import_ok: { type: 'boolean' },
    remaining_problems: { type: 'array', items: { type: 'string' } },
  },
  required: ['cardset', 'report', 'import_ok', 'remaining_problems'],
}

phase('Guard')
const guard = await agent(
  `${GROUND}\n\n${LEGAL}\n\nInput: ${A.source}. It holds card designs whose abilities are written in plain ${LOCALE}; its shape may be a CSV, YAML, JSON or a Markdown table. Read all of it. If the legal rules say stop, return ok=false with the reason and write nothing.\n\nOtherwise normalise every card to a JSON object {key, faction, kind, color, provisions, power, armor, rows, side, tags, token, provision_bonus, name: {<locale>: text}, ability: "<the plain-language ability text, verbatim>"} — keys and ids lower-case matching ^[a-z][a-z0-9-]{1,63}$ (derive a key from the designer's own id or a slug of the name if none), kinds unit/special/artifact/leader/stratagem, colours bronze/gold, rows melee/ranged; leave out what the design does not give. Write them in order, ${BATCH} per file, as JSON arrays to ${OUT}/batches/01.json, 02.json, … (mkdir -p first). Return the file paths, the card count, and in notes anything ambiguous (unknown columns, missing fields, keyword shorthand).`,
  { label: 'guard', phase: 'Guard', schema: GUARD },
)
if (!guard || !guard.ok) {
  log(`stopped: ${guard ? guard.reason : 'the guard agent failed'}`)
  return { ok: false, reason: guard ? guard.reason : 'guard failed' }
}
log(`${guard.count} cards in ${guard.batches.length} batches`)

const results = await pipeline(
  guard.batches,
  (batch, _item, i) => agent(
    `${GROUND}\n\nTranslate the card designs in ${batch} (plain ${LOCALE}) into the vocabulary. Write ${OUT}/drafts/${String(i + 1).padStart(2, '0')}.yaml: an opengwt.cardset/1 file with set: ${SET} and a cards list, each card with its key, faction, fields, name and the abilities (and activation, statuses, armor, rows, side where the text implies them) that say exactly what the design says — triggers, conditions, targets and sides, counts, amounts, timers, charges and cooldowns. A card names another card of the set by its key.\n\nNever approximate: a phrase the vocabulary cannot express is left out of the YAML and reported as unmapped, with the layer it would need and a proposed descriptive word (never an official keyword name) and its semantics. Read the vocabulary carefully before declaring a phrase unmapped — combinations of triggers, conditions, selectors, statuses, row effects and activation express a lot. Record every interpretation you had to choose in assumptions. Check the file with \`cd server && uv run opengwt-data check-set ../${OUT}/drafts/${String(i + 1).padStart(2, '0')}.yaml --set ${SET} --locale ${LOCALE} --data ../data\` and fix schema problems before returning.`,
    { label: `translate:${i + 1}`, phase: 'Translate', schema: TRANSLATED },
  ),
  (translated, batch, i) => {
    if (!translated) return null
    const draft = translated.draft
    return agent(
      `${GROUND}\n\nYou independently check a draft another agent wrote. Designs (plain ${LOCALE}): ${batch}. Draft: ${draft}. The translator's report: ${JSON.stringify(translated.cards)}\n\nRun \`cd server && uv run opengwt-data check-set ../${draft} --set ${SET} --locale ${LOCALE} --data ../data\`. For every card, compare the generated text with the design's own ability text: does the YAML say the same thing — trigger and timing, conditions, targets and sides, how many, how much, timers, charges, cooldown, where cards come from and go? Fix the draft in place where it misreads the design or fails the schema, and re-run until check-set is clean. Do not add abilities that approximate an unmapped phrase; if the translator dropped something without reporting it, report it in extra_unmapped. verdict: faithful (nothing to change), fixed (you changed it; say what), lossy (part of the design is unmapped).`,
      { label: `verify:${i + 1}`, phase: 'Verify', schema: VERIFIED },
    ).then((verified) => ({ batch, draft, translated, verified }))
  },
)

const done = results.filter(Boolean)
const cards = []
const gaps = new Map()
for (const r of done) {
  const verdicts = new Map((r.verified ? r.verified.cards : []).map((c) => [c.key, c]))
  for (const c of r.translated.cards) {
    const v = verdicts.get(c.key)
    const unmapped = [...c.unmapped, ...(v ? v.extra_unmapped : [])]
    cards.push({ key: c.key, status: unmapped.length ? (c.status === 'mapped' ? 'partial' : c.status) : c.status, verdict: v ? v.verdict : 'unverified', note: v ? v.note : '', text: v ? v.generated_text : '', assumptions: c.assumptions, unmapped })
    for (const u of unmapped) {
      const id = (u.proposal_id || 'unnamed').toLowerCase().replace(/[^a-z0-9_]+/g, '_')
      const g = gaps.get(id) || { proposal_id: id, layer: u.layer, semantics: u.semantics, cards: [], phrases: [] }
      g.cards.push(c.key)
      if (g.phrases.length < 5) g.phrases.push(u.phrase)
      gaps.set(id, g)
    }
  }
}
const gapList = [...gaps.values()].sort((a, b) => b.cards.length - a.cards.length)
const unverified = guard.batches.length - done.filter((r) => r.verified).length
if (unverified) log(`${unverified} batches were not verified — their cards are marked unverified in the report`)
log(`${cards.length} cards drafted; ${gapList.length} distinct vocabulary gaps`)

phase('Assemble')
const assembled = await agent(
  `${GROUND}\n\nMerge the drafts ${done.map((r) => r.draft).join(', ')} into one card set ${OUT}/${SET}.cardset.yaml (schema opengwt.cardset/1, set ${SET}; add a factions section naming each faction the cards use, with names only where the designs gave them). Validate it with \`cd server && uv run opengwt-data import ../${OUT}/${SET}.cardset.yaml --data ../data --dry-run\` (a dry run writes nothing). Fix only mechanical problems — a key reference across batches, a duplicate key — and list whatever else remains; never invent stats or abilities to satisfy a rule.\n\nThen write ${OUT}/gaps.md for the owner, in Chinese with the vocabulary ids in English: 1) a summary — cards drafted, faithful / fixed / lossy / unverified counts, import dry-run result; 2) the vocabulary gaps, most frequent first — proposed id, layer, semantics, how many cards need it, which cards, example phrases (each gap needs the owner's decision and a public source before it becomes a word, per the project's rules); 3) per card — key, status, verdict, the verifier's note, the generated ${LOCALE} text, assumptions. Data: ${JSON.stringify({ cards, gaps: gapList, guard_notes: guard.notes || '' })}`,
  { label: 'assemble', phase: 'Assemble', schema: ASSEMBLED },
)

const counts = {}
for (const c of cards) counts[c.verdict] = (counts[c.verdict] || 0) + 1
return {
  ok: true,
  cards: cards.length,
  verdicts: counts,
  gaps: gapList.map((g) => ({ id: g.proposal_id, layer: g.layer, cards: g.cards.length })),
  cardset: assembled ? assembled.cardset : null,
  report: assembled ? assembled.report : null,
  import_ok: assembled ? assembled.import_ok : false,
  remaining_problems: assembled ? assembled.remaining_problems : [],
}
