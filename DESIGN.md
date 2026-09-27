---
name: English Learning
description: A friendly personal study workspace built around tactile cards and practical calm.
colors:
  study-blue: "#4075a6"
  study-blue-deep: "#315f89"
  study-blue-ink: "#20394e"
  study-blue-muted: "#60788c"
  atmosphere-blue: "rgb(202, 216, 228)"
  atmosphere-mid: "hsl(209, 36%, 86%)"
  atmosphere-light: "hsl(224, 44%, 95%)"
  paper: "rgba(255, 255, 255, 0.65)"
  paper-solid: "#edf3f8"
  signal-orange: "#ff3e00"
  danger-red: "#a34646"
  warning-amber: "#b46b39"
  text: "rgba(0, 0, 0, 0.7)"
typography:
  display:
    fontFamily: "Bodoni Moda, Georgia, serif"
    fontSize: "clamp(2.35rem, 8vw, 4.5rem)"
    fontWeight: 600
    lineHeight: 0.95
  body:
    fontFamily: "Arial, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  playful:
    fontFamily: "Contrail One, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 400
  label:
    fontFamily: "Fira Mono, monospace"
    fontSize: "0.72rem"
    fontWeight: 700
    letterSpacing: "0.08em"
rounded:
  control: "0.55rem"
  button: "0.65rem"
  card: "0.9rem"
  pill: "999px"
spacing:
  xs: "0.25rem"
  sm: "0.5rem"
  md: "1rem"
  lg: "1.5rem"
  xl: "2rem"
components:
  button-primary:
    backgroundColor: "{colors.study-blue-deep}"
    textColor: "white"
    rounded: "{rounded.button}"
    padding: "0.7rem 1rem"
    typography: "{typography.body}"
  button-secondary:
    backgroundColor: "rgba(255, 255, 255, 0.72)"
    textColor: "{colors.study-blue-deep}"
    rounded: "{rounded.button}"
    padding: "0.7rem 1rem"
    typography: "{typography.body}"
  input:
    backgroundColor: "rgba(255, 255, 255, 0.86)"
    textColor: "{colors.study-blue-ink}"
    rounded: "{rounded.control}"
    padding: "0.72rem 0.8rem"
    typography: "{typography.body}"
  management-card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.text}"
    rounded: "{rounded.card}"
    padding: "1rem 1.1rem"
  study-chip:
    backgroundColor: "#f3f4f6"
    textColor: "{colors.text}"
    rounded: "{rounded.pill}"
    padding: "2px 6px"
---

# Design System: English Learning

## Overview

**Creative North Star: "The Calm Card Table"**

The interface should feel like sitting down with a small, familiar set of study cards: direct,
friendly, and ready for a short daily session. Its cool blue atmosphere lowers visual pressure,
while rounded controls and physical flip-and-swipe behavior keep the experience tactile and
lightweight.

This is a practical personal tool, not a dense corporate dashboard. The visual system favors a
clear task at the center, modest supporting information, and components that communicate state
through shape, color, and movement without surrounding the user with panels or metrics.

**Key Characteristics:**

- Cool, calm blue atmosphere with translucent paper-like surfaces.
- Friendly, lightweight composition with one clear task at a time.
- Tactile and playful cards, controls, pills, flips, and swipes.
- Editorial headings used selectively against a plain, practical body face.
- Mostly-flat depth: borders and tonal separation first, shadows only where layering needs proof.

## Colors

Study Blue provides the dependable working color; pale blue atmosphere and white paper layers keep
the app calm, while orange, amber, red, and answer-state colors are reserved for meaningful signals.

### Primary

- **Study Blue** (`#4075a6`): navigation state, language selection, labels, and focus language.
- **Deep Study Blue** (`#315f89`): primary actions, important links, and high-contrast blue text.

### Secondary

- **Signal Orange** (`#ff3e00`): an incumbent attention accent used by search controls and selected
  hover or mode states. Keep it rare so it does not compete with Study Blue.

### Neutral

- **Atmosphere Blue** (`rgb(202, 216, 228)`), **Atmosphere Mid**
  (`hsl(209, 36%, 86%)`), and **Atmosphere Light** (`hsl(224, 44%, 95%)`): the layered page
  background.
- **Translucent Paper** (`rgba(255, 255, 255, 0.65)`): cards, detail panels, and supporting surfaces.
- **Solid Blue Paper** (`#edf3f8`): drawers and dialogs that must visually separate from the page.
- **Blue Ink** (`#20394e`): form text and the darkest cool text role.
- **Muted Study Text** (`#60788c`): secondary explanations and metadata.
- **Body Ink** (`rgba(0, 0, 0, 0.7)`): default copy.

### Tertiary

- **Warning Amber** (`#b46b39`): mutation and recovery notices.
- **Danger Red** (`#a34646`): destructive actions and error boundaries.

### Named Rules

**The Blue Table Rule.** Study Blue establishes the workspace; signal colors mark an action or
state and must not become competing page themes.

## Typography

**Display Font:** Bodoni Moda (with Georgia and serif fallbacks)  
**Body Font:** Arial and the system sans-serif stack  
**Playful Font:** Contrail One (with sans-serif fallback)  
**Label/Mono Font:** Fira Mono (with monospace fallback)

**Character:** Editorial headings give collections and details a personal notebook quality. The
system sans body keeps daily operation fast to scan, Fira Mono makes compact metadata deliberate,
and Contrail One adds a friendly voice to welcome, loading, and completion moments.

### Hierarchy

- **Display** (600, `clamp(2.35rem, 8vw, 4.5rem)`, 0.95): management-page titles and major
  collection identity.
- **Headline** (medium to 600, `clamp(2rem, 7vw, 3.5rem)`): route titles and prominent states.
- **Title** (700, `1.08rem` to `1.65rem`): rows, drawers, editors, and dialogs.
- **Body** (400, `1rem`, 1.5): instructions, definitions, form values, and supporting copy.
- **Label** (700, `0.68rem` to `0.75rem`, `0.08em` to `0.14em`, uppercase): eyebrows, field
  metadata, navigation, and language abbreviations.

### Named Rules

**The One Editorial Moment Rule.** Let the largest page or panel heading carry the serif voice;
keep operational content plain and immediately readable.

## Layout

The shell is a single centered column with a `64rem` maximum width. Management pages fill that
column with `2rem 1.25rem 4rem` padding; search uses a narrower `46rem` reading width. Review is the
most focused surface: a centered card stack reaches `90vw` but caps at `400px`, leaving the answer
controls as the only strong secondary element.

Spacing follows a loose quarter-rem rhythm, with `0.75rem` to `1rem` gaps inside components and
`1.5rem` to `2rem` between page regions. Two-column detail and form grids collapse to one column at
`640px`; search controls stack below `36rem`. On narrow screens, heading actions and resource
actions align left and wrap instead of compressing.

## Elevation & Depth

The system is mostly flat. Tonal separation, translucent white surfaces, cool borders, and the
fixed blue atmosphere do most of the depth work. Small ambient shadows distinguish floating pills
and linked result cards; strong shadows are reserved for true overlays such as drawers and dialogs.

### Shadow Vocabulary

- **Quiet Nav** (`0 6px 20px rgba(47, 78, 105, 0.08)`): separates the pill navigation from the
  atmospheric page.
- **List Lift** (`0 7px 24px rgba(47, 78, 105, 0.07)`): slight lift for actionable rows.
- **Selected Tab** (`0 4px 12px rgba(38, 74, 107, 0.18)`): proves that a segmented option is active.
- **Drawer Edge** (`-18px 0 50px rgba(31, 57, 79, 0.18)`): communicates a panel above the page.
- **Dialog Lift** (`0 22px 60px rgba(31, 57, 79, 0.24)`): reserved for blocking confirmation.

### Named Rules

**The Mostly-Flat Rule.** Use border and tone for ordinary grouping; add a shadow only when an
element is actionable, selected, or physically above another surface.

## Shapes

Rounded rectangles are the default form language. Inputs use `0.55rem`, buttons approximately
`0.65rem`, and cards or panels `0.8rem` to `0.9rem`. Pills use `999px` for navigation shells,
language switches, chips, and badges. Borders are thin and cool blue; the left blue rule on
management rows and amber rule on recovery notices provide directional emphasis without extra
containers.

The review card is the signature silhouette: a compact portrait rectangle with an `8px` face
radius, stacked behind sibling cards and physically flipped or moved. Large overlay panels retain
soft `0.9rem` corners rather than becoming floating capsules.

## Components

### Buttons

- **Shape:** compact rounded rectangle (`0.65rem`) with `0.7rem 1rem` padding and strong label
  weight.
- **Primary:** Deep Study Blue background and white text.
- **Secondary:** translucent white background, blue border, and Deep Study Blue text.
- **Danger:** pale warm background, red border, and dark red text.
- **Hover / Focus:** hover may shift color or lift by `1px`; keyboard focus uses a visible blue
  outline with offset. Disabled controls reduce opacity and communicate waiting or unavailability.

### Chips

- **Style:** compact `12px` labels with `2px 6px` padding and a full pill radius.
- **State:** quiet gray is the default; orange can identify the leading card attribute, and blue
  tint carries scope or language badges.

### Cards / Containers

- **Corner Style:** `0.8rem` to `0.9rem` for management surfaces; `8px` for review-card faces.
- **Background:** translucent white for ordinary information, solid pale blue for overlays, white
  and slate for the two study-card faces.
- **Shadow Strategy:** flat by default; soft ambient lift for links or floating layers.
- **Border:** one-pixel translucent Study Blue, sometimes with a stronger colored left edge.
- **Internal Padding:** generally `1rem` to `1.25rem`.

### Inputs / Fields

- **Style:** translucent white fill, cool blue one-pixel border, `0.55rem` radius, and approximately
  `0.75rem 0.8rem` padding.
- **Focus:** `3px` translucent Study Blue outline with `2px` offset.
- **Error / Disabled:** errors use muted red borders; disabled field groups reduce opacity without
  hiding entered content.

### Navigation

Primary navigation sits in a translucent white pill with a quiet ambient shadow. Links are compact,
bold, uppercase labels with wide tracking. The active route uses a short blue underline; hover uses
the rare Signal Orange accent. Language and mode switches use the same segmented-control grammar,
with a filled selected item inside a pale bordered shell.

### Review Card

The review card is the signature interaction. It centers one learning prompt, keeps metadata in
small chips, flips in `0.35s`, and only allows the answer gesture after the back is visible. A
physical swipe or button press moves the card out while rose and emerald answer states supply clear,
temporary feedback.

## Do's and Don'ts

### Do:

- **Do** keep one study task or management decision visually dominant on each screen.
- **Do** use Study Blue, cool borders, and paper surfaces as the default working vocabulary.
- **Do** reserve pronounced shadows for selected states and true overlays.
- **Do** preserve the card flip-before-answer behavior and tactile swipe feedback.
- **Do** let pills, subtle lift, and short transitions add playfulness without adding visual noise.

### Don't:

- **Don't** turn the interface into a dense dashboard of metrics, panels, or competing controls.
- **Don't** replace the calm blue atmosphere with multiple equally dominant accent colors.
- **Don't** use the editorial display face for dense forms or long operational copy.
- **Don't** add shadows to every bordered surface; grouping should remain mostly flat.
- **Don't** trade the personal, lightweight character for generic enterprise styling.
