---
name: ui-design-gate
description: Use when an English Learning issue needs a UI design choice for a change to layout, hierarchy, or interaction.
---

# Choose a UI design

1. Read the affected route and its components, [product context](../../../PRODUCT.md), and [design system](../../../DESIGN.md). Identify existing behavior the issue needs to preserve.
2. Use the Impeccable skill to explore two or three distinct directions. Prefer runnable previews using synthetic data when interaction matters. Keep temporary previews separate from the implementation diff.
3. Compare each option at mobile and desktop widths. Check keyboard and touch behavior, focus, and the effect on state and data. For review controls, show both card faces and how flipping unlocks grading.
4. Present the previews and tradeoffs and get the owner's selection before implementing an unresolved design. If the issue already has a selected design covering the change, use it.
5. Record the selected design and rationale in the authorized issue update or local spec. Add an acceptance criterion that can be checked in the browser.
