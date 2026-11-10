---
name: Executive Pulse & Telemetry
colors:
  surface: '#0f131c'
  surface-dim: '#0f131c'
  surface-bright: '#353942'
  surface-container-lowest: '#0a0e16'
  surface-container-low: '#181c24'
  surface-container: '#1c2028'
  surface-container-high: '#262a33'
  surface-container-highest: '#31353e'
  on-surface: '#dfe2ee'
  on-surface-variant: '#bacac1'
  inverse-surface: '#dfe2ee'
  inverse-on-surface: '#2c3039'
  outline: '#85948c'
  outline-variant: '#3c4a43'
  surface-tint: '#2fe0aa'
  primary: '#44edb7'
  on-primary: '#003828'
  primary-container: '#00d09c'
  on-primary-container: '#00533c'
  inverse-primary: '#006c4f'
  secondary: '#7bd0ff'
  on-secondary: '#00354a'
  secondary-container: '#00a6e0'
  on-secondary-container: '#00374d'
  tertiary: '#cdd0ff'
  on-tertiary: '#131e8c'
  tertiary-container: '#abb2ff'
  on-tertiary-container: '#313ca4'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#59fdc5'
  primary-fixed-dim: '#2fe0aa'
  on-primary-fixed: '#002116'
  on-primary-fixed-variant: '#00513b'
  secondary-fixed: '#c4e7ff'
  secondary-fixed-dim: '#7bd0ff'
  on-secondary-fixed: '#001e2c'
  on-secondary-fixed-variant: '#004c69'
  tertiary-fixed: '#e0e0ff'
  tertiary-fixed-dim: '#bdc2ff'
  on-tertiary-fixed: '#000767'
  on-tertiary-fixed-variant: '#2f3aa3'
  background: '#0f131c'
  on-background: '#dfe2ee'
  surface-variant: '#31353e'
typography:
  display-hero:
    fontFamily: Plus Jakarta Sans
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
    letterSpacing: -0.03em
  display-hero-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 28px
    fontWeight: '700'
    lineHeight: 36px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.015em
  headline-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 22px
    letterSpacing: -0.005em
  body-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
    letterSpacing: 0em
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0.005em
  metric-xl:
    fontFamily: JetBrains Mono
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 36px
    letterSpacing: -0.03em
  metric-lg:
    fontFamily: JetBrains Mono
    fontSize: 22px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.02em
  metric-sm:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0em
  label-caps:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.08em
  telemetry-code:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0.02em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-desktop: 1.25rem
  margin: 1rem
  margin-desktop: 2rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.5rem
---

## Brand & Style

This design system establishes an ultra-refined, high-density executive command center tailored for weekly review cadences, sentiment intelligence, and live platform telemetry. It fuses the structured engineering precision of Linear, the optical clarity of Vercel, and the high-performance emerald energy native to financial technology.

### Target Audience & Psychological Posture
Engineered for C-suite operators, VP of Product leads, and quantitative product managers who require instantaneous anomaly detection, sentiment trend comprehension, and operational review telemetry without cognitive drag. The interface projects high agency, razor-sharp technical discipline, absolute stability, and continuous algorithmic pulse.

### Design Aesthetic: Precision Dark Glassmorphism
The aesthetic relies on deep oceanic obsidians, subtle hairline inner specular borders, deliberate neon focal nodes, and multi-tier surface elevations:
- **Atmospheric Depth:** Surface depth is communicated via layered dark zinc-slate tints combined with micro-diffused emerald and indigo ambient backdrops.
- **Specular Hairlines:** Interactive and structural containers utilize single-pixel white translucent boundaries rather than flat opaque strokes.
- **Data-Dense Micro-Typography:** High information density achieved via tabular monospaced numbers, compact label caps, and scannable visual anchors.

## Colors

The palette is constructed around a dark-first canvas optimized for long-duration executive sessions, dense telemetry screens, and high-contrast analytical charting.

### Core Architecture
- **Canvas Base (`#0B0F17`):** The foundational obsidian canvas layer.
- **Elevated Card / Tier 1 (`#121A26`):** The primary surface for modules, metric cards, and review grids.
- **Interactive Hover Surface (`#182232`):** Elevated target state applied on hover or active container focus.
- **Border Specular Hairline (`rgba(255, 255, 255, 0.08)`):** 1px structural framing for all glass and surface modules.
- **Inner Rim Lighting (`inset 0 1px 0 rgba(255, 255, 255, 0.05)`):** Applied to top-facing card edges for physical tactile depth.

### Accents & Telemetry Channels
- **Signature Pulse Emerald (`#00D09C`):** Primary action states, positive sentiment, healthy runtimes, and core KPIs.
- **Emerald Glow / Hover State (`#00F0B5`):** High-energy hover state for active emerald triggers, surrounded by `rgba(0, 208, 156, 0.2)` rings.
- **Telemetry Cyan (`#38BDF8`):** AI synthesis, real-time sync markers, MCP agents, and stream indicators.
- **Alert Amber (`#F59E0B`):** Review velocity drop-offs, platform warnings, and neutral-to-negative sentiment flags.
- **Critical Rose (`#F43F5E`):** Friction spikes, 1-star review anomalies, server latency, and error states.
- **Executive Indigo (`#818CF8`):** Cohort categorizations, long-tail trend markers, and administrative tags.

### Semantic Neutral Ladder
- **Text Primary (`#F8FAFC`):** Display values, primary metric tallies, and critical headlines.
- **Text Secondary (`#94A3B8`):** Subheads, column labels, secondary review feedback, and metadata.
- **Text Muted (`#475569`):** Timestamps, deactivated states, border ticks, and micro-grid labels.

## Typography

The typographic hierarchy enforces rapid visual triangulation between three distinct typefaces:

1. **Executive Framing (Plus Jakarta Sans):** Applied to dashboards, module headers, and summary card titles. Gives structured modern authority without feeling overly rigid.
2. **Analytical Readability (Inter):** Serves qualitative review prose, synthetic executive summaries, and user commentary. Tuned for high legibility at 12–15px.
3. **Quantitative Precision (JetBrains Mono):** Mandated for all MCP telemetry logs, star rating counts, percentage changes, delta badges, and micro-labels. All numerical metrics must render using monospaced or tabular numeral configurations to ensure zero jitter during real-time data polling.

## Layout & Spacing

A compact 12-column fluid grid governs layout integrity across dense data panes, supporting immediate cross-metric comparison.

### Layout Rhythm
- **Global Margins:** 16px on mobile viewports scaling to 32px on wide executive command monitors.
- **Interior Gutters:** Tight 16px to 20px column gaps to maintain maximum optical continuity between charts, sentiment gauges, and stream components.
- **Component Padding Scale:**
  - Micro tags, badge insets: `space-xs` (4px) to `space-sm` (8px).
  - Compact inputs, list rows, button padding: `space-md` (12px).
  - Analytics cards, executive modules: `space-lg` (16px) to `space-xl` (24px).

### Responsive Adaptation
- **Desktop (>= 1280px):** 12-column layout. High-density 4-column KPI rows alongside an 8-column main pulse visualizer and 4-column real-time review waterfall.
- **Tablet (768px - 1279px):** 6-column reflow. Metric headers collapse into a 2x2 matrix; analytical charts and review streams stack into full-width cards.
- **Mobile (< 768px):** Single-column stacked mode. Metric cards transition into a horizontal-snap carousel; text metrics scale to mobile variants; bottom-pinned action dock enabled.

## Elevation & Depth

Visual hierarchy does not use murky, blurred drop shadows; it relies on structured surface luminescence, backdrop blur filtration, and calibrated glow envelopes.

### Surface Tiers
- **Tier 0 (Canvas Base):** Solid `#0B0F17`.
- **Tier 1 (Surface Panel):** Solid `#121A26` with hairline stroke `rgba(255, 255, 255, 0.08)`.
- **Tier 2 (Glassmorphic Overlay / Floating Controls):** `rgba(18, 26, 38, 0.75)` with `backdrop-filter: blur(16px)` and 1px border `rgba(255, 255, 255, 0.12)`.
- **Tier 3 (Active Popovers / Modals):** `rgba(24, 34, 50, 0.95)` with `backdrop-filter: blur(24px)` and drop shadow `0 20px 40px -15px rgba(0, 0, 0, 0.7)`.

### Tactical Glow Lighting
- **Mint Indicator Aura:** Active states and high-priority metrics emit an emerald ambient field: `box-shadow: 0 0 20px rgba(0, 208, 156, 0.2)`.
- **Telemetry Live Beacon:** Subtle pulsing radial halo: `0 0 12px rgba(56, 189, 248, 0.35)`.
- **Inner Specular Horizon:** All structural cards feature a crisp upper edge highlight: `box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06)`.

## Shapes

The interface implements a refined, geometric profile (`roundedness: 1`) that preserves technical rigor while preventing harsh, unfinished corner intersections.

### Corner Radii Guidelines
- **Micro-Components (`rounded` - 4px):** Badges, chip tags, review rating stars, tooltip nodes, and monospaced telemetry chips.
- **Standard Controls (`rounded-lg` - 8px):** Buttons, text inputs, search fields, metric callouts, and dropdown menus.
- **Surface Containers (`rounded-xl` - 12px):** Telemetry cards, sentiment clusters, chart visualizers, and weekly pulse summary panels.
- **Circular Elements:** Live status beacons, user avatars, and round icon actions use `border-radius: 9999px`.

## Components

### 1. Buttons
- **Primary Pulse:** Background `#00D09C`, text `#0B0F17` (Font: `Plus Jakarta Sans`, 600 weight), radius 8px. Hover shifts background to `#00F0B5` with `box-shadow: 0 0 16px rgba(0, 208, 156, 0.35)`.
- **Secondary Glass:** Background `rgba(255, 255, 255, 0.04)`, border `1px solid rgba(255, 255, 255, 0.08)`, text `#F8FAFC`. Hover transitions to `#182232` with border `rgba(255, 255, 255, 0.16)`.
- **Destructive / Flag:** Background `rgba(244, 63, 94, 0.12)`, border `1px solid rgba(244, 63, 94, 0.25)`, text `#F43F5E`.

### 2. Metric & Telemetry Cards
- **Architecture:** Background `#121A26`, 1px border `rgba(255, 255, 255, 0.08)`, radius 12px, interior padding 16px. Top rim highlight `inset 0 1px 0 rgba(255, 255, 255, 0.05)`.
- **Hover State:** Background elevates to `#182232`, border transitions to `rgba(0, 208, 156, 0.3)`.
- **Structure:** Monospaced label (`label-caps`) in `#94A3B8` at the top, primary KPI (`metric-xl`) in `#F8FAFC` centered, and micro-delta badge at the footer.

### 3. Review Sentiment Chips & Tags
- **Positive:** Background `rgba(0, 208, 156, 0.1)`, text `#00D09C`, border `1px solid rgba(0, 208, 156, 0.25)`.
- **Neutral / Informational:** Background `rgba(56, 189, 248, 0.1)`, text `#38BDF8`, border `1px solid rgba(56, 189, 248, 0.25)`.
- **Warning:** Background `rgba(245, 158, 11, 0.1)`, text `#F59E0B`, border `1px solid rgba(245, 158, 11, 0.25)`.
- **Critical / Negative:** Background `rgba(244, 63, 94, 0.1)`, text `#F43F5E`, border `1px solid rgba(244, 63, 94, 0.25)`.
- **Typography:** `label-caps` (11px JetBrains Mono), 4px border radius, 4px vertical / 8px horizontal padding.

### 4. Input Fields & Search Bars
- **Base State:** Background `#0B0F17`, 1px border `rgba(255, 255, 255, 0.08)`, text `#F8FAFC`, placeholder `#475569`, radius 8px.
- **Focus State:** 1px border `#00D09C`, `box-shadow: 0 0 0 2px rgba(0, 208, 156, 0.2)`, outline none.
- **Prefix Icons:** 14px size tinted `#94A3B8`.

### 5. Checkboxes & Toggle Switches
- **Checkbox:** 16x16px, background `#121A26`, 1px border `rgba(255, 255, 255, 0.15)`, radius 4px. Checked state: `#00D09C` background with dark `#0B0F17` check icon.
- **Command Switch:** Track 36x20px in `#121A26` with 1px border `rgba(255, 255, 255, 0.1)`. Thumb 16x16px circle in `#94A3B8`. Active track switches to `rgba(0, 208, 156, 0.2)` with `#00D09C` thumb and glow.

### 6. Executive Review Stream / Data Lists
- **Item Container:** Border-bottom `1px solid rgba(255, 255, 255, 0.05)`, padding 12px 16px.
- **Hover Row:** Background `rgba(255, 255, 255, 0.02)` with transition duration 120ms.
- **Layout:** User handle & star rating in column 1, synthesized critique in column 2, MCP tag and timestamp in column 3.

### 7. MCP Status & Realtime Sync Indicator
- **Pulse Beacon:** Outer pulsing ring with 8px inner circle. Continuous CSS breath animation (0.4 to 1.0 opacity).
- **Log Drawer:** Monospaced terminal output (`telemetry-code`) rendering dark tinted rows (`#0B0F17`) with emerald and cyan code syntax highlighting.