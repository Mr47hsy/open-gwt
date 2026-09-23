# Glossary

Shared vocabulary. The zh/ru columns are the wording the translated docs should use, so that
`README.zh-CN.md` and `README.ru.md` stay consistent with each other.

## Game terms

Generic rules vocabulary only — see `04-legal.md` on why no official card, character or faction
names appear here.

| English | 简体中文 | Русский | Meaning |
| --- | --- | --- | --- |
| row | 行 / 战场行 | ряд | One of the two lines — melee and ranged — each player places cards on (ADR 0009) |
| melee row / ranged row | 近战行 / 远程行 | ближний ряд / дальний ряд | The two rows, in board order |
| row capacity | 行容量 | вместимость ряда | Most cards one player's row holds; nine by default |
| position / adjacent | 位置 / 相邻 | позиция / соседний | A card's place in its row, left to right, and the cards directly beside it |
| round | 局 | раунд | One scoring segment; a match is best-of-three |
| turn | 回合 | ход | One player's go within a round: activated abilities before and after one card, until the player ends it; or a pass instead of the card |
| end turn | 结束回合 | закончить ход | What a player does once their turn's card is played; a turn never ends by itself (intent `end_turn`) |
| tie | 平局 | ничья | A round with equal scores; by default it counts as won by both players |
| match | 对战 | матч | The whole game, up to three rounds |
| pass | pass / 停手 | пас | Stop playing for the round, keeping the rest of your hand |
| hand | 手牌 | рука | Cards you hold; carried across rounds |
| deck | 牌库 | колода | Cards left to draw from |
| draw | 抽牌 | добор | Taking a card from the deck |
| mulligan | 换牌 | мулиган | Returning cards from hand to the deck for others, a limited number of times at the start of each round |
| points / power | 点数 / 战力 | очки / сила | A unit's contribution to the row total |
| board | 战场 | поле | All rows for both players |
| provision cost / budget | 构筑费用 / 预算 | стоимость / бюджет | What a card costs at deck-building time, and the total a leader allows (ADR 0009) |
| base power / current power | 基础战力 / 当前战力 | базовая сила / текущая сила | The printed value (raised by base-power raises), and the value boosts raise and damage lowers; continuous effects add to it |
| boost / damage | 增益 / 伤害 | усиление / урон | Raise and lower a unit's current power; damage meets shields and armour first |
| armour | 护甲 | броня | Absorbs damage before power does |
| heal / reset | 治疗 / 重置 | исцеление / сброс | Bring a damaged unit back up to its base power / bring any unit back to its base power |
| boosted / damaged | 已增益 / 受伤 | усиленный / раненый | A unit whose current power is above / below its base power |
| hazard / boon | 有害行效果 / 有益行效果 | вредный / полезный эффект ряда | A row effect that damages / boosts; `clear_row_effect` can clear just one kind |
| guarding | 守护 | охрана | A status: the opponent cannot choose any other card on the guard's row |
| status-proof | 状态免疫 | защита от статусов | A status: no status can be added to the card |
| status | 状态 | статус | A marker on a unit that alters how rules apply to it, possibly with a timer |
| activated ability | 主动能力 | активируемая способность | An ability the player triggers during a turn, before or after its card; using it does not end the turn but commits it to a card (intent `use_order`) |
| charges / cooldown / ready | 次数 / 冷却 / 就绪 | заряды / перезарядка / готова | Uses an activated ability has left, turns before it can be used again, and whether it can be used now |
| timer | 计时 | таймер | Turns a status lasts; it ticks at its controller's turn end |
| bronze / gold | 铜卡 / 金卡 | бронзовая / золотая карта | Card colours that set the copy limit in a deck |
| unit / special / artifact | 单位 / 特殊牌 / 器物 | отряд / особая карта / артефакт | A card with power on a row; a card that acts once and goes to the graveyard; a card on a row without power |
| leader / leader ability | 领袖 / 领袖能力 | лидер / способность лидера | Not a card on the board: the provision bonus and the activated ability a deck is built around |
| stratagem | 计策 | стратагема | The card a deck brings for going first: only the round-one starter gets it, on the board for round one, used once (ADR 0011) |
| going first / starter | 先手 | первый ход / начинающий игрок | The player who starts a round; round one's starter is compensated with a redraw more and a stratagem |
| token | 衍生卡 | токен | A card created during a match, never in a deck; banished when it leaves the board |
| tag | 标签 | метка | A free-form original word on a card that other cards' effects refer to |
| graveyard / banish | 墓地 / 放逐 | кладбище / изгнание | Where destroyed cards go, and removal from the match entirely |
| owner / controller | 所有者 / 控制者 | владелец / контролирующий игрок | Whose deck a card came from, and whose side of the board it stands on |
| target / candidate | 目标 / 候选 | цель / кандидат | What an ability acts on, and what it may pick from |

## Project terms

| Term | 简体中文 | Русский | Meaning |
| --- | --- | --- | --- |
| rules core | 规则内核 | ядро правил | Engine-agnostic library holding all rules |
| engine-agnostic | 与引擎无关 | независимый от движка | No dependency on Unity or any engine |
| deterministic replay | 确定性回放 | детерминированный реплей | Seed + action log reproduces a match exactly |
| seed | 随机种子 | сид | PRNG seed a match carries |
| action log | 操作记录 | журнал действий | Ordered list of actions making up a match |
| server-authoritative | 服务端权威 | авторитарный сервер | Server decides outcomes; client only renders |
| intent | 操作意图 | намерение | What the client asks for; the server decides |
| hidden information | 隐藏信息 | скрытая информация | Hands, decks, upcoming draws |
| clean room | 净室实现 | чистая реализация | Built from public sources, never from official binaries |
| thin client | 瘦客户端 | тонкий клиент | Client that renders and sends intents but runs no rules |
| content pack | 内容包 | пакет контента | Compiled cards, decks and translations the server serves |
| card protocol | 卡牌协议 | протокол карт | The YAML format and closed vocabulary cards are written in |
| ability | 能力 | способность | A trigger plus an action on a card |
| row effect | 行效果 | эффект ряда | A persistent modifier on one row of one side; at most one per row-side |
| row-side | 一方的行 | ряд стороны | One row of one player — the unit row effects, capacity and positions apply to |
| continuous effect | 持续效果 | постоянный эффект | An effect in force while its card is on the board, never queued (`while_on_board`) |
| vocabulary word | 词汇 | слово словаря | A trigger, action, selector, status or row effect of the card protocol; an identifier, never displayed |
| acting player | 行动方 | действующий игрок | The player an ability's `self` and `opponent` are relative to, and who makes its choices |
| resolution queue | 结算队列 | очередь разрешения | First-in, first-out list of abilities waiting to resolve |
| pending choice | 待定选择 | ожидающий выбор | A pick the core asks one player for, from options it computed; nothing else happens until it is made |
| placeholder id | 占位 id | идентификатор-заглушка | Opaque card id used until a human writes an original name |

## Usage notes

- English is the source of truth for all documentation; zh and ru are translations of it.
- In Chinese text, keep **pass** in Latin script when it refers to the action — it is what players
  actually say — rather than translating it away.
- Do not invent alternative translations for terms already in this table; add a row instead.
