# draft-d：能力草稿与词汇缺口报告

来源：`.drafts/draft-d/batches/01.json`、`02.json`（中文设计，与
`docs/protocol/examples/draft-abilities.csv` 相同）→ 草稿 `drafts/01.yaml`、`drafts/02.yaml` →
合并卡组 `.drafts/draft-d/draft-d.cardset.yaml`。整个 `.drafts/` 被 git 忽略；这是给所有者审阅的提案，
不是正式内容。

## 1. 摘要

| 项目 | 结果 |
| --- | --- |
| 起草卡牌 | 13 张（批次 01：7 张，dr-scout … dr-herald；批次 02：6 张，dr-recruit … dr-scholar），全部属于阵营 `draft-d` |
| 判定 | faithful 10 · fixed 0 · lossy 3 · unverified 0 |
| 映射状态 | mapped 10 · partial 0 · unmapped 3（dr-alchemist、dr-shifter、dr-scholar） |
| 词汇缺口 | 5 个，各被 1 张卡需要 |
| 导入试运行 | **通过**（`opengwt-data import … --dry-run`，退出码 0，未写入任何文件） |

导入试运行的输出：

- `set draft-d: 13 cards (draft-d 13), 0 decks`
- 将分配的 id：dr-scout → `u-3001`、dr-medic → `u-3002`、dr-drummer → `u-3003`、dr-sentry → `u-3004`、
  dr-trapper → `s-3001`、dr-rally → `s-3002`、dr-herald → `u-3005`、dr-recruit → `t-3001`、
  dr-alchemist → `u-3006`、dr-shifter → `u-3007`、dr-captain → `l-3001`、dr-gambit → `g-3001`、
  dr-scholar → `u-3008`
- 待翻译名称（`TODO(i18n)` 占位）：en 1、ru 14、zh-CN 1
- 由能力生成的卡面文本：en 13、ru 13、zh-CN 13
- 将写入：`data/cards/draft-d.cards.yaml`、`data/i18n/{en,ru,zh-CN}/draft-d.cards.yaml`、
  `data/import/draft-d.yaml`

合并时的机械修正：**无需修正**。dr-herald（批次 01）引用的 `dr-recruit` 在批次 02 中定义，
合并后正常解析（合并后的卡面文本显示“草稿新兵”，单独检查批次 01 时显示为 `card.dr-recruit.name`）；
两个批次没有重复的 key。新增了 `factions: { draft-d: {} }`：设计没有给阵营名称，所以只列出 id。

仍待所有者决定的事项（都不是机械问题，没有自行补全）：

1. 阵营 `draft-d` 没有任何语言的名称：导入会在 en、zh-CN、ru 各生成一个 `TODO(i18n)` 占位。
2. 13 张卡都没有 ru 名称：导入会生成 13 个 ru 占位（与第 1 项合计 ru 14 个）。
3. 3 张 lossy 卡（dr-alchemist、dr-shifter、dr-scholar）的整个能力都无法表达，草稿中只保留了数值。
   如果现在导入，它们会成为没有能力的白板单位，与设计不符；是否在缺口成为词汇之前导入，由所有者决定。
4. 设计中没有卡组：cards.md §12 的卡组规则（张数、单位数、副本、预算）没有被检验，
   领袖 dr-captain 和计策 dr-gambit 也没有被任何卡组使用。

所有者 2026-09-24 的三条解读（SKILL.md §2）已在本批中落实：医师的治疗不包括自身（dr-medic，
`all` 本身就排除发动能力的卡）；炼金师的“第一次”指整场对战一次（见缺口 `once_per_match`）；
易形者变出的新兵归易形者的控制者所有（见缺口 `transform_in_place`）。

## 2. 词汇缺口

五个缺口各被 1 张卡需要，频次相同，按出现顺序排列。每个缺口都要经所有者决定、并有公开来源，
才能成为词汇（cards.md §15：规则核心变更，升级 schema 版本并附测试）。这五个缺口已按样例记录在
`.agent/memory/backlog.md`（提交 7274d5b），连同所有者的决定。

| # | 提议 id | 层 | 卡数 | 卡牌 |
| --- | --- | --- | --- | --- |
| 1 | `on_power_reached` | trigger | 1 | dr-alchemist |
| 2 | `once_per_match` | condition | 1 | dr-alchemist |
| 3 | `transform_in_place` | action | 1 | dr-shifter |
| 4 | `hand_card_to_deck_bottom` | action | 1 | dr-scholar |
| 5 | `reveal_to_opponent` | action（实为动作参数） | 1 | dr-scholar |

dr-alchemist 需要 1 和 2 同时存在，dr-scholar 需要 4 和 5 同时存在，才能完整表达。

### 2.1 `on_power_reached`（trigger）

- **卡数**：1 —— dr-alchemist
- **例句**：“当此单位的战力……达到 8 或更高时”
- **语义**：触发器，参数 `amount`（正整数），仅限单位。当场上的此单位的战力（current + aura，
  cards.md §11.1）从低于 `amount` 变为不低于 `amount` 时触发，无论原因：`boost`、`raise_base_power`、
  出现的光环（带 `continuous_boost` 的卡进场或解除锁定），或单位进场时就已达到。在单位战力的每次变化后
  检查（包括光环），而不只是在消灭检查时。行动方是单位的控制者。“整场对战一次”的限制由单独的词
  `once_per_match` 提供。
- **为何现有词汇不够**：没有在战力越过阈值时触发的触发器。`on_boosted` 加
  `if: {this: {power_at_least: 8}}` 被视为近似而放弃：它在战力 ≥ 8 时每次被增益都会触发，而不是一次；
  并且 `raise_base_power` 和 `continuous_boost` 光环不会触发 `on_boosted`，这些途径会被漏掉。
- **请所有者确认**：单位进场时已达阈值是否算“达到”；光环在 cards.md §11.1 中每次读取时重算、从不存储，
  所以这个触发器需要引擎在每次战力变化前后比较，是一个新的检查点。

### 2.2 `once_per_match`（condition）

- **卡数**：1 —— dr-alchemist
- **例句**：“第一次”
- **语义**：条件 `once_per_match: true`。当此卡实例的这个能力在本场对战中尚未结算过时成立。
  能力在条件满足时第一次结算后，记录在实例上，保留整场对战——跨局、跨区域：实例离场时保留其 id
  （cards.md §5），这个记录必须在离场重置场上状态时保留下来。因条件不满足而被跳过的能力不记录。
  依照所有者的约定（SKILL.md §2）：“第一次 / 首次”指整场对战一次，而不是每次在场一次。
- **为何现有词汇不够**：词汇中没有限制触发型能力结算次数的词；次数和冷却（activation）只适用于
  `on_activate` 能力。

### 2.3 `transform_in_place`（action）

- **卡数**：1 —— dr-shifter
- **例句**：“把一个敌方单位变成一张“草稿新兵”，保留其所在位置”
- **语义**：动作，参数 `target`（单位选择器）和 `card`（单位或器物的 id，或本卡组的 key，与
  `place_new_card` 相同）。每个目标在同一方的同一行、同一位置被 `card` 的一个新实例取代。
  新实例归行动方所有，即发动这个能力的卡的控制者（所有者的约定，SKILL.md §2），无论它站在哪一侧；
  所以站在对手一侧时带有 `on_enemy_side`。它获得自己的固有状态（衍生卡还获得 `banish_on_leave`）和印刷战力，
  不继承目标的增益、伤害、护甲或状态。它不是被打出，所以 `on_play` 和 `on_ally_played` 都不触发；
  它也没有移动，所以 `damage_on_arrival` 不起作用。被取代的卡离场进入其所有者的放逐区，不触发
  `on_destroyed`。
- **为何现有词汇不够**：没有原地变形的动作。`banish` 加 `place_new_card`（`card: dr-recruit`、
  `side: opponent`）被视为近似而放弃：`place_new_card` 把新卡放在发动卡所在的行（或一个固定行），
  发动卡右侧或行的最右端，不能使用目标的行和位置，也没有选择器能把目标的位置传给下一个能力。
- **请所有者确认**：设计没有说原来那张卡去哪里；“放逐、不触发 `on_destroyed`”是提案。另外，
  cards.md §10 的 `damage_on_arrival` 对“新放置”（placed new）的单位也生效，而提案让变形出的新卡不受它影响；
  两者哪个更合适，也请所有者决定。

### 2.4 `hand_card_to_deck_bottom`（action）

- **卡数**：1 —— dr-scholar
- **例句**：“从你的手牌中选择一张牌……然后把它放到你牌库的底部”
- **语义**：动作，参数 `cards`，一个作用于 `side`（默认 `self`）手牌的卡牌选择器（cards.md §7.3）。
  `pick: chosen` 是 `card` 类的选择；因为手牌是隐藏的，这个选择不能取消。每张被选的卡按选择顺序
  依次离开手牌，放到其所有者牌库的底部，不触发它的任何能力。没有候选时什么都不发生，也不询问选择。
  `pick: chosen` 只允许用于 `on_play` 和 `on_activate` 能力。
- **为何现有词汇不够**：没有把手牌移到牌库的动作。`discard` 是唯一从手牌取卡的动作，而它把卡送进墓地。

### 2.5 `reveal_to_opponent`（action 层，实为参数）

- **卡数**：1 —— dr-scholar
- **例句**：“展示给对手”
- **语义**：`hand_card_to_deck_bottom`（或任何从隐藏区域选卡的动作）上的参数 `reveal: true`。
  每张被选的卡移动之前，通过一个对战事件把它的卡牌 id 展示给对手（match.md 的隐藏信息规则）。
  卡牌和区域的其他一切都不变。
- **为何现有词汇不够**：没有把隐藏的卡展示给对手的动作。展示必须作用于随后被放到牌库底部的同一张卡，
  而词汇中没有卡牌层面的“上一次选择”选择器，无法把两个动作串在同一张手牌上。

## 3. 逐卡结果

生成的 zh-CN 文本取自合并后卡组的 `import --dry-run --preview zh-CN`。

### dr-scout

- **状态**：mapped · **判定**：faithful
- **校验者说明**：`on_play` 对行动方在对手一侧选择的一个单位造成 3 点伤害（`units: chosen`、
  `side: opponent`）。触发时机、目标、一侧、数量和数值都与设计一致。未改动。
- **生成文本**：打出时：对一个敌方单位造成3点伤害。
- **假设**：
  - “一个敌方单位”理解为行动方选择的单位（`units: chosen`、`side: opponent`），而不是随机单位；
    作为玩家的选择，它从不提供免疫单位（cards.md §7.1）。

### dr-medic

- **状态**：mapped · **判定**：faithful
- **校验者说明**：`on_play` 的 `heal`，`units: all`、`side: self`、`where: {damaged: true}`。
  依照 SKILL.md §2（所有者的决定：“所有”从不包括卡牌自身），医师不治疗自己：`all` 本身就排除发动能力的卡，
  草稿也没有额外的自我治疗。`damaged` 过滤与“受伤的”对应，在机制上不改变任何结果。未改动。
- **生成文本**：打出时：治疗所有其他友方单位（已受伤）。
- **假设**：
  - 依照 SKILL.md §2（所有者的决定），“所有受伤的友方单位”不包括医师自身：`units: all`、`side: self`
    排除发动能力的卡；没有为医师自身添加治疗能力。
  - “受伤的”保留为显式过滤 `where: {damaged: true}`；`heal` 本来就只把受伤单位恢复到基础战力并保留增益，
    所以这个过滤在机制上不改变任何结果。

### dr-drummer

- **状态**：mapped · **判定**：faithful
- **校验者说明**：“在场时”是 `while_on_board` 的 `continuous_boost` +1，`scope: adjacent`。这是作用于鼓手
  所在一方的行上左右紧邻的单位的持续光环，鼓手离场或被锁定时停止。与设计一致。未改动。
- **生成文本**：相邻单位战力+1。
- **假设**：
  - “在场时 … 战力 +1”理解为持续光环（`while_on_board` `continuous_boost`，`scope: adjacent`），而不是一次性增益：
    鼓手离场或被锁定时结束。
  - “相邻的单位”指鼓手所在一方的行上紧邻其左右的单位，即词汇中的“相邻”（cards.md §5）。

### dr-sentry

- **状态**：mapped · **判定**：faithful
- **校验者说明**：固有状态 `statuses: [immune]`，没有计时，所以是永久的。`rows: [melee]` 对应“只能放在近战行”，
  护甲 2 来自设计的 armor 字段。`on_turn_start` 在其控制者的每个回合开始时给自身（`units: this`）增益 1，
  即“你的每个回合开始时”。未改动。
- **生成文本**：只能打出在近战行。护甲2。免疫：不会作为选择目标出现。你的回合开始时：使自身获得1点增益。
- **假设**：
  - 护甲 2 来自设计的 armor 字段，能力文本中没有提到。
  - “免疫”是固有状态 `immune`，只让单位不出现在玩家的选择（`chosen`）中；`all` / `random` / 行效果仍然能作用于它
    （cards.md §9）。
  - “只能放在近战行”是 `rows: [melee]`；只约束打出，不约束之后的移动。
  - “你的每个回合开始时”是 `on_turn_start`，跟随卡牌控制者的回合；如果哨兵换边，它在新控制者的回合开始时增益。

### dr-trapper

- **状态**：mapped · **判定**：faithful
- **校验者说明**：这张特殊牌有两个按顺序的 `on_play` 能力。第一个给玩家在对手一侧选择的单位添加没有 `turns` 的
  `locked`（永久锁定）；第二个对 `units: previous_targets`，即同一单位，造成 2 点伤害。顺序和“同一单位”的关联
  与设计（锁定……然后……）一致。未改动。
- **生成文本**：锁定一个敌方单位。对同一目标造成2点伤害。
- **假设**：
  - 没有期限的“锁定”是永久锁定（`add_status` `locked`，不带 `turns`）。
  - “一个敌方单位”是行动方的选择（`units: chosen`、`side: opponent`）。
  - “然后对同一单位”是同一张卡下一个 `on_play` 能力上的 `units: previous_targets`；如果被选单位有
    `status_proof`，锁定无效，但伤害仍作用于第一个能力选中的单位。

### dr-rally

- **状态**：mapped · **判定**：faithful
- **校验者说明**：`on_play` 的 `play_from_deck`，`pick: chosen`、`side: self`、
  `where: {kind: [unit], color: bronze, power_at_most: 4}`。在场外，`power_at_most` 检查印刷战力，所以
  “战力不高于 4”是对的。也核对了其他 pick 的生成文本：`random` 显示为“随机”，`first` 显示为“最前面的”，
  所以这里的“一个单位”是玩家自己的选择，与“一张”的读法一致。未改动。
- **生成文本**：从你的牌库中打出一个单位（铜卡、战力不高于4）。
- **假设**：
  - “一张”理解为行动方在自己牌库所有符合条件的卡中选择（`pick: chosen`、`side: self`，无 `offer`），
    而不是随机一张。
  - “战力不高于 4”使用印刷战力（在场外），“铜色单位”是 `where: {kind: [unit], color: bronze}`；
    衍生卡从不在牌库中，所以不会被选中。

### dr-herald

- **状态**：mapped · **判定**：faithful
- **校验者说明**：`on_play` 的 `place_new_card`，`card: dr-recruit`（批次 02 的衍生卡 key），`count: 2`，
  默认 `side: self`，没有 `row`。新兵放在传令官所在的行、传令官右侧，归行动方所有（在此牌旁边放置两张）。
  单独检查批次 01 时名称显示为 `card.dr-recruit.name`，只是因为衍生卡在批次 02 中。未改动。
- **生成文本**：打出时：在此牌旁边放置2张新的“草稿新兵”。
  （单独检查批次 01 时为“打出时：在此牌旁边放置2张新的“card.dr-recruit.name”。”，合并后名称已解析。）
- **假设**：
  - “草稿新兵”是本卡组的 key `dr-recruit`（批次 02 的衍生卡）；单独对这个批次运行 check-set 时，
    名称显示为 `card.dr-recruit.name`，直到批次合并。
  - “在此牌旁边”理解为 `place_new_card` 的放置方式：在传令官一侧和所在行、传令官右侧，第二个新兵在第一个右侧；
    行已满时不放置。“左右各放一个”无法表达，也没有从设计中这样解读。
  - 新兵归传令官能力的行动方所有，并带有 `banish_on_leave`，与 `place_new_card` 的行为一致；它们是被放置而不是被打出，
    所以不触发 `on_play` 或 `on_ally_played`。

### dr-recruit

- **状态**：mapped · **判定**：faithful
- **校验者说明**：设计文本只说明这是一张从不在卡组中的衍生卡。这正是战力 1、没有颜色和构筑费用的单位上的
  `token: true`。设计没有给它能力，所以它没有 `abilities`，生成文本为空。无需改动。
- **生成文本**：（空——设计没有能力）
- **假设**：
  - “衍生卡，不会出现在卡组中”正是 `token: true`（从不在卡组中，只能通过能力上场，离场时总是被放逐）。
    设计没有给能力、标签、行或颜色；衍生卡没有颜色和构筑费用。

### dr-alchemist

- **状态**：unmapped · **判定**：lossy
- **校验者说明**：整个能力都无法表达，卡牌只保留数值。翻译者报告了缺少的两个词：战力达到阈值的触发器
  （`on_power_reached`，`amount: 8`）和整场对战一次的限制（`once_per_match`）。放弃 `on_boosted` 加
  `if: {this: {power_at_least: 8}}` 这种近似是正确的：它在 ≥ 8 时每次被增益都会触发，并且漏掉
  `raise_base_power` 和光环。“第一次”按整场对战一次理解，遵循 SKILL.md §2 中所有者的约定，所有者在本次请求中
  也再次确认。随后的抽牌（“抽一张牌”，即 `do: draw`、`count: 1`、`side: self`）可以表达，但没有可挂的触发器。
  把它一并省略是正确的，且已报告。草稿没有问题。
- **生成文本**：（空——能力未映射）
- **假设**：
  - 适用所有者的约定：“第一次”指整场对战一次，而不是每次在场一次。
  - “战力”是 cards.md §11.1 定义的单位战力（current + aura），所以通过光环达到 8 也算。
  - “抽一张牌”本可写作 `do: draw`、`count: 1`、`side: self`。由于没有触发器就无法写出能力，它与触发器一起被省略。
    卡牌只保留数值。
- **缺口**：`on_power_reached`、`once_per_match`

### dr-shifter

- **状态**：unmapped · **判定**：lossy
- **校验者说明**：整个 `on_play` 能力都无法表达，卡牌只保留数值。没有把单位原地替换为新卡的动作。翻译者正确地
  放弃了 `banish` 加 `place_new_card`，因为 `place_new_card` 不能使用目标的行和位置。提议的
  `transform_in_place` 遵循所有者的约定（SKILL.md §2，本次请求中再次确认）：新兵归易形者的控制者，即行动方所有，
  站在敌方单位原来的位置、对手一侧，因此带有 `on_enemy_side`。触发器（`on_play`）和目标
  （`units: chosen`、`side: opponent`）可以表达，但能力需要动作，所以把它们一并省略是正确的。缺口已报告。
  草稿没有问题。
- **生成文本**：（空——能力未映射）
- **假设**：
  - “一个敌方单位”是行动方的选择，`units: chosen`、`side: opponent`，任意行。遵循 SKILL.md 中的示例读法：
    从不提供免疫单位，并遵守 `guarding`。
  - 适用所有者的约定：易形者变出的新兵归易形者的控制者（行动方）所有，站在敌方单位原来的位置、对手一侧。
  - `dr-recruit`（本卡组的衍生卡）是提议动作中指定的卡。由于整个能力未映射，草稿中还没有任何东西放置它。
    卡牌只保留数值。
- **缺口**：`transform_in_place`

### dr-captain

- **状态**：mapped · **判定**：faithful
- **校验者说明**：“构筑预算 +15”是 `provision_bonus: 15`。“主动能力，共 2 次”是 `activation: {charges: 2}`。
  领袖的次数保留整场对战，且从第一回合起就可用，所以不需要 `cooldown` 或 `ready_on_play`。“使一个友方单位获得 3 点增益”
  是 `on_activate` 的 `boost` 3，`units: chosen`、`side: self`。生成文本与设计一致：触发时机、目标、一侧、
  数值和次数。无需改动。
- **生成文本**：构筑预算增加15。主动能力（2次）：使一个友方单位获得3点增益。
- **假设**：
  - “构筑预算 +15”是 `provision_bonus: 15`。
  - “主动能力，共 2 次”是 `activation: {charges: 2}`。领袖的次数持续整场对战，且从第一回合起就可用（cards.md §5、§6.3），
    所以没有 `cooldown` 也没有 `ready_on_play`。
  - “一个友方单位”是 `units: chosen`、`side: self`，任意行。“获得 3 点增益”是 `do: boost`、`amount: 3`。

### dr-gambit

- **状态**：mapped · **判定**：faithful
- **校验者说明**：一张计策，`activation: {charges: 1}`，`on_activate` 为行动方抽 1 张牌。这正是设计所说的
  “使用一次：抽一张牌”。`charges: 1` 与计策的默认值相同，无害。设计没有给行，所以它从 `Rules.rows` 的第一行开始。
  无需改动。
- **生成文本**：主动能力（1次）：抽1张牌。
- **假设**：
  - “使用一次”写作 `activation: {charges: 1}`。这与计策默认的单次次数相同，两种写法生成的文本也相同。
    计策使用后被放逐（cards.md §3）。
  - “抽一张牌”是 `do: draw`、`count: 1`，为行动方（`side: self`）抽牌。
  - 设计没有给行，所以省略 `rows`，计策从 `Rules.rows` 的第一行开始。

### dr-scholar

- **状态**：unmapped · **判定**：lossy
- **校验者说明**：整个 `on_play` 能力都无法表达，卡牌只保留数值。`discard` 是唯一从手牌取卡的动作，它把卡送进墓地。
  没有把手牌移到牌库底部的动作，也没有向对手展示隐藏卡牌的动作。翻译者报告了这两个缺口：
  `hand_card_to_deck_bottom`，以及其上的展示参数（`reveal_to_opponent`）。这覆盖了设计的每个短语，包括
  “你的”手牌和牌库，以及先展示后移动的顺序。草稿没有问题。
- **生成文本**：（空——能力未映射）
- **假设**：
  - “你的手牌”和“你牌库”是行动方自己的手牌和牌库（`side: self`）。
  - “选择一张牌”是行动方从手牌中选择任意类型的一张牌（`pick: chosen`，无 `where` 过滤）。学者自身已经在场上，
    所以不是候选。
  - 展示和移动作用于同一张被选的卡，按这个顺序。两者都未映射，所以卡牌只保留数值。
- **缺口**：`hand_card_to_deck_bottom`、`reveal_to_opponent`
