# Design

## Theme

Mood: midnight research cockpit with precise instrument light. Product surfaces use a near-black neutral base, sky-blue radar marks, and a coral warning/action accent. The palette is restrained: color is for priority, state, and selection rather than decoration.

## Color Palette

Use OKLCH custom properties.

```css
:root {
  --bg: oklch(0.095 0 0);
  --surface: oklch(0.145 0.012 220);
  --surface-2: oklch(0.195 0.018 220);
  --ink: oklch(0.935 0.012 220);
  --muted: oklch(0.705 0.025 220);
  --primary: oklch(0.660 0.145 210);
  --primary-soft: oklch(0.250 0.055 210);
  --accent: oklch(0.660 0.170 28);
  --success: oklch(0.700 0.135 150);
  --warning: oklch(0.780 0.135 85);
  --danger: oklch(0.650 0.170 25);
  --line: oklch(0.310 0.026 220);
}
```

## Typography

Use one product UI stack: `Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`. Headings are compact and clear, not hero-scale. Labels and data use the same family with tighter weight and letter spacing set to zero.

## Layout

The app uses a three-pane cockpit:

- Left rail: product identity, source health, daily status, navigation.
- Main work area: radar summary, topic cards, or Markdown editor.
- Right rail on workshop screens: WeChat preview, assets, source evidence, checklist.

Mobile collapses into top navigation plus stacked sections. Cards use 8px radius, stable dimensions, and no nested-card styling.

## Motion

Motion conveys refresh, generation, selection, and progress. Radar pulse and item reveal are allowed on discovery views, capped around 180-240ms for interface transitions. `prefers-reduced-motion: reduce` disables continuous animation and leaves all content visible.

## Components

- Topic score bars: four named scores with numeric values and explanations.
- Source chips: show source type, health, and count.
- Draft package viewer: Markdown, HTML, sources, checklist, asset prompts.
- Rerun controls: explicit buttons for title, article, style, review, cover, mechanism, and WeChat rendering.
- Empty/loading/error states: show source status and next action rather than generic placeholders.
