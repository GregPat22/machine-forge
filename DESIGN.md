# Machine Forge design system

Approved 2026-11-03: the earlier Overview design in deep cobalt, with the eagle-eye MF logo.
The subsequent decorative pattern treatment is rejected. This is a working engineering app.

| Token | Value | Use |
|---|---|---|
| Accent | #293DA7 | Primary actions, selection, links |
| Accent hover | #203187 | Action hover |
| Accent tint | #E9EDF9 | Selected surfaces |
| Workspace | #F4F5F8 | Light working canvas |
| Surface | #FEFEFF | Panels and forms |
| Ink | #232B35 | Main text |
| Secondary ink | #5C6572 | Supporting text |
| Rule | #D7DADF | Grouping and separation |
| Sidebar | #1D263B | Navigation |

IBM Plex Sans is used for reading, headings and controls; IBM Plex Mono for IDs, revision labels,
units and technical values. Fonts are self-hosted with their license notices. The selected light
workspace is consistent across OS appearance preferences. No theme switch is introduced.

Use restrained square controls, fine rules and a 4px spacing base. Primary actions and important
navigation are at least 48px high. Keep readable mixed-case paragraphs, visible keyboard focus,
explicit status labels, native dialog Escape/focus restoration, and reduced-motion support.
Mobile panels stack in task order and navigation opens as a labelled dialog.

The source of every engineering value is a model field or engine result. Requirements are not
achieved rates. Empty/missing/error states remain explicit. Unknown geometry is an envelope;
the existing layout response supplies every size and position in the Overview preview.

Draft mockups and screenshots remain local. The final logo and font assets used by the app are
part of its source. No hatching, circle patterns, bracketed metadata or mockup-only controls.
