# OpenContext Graphite — README Style Guide

Rules for maintaining visual consistency. Every future edit should follow this system.

---

## Layout

- Main visual width: **720px** (all SVG images)
- Main card content width: **760px** (`<td width="760">`)
- Always wrap major sections in `<div align="center">` + centered card
- Separate all sections with `divider.svg` — never use Markdown `---`

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
- `Benchmark · psf/requests · retry bug · 62% fewer tokens`
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

| Token | Hex | Use |
|-------|-----|-----|
| Background | `#0B0F14` | SVG/page background |
| Card | `#111821` | Card fill |
| Border subtle | `#21262D` | Dividers, card borders |
| Teal | `#00C9A7` | Primary accent, success, improvement % |
| Blue | `#00A8E8` | Secondary accent, monospace highlights |
| Purple | `#845EC2` | Tertiary, call graph, test examples |
| Red | `#FF7B72` | Danger, "before" numbers |
| Amber | `#E3B341` | Warnings, $$ cost indicators |
| Text | `#E6EDF3` | Primary text |
| Muted | `#8B949E` | Secondary text |
| Very muted | `#3D4450` | Labels, captions, subtitles |

## SVG Assets

| File | Purpose | Dimensions |
|------|---------|-----------|
| `logo.svg` | Hero logo | 108×108 |
| `runtime-strip.svg` | Feature pills below title | 720×48 |
| `demo-terminal.svg` | Hero terminal demo | 720×360 |
| `before-after.svg` | Side-by-side comparison | 720×240 |
| `stats-bar.svg` | 4 key metric cards | 720×88 |
| `benchmark-card-requests.svg` | requests benchmark | 720×380 |
| `benchmark-card-fastapi.svg` | fastapi benchmark | 720×380 |
| `benchmark-numbers.svg` | Numbers summary table | 720×240 |
| `workflow-audience.svg` | 4-card audience grid | 720×210 |
| `pipeline.svg` | 8-step pipeline | 720×140 |
| `sdd-phases.svg` | 9-phase SDD workflow | 720×160 |
| `per-phase-models.svg` | Model routing table | 720×200 |
| `wizard-flow.svg` | install wizard terminal | 720×400 |
| `presets.svg` | preset list terminal | 720×290 |
| `footer-mark.svg` | Footer logo + tagline | 720×64 |
| `divider.svg` | Section separator | 720×24 |
