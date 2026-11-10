# Frontend UI Design System — "The Verified Instrument"

Every frontend change or UI component in `frontend/` MUST strictly adhere to **The Verified Instrument** design system.
**Core Rule**: Never alter UX, state management, event handlers, props, or API contracts when performing visual updates unless explicitly requested.

## 1. Aesthetic Direction & Surface Hierarchy (Dark-First Precision Workbench)

The interface is modeled after high-precision hardware test benches (RTINGS, PCPartPicker, Linear, Vercel): dark obsidian surfaces, hairline `#1E2836` borders, zero decorative neon glows, and strict tabular data alignment.

```css
:root {
  /* Surface Hierarchy */
  --bg-app: #0A0E13;          /* Level 0: App Canvas */
  --bg-surface: #10161D;      /* Level 1: Cards, Filter Bar, Panels */
  --bg-raised: #151D27;       /* Level 2: Hover States, Inner Sub-cards, Spec Cells */
  --bg-overlay: #1A2431;      /* Level 3: Modal Headers/Footers, Sticky Bars */
  --bg-input: #0D131A;        /* Recessed Wells: Inputs, Search, Slider Tracks */

  /* Borders & Hairlines */
  --border-subtle: #1E2836;   /* Default 1px structural hairline */
  --border-strong: #2B394C;   /* Hover / interactive card border */

  /* Text Hierarchy */
  --text-primary: #E8ECF1;    /* Primary headings, values, titles */
  --text-secondary: #A6B0BE;  /* Body copy, spec descriptions, pros/cons text */
  --text-muted: #7C8898;      /* Uppercase micro-labels, MPNs, timestamps */
  --text-inverse: #0A0E13;    /* Dark text on solid Cairo Gold CTAs */

  /* Semantic Accents (Strict 1-Job-Per-Color Discipline) */
  --gold: #E9B949;            /* Cairo Gold: Money, TOPSIS Match %, Primary CTA, Active Persona */
  --gold-bright: #F5C95C;     /* Hover Gold & Score Numerals >= 85 */
  --gold-dim: rgba(233, 185, 73, 0.12);
  --gold-ring: rgba(233, 185, 73, 0.25);

  --cyan: #22D3EE;            /* Telemetry Cyan: 1-100 Score Bars, Metric Sliders, Spec Icons/Dots */
  --cyan-dim: rgba(34, 211, 238, 0.12);

  --indigo: #818CF8;          /* Signal Indigo: AI/TOPSIS/NLP provenance badges ONLY */
  --indigo-dim: rgba(129, 140, 248, 0.12);

  --success: #34D399;         /* Emerald: Live/Verified status, Best Price outline, Pros (+) */
  --success-dim: rgba(52, 211, 153, 0.08);
  --danger: #F87171;          /* Rose: Cons (-), Errors, Out of Stock, Score Numerals < 50 */
  --danger-dim: rgba(248, 113, 113, 0.08);
  --warning: #FBBF24;         /* Amber: Stale cache / low stock warnings */

  /* Hardware Tier Keys (2px Left Border & Icon Wells Only) */
  --tier-thermal: #F59E0B;
  --tier-display: #22D3EE;
  --tier-mobility: #34D399;
  --tier-expansion: #A78BFA;

  /* Studio Lightbox Well (The ONLY Light Surface) */
  --studio-well: #EDEBE6;     /* Warm studio grey for 4:3 product photography */

  /* Typography */
  --font-display: "Space Grotesk", "Inter", system-ui, sans-serif;
  --font-ui: "Inter", system-ui, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, monospace;
  --font-arabic: "IBM Plex Sans Arabic", "Inter", system-ui, sans-serif;

  /* Shadows */
  --shadow-1: 0 1px 2px rgba(0, 0, 0, 0.40);
  --shadow-2: 0 4px 16px rgba(0, 0, 0, 0.45);
}
```

## 2. Strict 4-Rule Color Discipline (Zero Rainbow Fatigue)

1. **Cairo Gold (`#E9B949` / `#F5C95C`) = Money & Decisions ONLY**:
   - Used exclusively for: Primary CTA buttons (`#E9B949` fill with `#0A0E13` text), EGP prices, TOPSIS Match `%` badge, Rank `#1` chip, active persona selection border, active view-switcher segment, and the Budget EGP slider.
   - **One Gold Focal Rule**: Never allow more than one solid gold fill element per card.
2. **Telemetry Cyan (`#22D3EE`) = Hardware Data & Benchmarks ONLY**:
   - Used exclusively for: `1–100` score bar fills, minimum metric gate sliders, spec bullet dots, and persona icon wells.
   - Never use Cyan on buttons, links, or prices.
3. **Signal Indigo (`#818CF8`) = Machine Intelligence Provenance ONLY**:
   - Used exclusively on small tags/badges indicating `TOPSIS`, `AI Review Synthesis`, or `NLP` evidence counts. Never use for buttons or layout backgrounds.
4. **Emerald (`#34D399`) & Rose (`#F87171`) = Verification & Judgement ONLY**:
   - Used exclusively for: Verified Live status dot, `BEST PRICE` outline chip, Pros (`+`) vs. Cons (`-`), and low score numerals (`< 50`).

## 3. Typography & Bilingual Rules

- **Display & Numerals (`--font-display: Space Grotesk`)**: Used for page titles, laptop model names, EGP prices, TOPSIS match `%`, and score numerals. Always apply `font-variant-numeric: tabular-nums` on every price, score, percentage, and metric counter.
- **UI & Specs (`--font-ui: Inter`)**: Used for controls, spec lists, and English descriptions.
- **Technical Metadata (`--font-mono: IBM Plex Mono`)**: Used for Manufacturer Part Numbers (MPNs), `#rank` badges, timestamps (`14m ago`), and hardware dimension codes.
- **Arabic Copy (`--font-arabic: IBM Plex Sans Arabic`)**: Used for Arabic review synthesis and RTL text (`dir="auto"`, `line-height: 1.65`, `letter-spacing: 0`). Always keep numerals in Western Arabic digits (`0–9`) with `tabular-nums`.

## 4. Signature Component Rules

- **Studio Lightbox Well (`--studio-well: #EDEBE6`)**: Every laptop product image sits inside a `4:3` rounded container (`border-radius: 8px`, `background: #EDEBE6`, `padding: 12px`, `object-fit: contain`) with a subtle inner border `inset 0 0 0 1px rgba(10,14,19,0.08)` so white-background store photos look like intentional studio photography instead of floating stickers.
- **Score Bars**: Uniform `6px` height, `--border-subtle` track, `100%` `--cyan` fill (`linear-gradient(90deg, rgba(34,211,238,0.75), #22D3EE)`), with hairline vertical tick marks at `50%` and `80%`. Score numerals next to the bar reflect thresholds:
  - `>= 85`: `--gold-bright` (`#F5C95C`)
  - `50–84`: `--text-primary` (`#E8ECF1`)
  - `< 50`: `--danger` (`#F87171`)
- **Hardware Tier Cards**: In the detail modal, the 4 hardware tier cards (Thermal, Display, Mobility, Expansion) use `--bg-raised` with a `2px solid` left accent border in their respective `--tier-*` color.
- **Forbidden Anti-Patterns**:
  - No multi-stop neon/purple-to-pink gradients or glowing drop shadows.
  - No circular SVG gauge charts (use horizontal ticked telemetry bars).
  - No pure `#000000` backgrounds or pure `#FFFFFF` text.
  - No `backdrop-filter: blur()` on scrolling card grids (reserve for modal backdrop only).

## 5. Component Class & Layout Reference (from Visual Style Tile)

- **Buttons**:
  - `.btn-primary`: `background: var(--gold); color: var(--text-inverse); height: 44px; padding: 0 20px; border-radius: 10px; font-weight: 600;` (`:hover { background: var(--gold-bright); }`)
  - `.btn-secondary`: `background: transparent; border: 1px solid var(--border-strong); color: var(--text-primary);` (`:hover { border-color: var(--gold); background: var(--gold-dim); }`)
  - `.btn-ghost`: `background: transparent; color: var(--text-secondary); height: 36px; padding: 0 12px; border-radius: 8px;` (`:hover { color: var(--text-primary); background: var(--bg-raised); }`)
- **Chips & Badges**:
  - `.rank-chip`: `font-family: var(--font-mono); font-weight: 600; font-size: 12px; color: var(--text-secondary); border: 1px solid var(--border-strong); border-radius: 6px; padding: 4px 8px;`
  - `.brand-chip`: `background: var(--bg-raised); border: 1px solid var(--border-subtle); border-radius: 6px; padding: 4px 8px; font-size: 11px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--text-secondary);`
  - `.mpn-chip`: `font-family: var(--font-mono); font-weight: 500; font-size: 12px; color: var(--text-muted); border: 1px solid var(--border-subtle); border-radius: 6px; padding: 4px 8px;`
  - `.topsis-badge`: `background: var(--gold); color: var(--text-inverse); border-radius: 8px; padding: 6px 12px;` (`.pct`: `Space Grotesk 700 17px`; `.lbl`: `9.5px uppercase`)
  - `.best-chip`: `border: 1px solid rgba(52, 211, 153, .5); color: var(--success); border-radius: 6px; padding: 3px 8px; font-size: 11px; font-weight: 600; text-transform: uppercase;` with a `6px` `--success` dot.
  - `.ai-chip`: `background: var(--indigo-dim); color: var(--indigo); border-radius: 6px; padding: 4px 8px; font-size: 11px; font-weight: 600; text-transform: uppercase;`
- **Segmented Controls (`.seg`)**:
  - Container: `background: var(--bg-input); border: 1px solid var(--border-subtle); border-radius: 10px; padding: 3px; gap: 4px;`
  - Selected button (`aria-pressed="true"`): `background: var(--bg-raised); color: var(--gold-bright); border-color: rgba(233, 185, 73, .4); font-weight: 600;` (never a solid gold fill).
- **Persona Cards (`.persona`)**:
  - Default: `background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 12px; padding: 16px;` with `40x40px` icon well (`background: var(--cyan-dim); color: var(--cyan); border-radius: 10px;`).
  - Selected (`aria-pressed="true"`): `border: 1.5px solid var(--gold); box-shadow: 0 0 0 3px var(--gold-ring); background: linear-gradient(0deg, var(--gold-dim), var(--gold-dim)), var(--bg-surface);` with `.ptitle { color: var(--gold-bright); }` and a `20x20px` gold check badge in the top-right corner.
- **Sliders (`input[type="range"]`)**:
  - Budget slider uses `--accent: var(--gold)` and a `.budget-input` readout (`background: var(--bg-input); border: 1px solid var(--border-subtle); border-radius: 10px; padding: 8px 14px;` with `.amt` in `Space Grotesk 600 20px var(--gold-bright)`).
  - Criteria/metric sliders use `--accent: var(--cyan)` and display an `.any-chip` (`border: 1px solid var(--border-subtle); border-radius: 999px; padding: 4px 10px; font-size: 12px; color: var(--text-muted);`) when at `0`.
- **Result Card & Detail Modal Fragments**:
  - `.studio-well`: `background: var(--studio-well); border-radius: 12px; border: 1px solid rgba(255, 255, 255, .08); aspect-ratio: 4/3; padding: 12px;` with `img { object-fit: contain; }`.
  - `.spec-bullets`: `background: var(--bg-raised); border: 1px solid var(--border-subtle); border-radius: 10px; padding: 12px 14px;` with `6x6px` square `--cyan` bullets.
  - `.pc.pros` / `.pc.cons`: `border: 1px solid var(--border-subtle); border-radius: 10px; padding: 14px 16px;` with `--success-dim` / `--danger-dim` backgrounds and `✓` / `✕` markers.
  - `.crit-tile`: `background: var(--bg-raised); border: 1px solid var(--border-subtle); border-radius: 10px; padding: 12px;` with threshold-colored `.cnum` (`>= 85` `--gold-bright`, `50–84` `--text-primary`, `< 50` `--danger`) and a `4px` `--cyan` mini bar.
  - `.tier`: `background: var(--bg-raised); border: 1px solid var(--border-subtle); border-left: 2px solid var(--key); border-radius: 12px; padding: 16px;` where `--key` is `--tier-thermal` (`#F59E0B`), `--tier-display` (`#22D3EE`), `--tier-mobility` (`#34D399`), or `--tier-expansion` (`#A78BFA`).
  - `.spec-cell`: `background: var(--bg-raised); border: 1px solid var(--border-subtle); border-radius: 12px; padding: 16px;` with `--cyan` header icon, mono `.cbadge`, `Space Grotesk 600 17px` `.big` headline, and 2-column `.spec-fields` (`--indigo` for AI TOPS values).
