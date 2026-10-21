# Design spec: B · Clean eco

_Chosen by Lystiger. Reason: Better should the logo and products_

Design output only. Product code is built by BUILDER from this spec.

## Tokens

| Token | Value |
| --- | --- |
| bg | `#f6faf6` |
| surface | `#ffffff` |
| text | `#14201a` |
| muted | `#4f6158` |
| primary | `#1d6b36` |
| on-primary | `#ffffff` |
| accent | `#7fbf3f` |
| radius | `6px` |
| gap | `24px` |
| font | `system-ui, -apple-system, "Segoe UI", sans-serif` |

## Contrast (computed)

| Pair | Ratio | WCAG AA text |
| --- | --- | --- |
| text on background | 15.92 : 1 | passes AA |
| button text on primary | 6.54 : 1 | passes AA |
| muted text on background | 6.26 : 1 | passes AA |

## Components and states

- **Primary button:** default, hover, focus (visible ring), disabled (45% opacity). Text in `--on-primary`.
- **Secondary button:** outline in `--primary`, same states.
- **Product card:** surface, `--radius`, pack image on a neutral ground, name, meta, Add to quotation.
- **Form field:** default, focus, error (border in the error colour, message below), disabled.
- **Basket drawer:** list of lines, quantity, unit, remove; empty state; send button.

## Layout and motion

- Spacing gap: `--gap`. Radius: `--radius`.
- Entry transitions 260 ms, hover 160 ms, standard easing. No looping animation (reduced motion turns off transitions).
- Touch targets at least 44 px on phone width.

## Copy

Use the English and Vietnamese strings in `designs/unigreen/build.py`. Vietnamese must hold on phone width.

## Diagrams

See `designs/unigreen/diagrams/README.md` for the sitemap, flows, sequence, status lifecycle and database.
