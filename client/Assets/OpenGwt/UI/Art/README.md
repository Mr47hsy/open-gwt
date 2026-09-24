# Art

Original vector art for the open-gwt client, drawn for this project from geometric primitives
(rectangles, circles, polygons, simple paths) and licensed under CC BY 4.0 like every original
asset here (`/LICENSE-ASSETS`). Nothing in this directory is traced from, modelled on or meant to
recall any official card, frame or icon.

| File | Used for |
| --- | --- |
| `card-frame.svg` | every card; white at low opacity over the card's USS background colour |
| `power-badge.svg` | a card's power and a row's total; USS tints the rim |
| `row-melee.svg`, `row-ranged.svg` | the two rows (`Rules.rows`): row heads, card headers, card watermarks, the preview |
| `kind-special.svg`, `kind-artifact.svg`, `kind-leader.svg`, `kind-stratagem.svg` | the card kinds that are not units: header icon and watermark |
| `status-*.svg` | one per status of `cards.md` §9, in card headers (with the timer beside it) and the preview |
| `badge-armor.svg` | a unit's armour, under the power badge |
| `order.svg` | an activated ability: the button on a card and the leader |

Icons are drawn in white so `-unity-background-image-tint-color` gives them any token colour.
`Editor/SvgImportSettings.cs` imports every SVG here as a UI Toolkit `VectorImage` with
antialiased arc tessellation — the built-in Vector Graphics module of Unity 6.3 and later, no
package — so they stay sharp at every panel scale. Keep new art in the same style: flat shapes,
no text, no gradients, no strokes thinner than 0.7 units at 24×24.
