# Design System: autonomous_trading_ai Operator UI

## 1. Visual Theme & Atmosphere

This UI is not a retail trading dashboard and should never feel like one. It is a calm operator surface for a live autonomous trading system: observability-first, read-only, low-noise, and slightly premium without becoming glossy or theatrical.

The overall mood should sit between:
- Linear's dark precision and surface discipline
- IBM's structured, legible enterprise clarity
- Revolut's refined fintech calm

But the final result must be specific to this product:
- less marketing sheen
- less neon trading cliché
- more runtime awareness
- more diagnosis density
- more quiet confidence

The interface should feel like a control room designed for a technically literate operator who wants fast answers, not stimulation. Information should surface in a deliberate luminance hierarchy. The UI should reward scanning: a user should be able to understand health, freshness, and anomaly state in a few seconds.

**Core character:**
- dark-mode-native
- operator-grade
- restrained premium
- information-dense but breathable
- cool-toned and unsentimental
- trustworthy, not flashy

**Emotional target:**
"The system is legible. I know what state it is in. I know where to look next."

**Key characteristics:**
- dark canvas with cool blue-steel neutrals
- restrained blue accent instead of green/red overload
- semantic severity colors used only where meaning exists
- typography-led hierarchy
- compact cards with strong scanning rhythm
- minimal decorative gradients, used only sparingly for atmosphere
- no casino aesthetics, no glow-heavy crypto UI, no fake cockpit theatrics

---

## 2. Color Palette & Roles

### Background Surfaces
- **Void Background** (`#0A0D12`): deepest page background; cool near-black with faint blue bias
- **Panel Background** (`#11161D`): default shell/sidebar/page section background
- **Surface Base** (`#151C24`): standard cards and grouped panels
- **Surface Raised** (`#1A2330`): elevated cards, active containers, focused regions
- **Surface Hover** (`#223041`): hover/active affordance on dark surfaces

### Text & Content
- **Primary Text** (`#E8EEF5`): main text; crisp but not pure white
- **Secondary Text** (`#B4C0CC`): supporting body text, descriptions, table meta
- **Muted Text** (`#8090A3`): tertiary information, quiet labels, timestamps
- **Faint Text** (`#607081`): disabled or deeply de-emphasized text

### Brand / Accent
- **Signal Blue** (`#4C8BF5`): primary accent for focus, links, selected states, key interactive surfaces
- **Signal Blue Hover** (`#68A1FF`): hover/active accent variant
- **Signal Blue Dim** (`#2D5FA8`): subtle accent fills and borders

### Severity / Status
Use status colors only for real meaning, never for decoration.

- **Info** (`#4C8BF5`): informational state, active navigation, selected controls
- **Success** (`#2FBF71`): healthy/nominal/connected state
- **Warning** (`#E6A93D`): stale data, missing non-critical artifacts, lock states, degraded conditions
- **Critical** (`#E25D5D`): backend unreachable, failed fetch, broken runtime dependency, severe anomaly
- **Neutral Status** (`#8FA3B8`): present but not especially notable

### Borders & Dividers
- **Border Subtle** (`rgba(210, 225, 241, 0.06)`): default low-noise border
- **Border Standard** (`rgba(210, 225, 241, 0.10)`): card, input, table boundaries
- **Border Strong** (`rgba(210, 225, 241, 0.16)`): selected or emphasized boundaries
- **Hairline Divider** (`rgba(210, 225, 241, 0.05)`): section separators

### Overlays / Effects
- **Overlay Backdrop** (`rgba(7, 10, 14, 0.72)`): modal/drawer backdrop
- **Ambient Tint** (`rgba(76, 139, 245, 0.08)`): faint accent wash for premium depth, used sparingly

### Light Theme Guidance
If light mode is supported, it should preserve the same hierarchy and restraint rather than becoming bright consumer fintech.

- **Light Background** (`#F4F7FA`)
- **Light Surface** (`#FFFFFF`)
- **Light Surface Alt** (`#ECF1F6`)
- **Light Text** (`#14202B`)
- **Light Muted** (`#5E7184`)
- **Light Border** (`rgba(20, 32, 43, 0.10)`)

---

## 3. Typography Rules

### Font Family
Use a typography pairing that feels technical, modern, and premium without becoming trendy.

- **Primary Sans**: `Inter Variable`, `SF Pro Display`, `Segoe UI`, `system-ui`, `sans-serif`
- **Monospace**: `JetBrains Mono`, `Berkeley Mono`, `SF Mono`, `Consolas`, `ui-monospace`, `monospace`

If custom font expansion happens later, prefer something crisp and engineered — not playful, rounded, or overly fashionable.

### Hierarchy

| Role | Font | Size | Weight | Line Height | Letter Spacing | Notes |
|------|------|------|--------|-------------|----------------|-------|
| Display | Sans | 40px | 650 | 1.05 | -0.04em | Landing/hero-scale route titles only |
| Page Title | Sans | 30px | 620 | 1.10 | -0.03em | Primary route heading |
| Section Title | Sans | 22px | 600 | 1.20 | -0.02em | Major section/canvas titles |
| Card Title | Sans | 16px | 600 | 1.30 | -0.01em | Card headers |
| Emphasis Body | Sans | 15px | 560 | 1.45 | 0 | Important inline values |
| Body | Sans | 14px | 420 | 1.50 | 0 | Default UI text |
| Small Body | Sans | 13px | 420 | 1.45 | 0 | Secondary text |
| Label | Sans | 12px | 540 | 1.35 | 0.02em | Eyebrows, labels, status text |
| Micro | Sans | 11px | 520 | 1.30 | 0.03em | Tiny metadata |
| Mono Body | Mono | 12px | 450 | 1.45 | 0 | Raw values, payload snippets, IDs |
| Mono Small | Mono | 11px | 450 | 1.35 | 0 | Dense technical annotations |

### Typography Principles
- Titles should feel compact and engineered, not editorial or dramatic.
- Most UI text should live in the 12–16px range.
- The default reading size for dense operator UI should be 13–14px.
- Monospace should be used selectively for IDs, timestamps, payload fragments, and strategy-like technical details.
- Avoid excessive font-weight variety; keep the system disciplined.
- Do not use huge type unless it genuinely helps hierarchy.

---

## 4. Component Stylings

### Buttons

**Primary Button**
- Background: `#4C8BF5`
- Text: `#F7FBFF`
- Radius: 10px
- Border: none or `1px solid rgba(255,255,255,0.06)` if needed
- Hover: brighter blue shift + slightly raised surface impression
- Use: refresh, key navigation actions, primary route actions

**Secondary Button**
- Background: `#1A2330`
- Text: `#D6E0EA`
- Border: `1px solid rgba(210, 225, 241, 0.10)`
- Radius: 10px
- Use: secondary actions, utility controls

**Ghost Button**
- Background: transparent
- Text: `#B4C0CC`
- Border: `1px solid rgba(210, 225, 241, 0.08)`
- Hover: subtle surface fill `rgba(255,255,255,0.03)`
- Use: low-emphasis actions in dense panels

**Toolbar / Micro Button**
- Height should be compact but still clickable
- Font: 12px weight 540
- Radius: 8px
- Use for table controls, filters, timeframe toggles, refresh scopes

### Cards & Panels
Cards should communicate structured intelligence, not marketing modularity.

- Background: `#151C24`
- Border: `1px solid rgba(210, 225, 241, 0.08)`
- Radius: 14px
- Padding: generous enough for readability, compact enough for dense layouts
- Use slightly brighter top borders or inset highlights very sparingly
- Hover should be subtle; this is not a gallery UI

**Card types:**
- summary card
- diagnostic card
- timeline row container
- dense metric card
- strategy detail card

### Status Badges
Badges are critical to this UI and should feel intentional.

**Badge rules:**
- rounded-pill or soft rounded rectangle
- compact, highly legible
- no saturated backgrounds unless semantic severity requires it
- severity should be readable even without color through label wording

**Styles:**
- neutral badge: muted slate fill
- info badge: dim blue fill/border
- success badge: dim green fill/border
- warning badge: amber-tinted fill/border
- critical badge: red-tinted fill/border

### Inputs / Filters / Search
- Background: `#11161D` or `#151C24`
- Border: `1px solid rgba(210,225,241,0.10)`
- Text: `#E8EEF5`
- Placeholder: `#8090A3`
- Radius: 10px
- Focus ring: soft blue outer glow + stronger border

### Tables / Dense Lists
If tables are used, they should feel crisp and quiet.

- no heavy gridlines
- use row separators or alternating surface shifts very subtly
- prioritize scanability of first 3 columns
- numeric columns should align cleanly
- status or anomaly columns should be visible early

### Navigation
Navigation should feel stable and technical.

- dark shell with subtle separation from content area
- active route indicated by surface shift + accent line or glow restraint
- labels should be medium-weight, concise, and low-noise
- theme toggle, refresh, and critical utility actions should feel native to the shell

---

## 5. Layout Principles

### Spacing System
Use a disciplined 4px/8px-derived spacing system.

Recommended scale:
- 4px
- 8px
- 12px
- 16px
- 20px
- 24px
- 32px
- 40px

### Layout Philosophy
- Prioritize scanning over spectacle.
- Favor dashboard compositions that answer questions fast.
- Above-the-fold should reveal system state quickly.
- Group related diagnostics tightly.
- Use whitespace as a control mechanism, not as decoration.

### Grid & Containers
- Use responsive content containers with strong max-width discipline.
- Default pages should support multi-column desktop layouts.
- Summary information should sit above drill-down information.
- Avoid layouts that force excessive vertical scrolling before key state is visible.

### Density Rules
- Dense != cramped
- Every panel should justify its space with utility.
- Repeated metadata should collapse or align, not scatter.
- Operator workflows matter more than card symmetry.

---

## 6. Depth & Elevation

Depth should be built through subtle surface stepping, not flashy shadows.

| Level | Treatment | Use |
|------|-----------|-----|
| Level 0 | `#0A0D12` background | page canvas |
| Level 1 | `#11161D` shell / section surface | sidebar, route shell |
| Level 2 | `#151C24` card surface + subtle border | default cards |
| Level 3 | `#1A2330` raised surface + stronger border | active/important regions |
| Level 4 | soft shadow + overlay + brighter border | dropdowns, dialogs, overlays |

**Shadow approach:**
- subtle black shadow stacks only
- combine with border contrast, not instead of it
- avoid giant blurred glows
- blue glow only for focus/selection moments

---

## 7. Do's and Don'ts

### Do
- Design for operator trust and clarity.
- Make stale, missing, and degraded states legible.
- Use semantic color only when it means something.
- Prefer compact, structured status summaries.
- Keep cards useful and information-rich.
- Use contrast carefully so important signals pop quickly.
- Make route hierarchy obvious.
- Preserve a premium, calm, technical tone.

### Don't
- Don't imitate retail trading dashboards with neon green/red overload.
- Don't add fake charts or decorative visual noise just to fill space.
- Don't use glowing gradients as a substitute for hierarchy.
- Don't hide important state behind tabs if it should be obvious immediately.
- Don't make every card equally loud.
- Don't use excessive animations, pulsing alerts, or gamified cues.
- Don't add execution controls or high-risk action surfaces without explicit approval.
- Don't let the UI feel like crypto casino software.

---

## 8. Responsive Behavior

### Breakpoints
| Name | Width | Notes |
|------|-------|-------|
| Mobile | <640px | minimal support, stacked layout |
| Tablet | 640–960px | compressed 2-column possibilities |
| Desktop | 960–1280px | standard operator layout |
| Wide | >1280px | denser multi-panel layout |

### Responsive Rules
- On smaller screens, preserve hierarchy before density.
- Collapse secondary panels below critical summaries.
- Keep status strips and top-level health visible early.
- Avoid horizontal scroll for primary operator pages when possible.
- Tables may simplify into stacked cards if necessary.

### Touch / Input Targets
- Buttons and filters should remain comfortably clickable.
- Dense UI is acceptable, but not if controls become fiddly.

---

## 9. Agent Prompt Guide

### Quick Design Summary
When generating UI for this project, aim for:
- dark operator dashboard
- cool blue-steel palette
- low-noise premium control-room aesthetic
- Linear/IBM/Revolut discipline, but customized for trading-system observability
- read-only runtime diagnosis first, visual polish second

### Preferred UI Traits
- compact status bars
- elegant severity badges
- structured diagnostic cards
- clean data tables / lists
- quiet premium surfaces
- obvious freshness / staleness cues
- route layouts optimized for fast scanning

### Example Prompt Fragments
- "Design this page as a dark, operator-grade dashboard with restrained premium styling, cool blue-steel surfaces, subtle borders, and strong data hierarchy. Avoid neon trading clichés."
- "Use compact metric cards with clear status semantics, readable timestamps, and explicit stale/offline/error states."
- "Make the page feel like a calm control room for a live autonomous system, not a speculative retail trading app."
- "Prioritize observability, diagnosis, and runtime legibility over decorative visuals."

### Route-Specific Guidance
- **Overview**: immediate state comprehension, top-level health strip, compact summaries
- **Execution**: anomaly visibility, open-trade context, lock-state clarity, recent operational signals
- **Pool**: structured distribution and ranking visibility
- **Manifest**: runtime artifact legibility, slot clarity, availability status
- **Audit**: scannable timeline, source differentiation, expandable detail without clutter

---

## 10. Project-Specific Design Guardrails

- This is a read-only operator UI unless explicitly expanded later.
- The primary user is technically literate and wants fast state comprehension.
- The UI should help explain no-trade and degraded-runtime states.
- The design system must support all three roadmap phases:
  - Phase 1: reliability and state legibility
  - Phase 2: deeper diagnosis and drill-down
  - Phase 3: polish, density, and product quality

If a design choice improves beauty but hurts operational clarity, reject it.
If a design choice improves clarity without making the UI ugly or noisy, prefer it.
