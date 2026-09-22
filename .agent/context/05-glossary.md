# Glossary

Shared vocabulary. The zh/ru columns are the wording the translated docs should use, so that
`README.zh-CN.md` and `README.ru.md` stay consistent with each other.

## Game terms

Generic rules vocabulary only — see `04-legal.md` on why no official card, character or faction
names appear here.

| English | 简体中文 | Русский | Meaning |
| --- | --- | --- | --- |
| row | 行 / 战场行 | ряд | One of the three lines units are placed on |
| round | 局 | раунд | One scoring segment; a match is best-of-three |
| match | 对战 | матч | The whole game, up to three rounds |
| pass | pass / 停手 | пас | Stop playing for the round, keeping the rest of your hand |
| hand | 手牌 | рука | Cards you hold; carried across rounds |
| deck | 牌库 | колода | Cards left to draw from |
| draw | 抽牌 | добор | Taking a card from the deck |
| mulligan | 换牌 | мулиган | Replacing cards before a round |
| points / power | 点数 / 战力 | очки / сила | A unit's contribution to the row total |
| board | 战场 | поле | All rows for both players |

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
| row effect | 行效果 | эффект ряда | A persistent modifier on one row of one side |
| placeholder id | 占位 id | идентификатор-заглушка | Opaque card id used until a human writes an original name |

## Usage notes

- English is the source of truth for all documentation; zh and ru are translations of it.
- In Chinese text, keep **pass** in Latin script when it refers to the action — it is what players
  actually say — rather than translating it away.
- Do not invent alternative translations for terms already in this table; add a row instead.
