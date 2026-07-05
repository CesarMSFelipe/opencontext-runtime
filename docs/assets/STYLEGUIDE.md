# OpenContext Graphite — README Style Guide

Rules for maintaining visual consistency. Every future edit should follow this system.

---

## Layout

- Main visual width: **720px** (all SVG images)
- Main card content width: **760px** (`<td width="760">`)
- Always wrap major sections in `<div align="center">` + centered card
- Separate sections with `###` Markdown headings; keep prose as plain Markdown, not wrapped in layout tables. Real TUI/CLI flows use the recorded `demo-*.gif` assets (see `scripts/render-readme-demos.sh`)

## Card Structure

Every text section must use this wrapper:

```html
<div align="center">

<table>
<tr>
<td width="760">

...content...

</td>
</tr>
</table>

</div>
```

Two-column cards (side by side):

```html
<div align="center">

<table>
<tr>
<td width="760">
<table>
<tr>
<td width="50%" valign="top">Left column</td>
<td width="50%" valign="top">Right column</td>
</tr>
</table>
</td>
</tr>
</table>

</div>
```

## Section Headers

- Use `<h3>Section Name</h3>` **inside** the `<td>` — not `##` headers outside cards
- `<h3>` in GitHub does not render with the bottom underline that `##` does
- Title Case for all section names

## Captions

All image captions use centered `<sub>`:

```html
<p align="center">
  <sub>Type · repo/context · task · result</sub>
</p>
```

Examples:
- `Benchmark · psf/requests · retry bug · 65% fewer tokens`
- `Runtime · deterministic pipeline · no LLM in retrieval path · offline`
- `Configuration · stack detection · editor setup · presets`

## Code Blocks

Label code blocks with bold text immediately above — no colon:

```
**Command**
\`\`\`bash
...
\`\`\`

**Output**
\`\`\`
...
\`\`\`
```

All code blocks must be inside a card — never floating in raw Markdown.

## Secondary Sections

These sections live inside `<details>` blocks to keep the landing page focused:

- Execution Harness
- Local Agent Memory
- Workflow Skills
- Runtime Configuration
- Runtime Commands

All five grouped in a single card at the bottom.

## Palette

| Token | Hex | Use | WCAG ratio on #0B0F14 |
|-------|-----|-----|----------------------|
| Background | `#0B0F14` | SVG/page background | — |
| Card | `#111821` | Card fill | — |
| Border subtle | `#21262D` | Dividers, card borders | — |
| Teal | `#2DC4A4` | Primary accent, success, improvement % | 7.8:1 ✓ |
| Blue | `#35ADE5` | Secondary accent, offline/KG highlights | 7.2:1 ✓ |
| Purple | `#8A6BBF` | Tertiary, call graph, test examples | 5.1:1 ✓ |
| Red | `#E8706A` | Danger, "before" numbers, failing | 5.4:1 ✓ |
| Amber | `#D4A840` | Warnings, quality gates, cost | 6.2:1 ✓ |
| Text | `#E6EDF3` | Primary text | 15.4:1 ✓ |
| Muted | `#9DA6B0` | Secondary text, descriptions | 6.8:1 ✓ |
| Very muted | `#606978` | Section labels, captions | 3.5:1 ✓ AA large |

> All ratios meet WCAG 2.1 AA (4.5:1 normal text, 3:1 large text ≥18px or bold ≥14px).
> Section labels use letter-spacing + uppercase which qualifies as large text.

### Tinted card fills (accent-colored dark cards)

| Accent | Fill |
|--------|------|
| Blue-tinted | `#0D1A28` |
| Teal-tinted | `#0D2220` |
| Purple-tinted | `#12101C` |
| Red-tinted | `#1E1010` |
| Amber-tinted | `#1E1600` |

### SVG asset rules

- **Never use SVGs for content that must be copyable** (commands, code, URLs) or clickable (links). Use HTML/Markdown cards instead.
- SVGs are for visual communication of structure, flow, and hierarchy — not for text-heavy content.

## SVG Assets

| File | Purpose | Dimensions |
|------|---------|-----------|
| `logo.svg` | Hero logo | 108×108 |
| `runtime-strip.svg` | Feature pills below title | 720×48 |
| `stats-bar.svg` | 4 key metric cards | 720×88 |
| `benchmark-numbers.svg` | Numbers summary table | 720×240 |
| `workflow-audience.svg` | 4-card audience grid | 720×210 |
| `pipeline.svg` | 8-step pipeline | 720×140 |
| `sdd-phases.svg` | 9-phase SDD workflow | 720×160 |
| `footer-mark.svg` | Footer logo + tagline | 720×64 |
