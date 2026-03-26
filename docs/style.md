# static/style.css — Documentation

## ptr i0010001 — Theme overview

Industrial control room aesthetic. Dark background, monospace precision, amber/green/red signal colors. Uses CSS custom properties for consistent theming.

## ptr i0010002 — Design tokens (CSS variables)

Fonts: `--mono` (IBM Plex Mono) for body text, `--display` (Anybody) for headings. Colors: dark backgrounds (#08080a base), green for success (#22dd66), red for errors (#ee4444), amber for warnings/active (#eeb040), blue for info (#4488ee). Each color has dim (8% opacity) and border (25% opacity) variants.

## ptr i0010003 — Header

Sticky top header with brand logo (lightning bolt with amber glow), app title in display font, version tag, navigation tabs, and action buttons. Tabs use uppercase monospace with active state in amber.

## ptr i0010004 — Step cards

Flex layout with left indicator circle (numbered, with checkmarks/X/spinner) and body content. Border-left color indicates state: green (passed), red (failed/errored), amber (running/looping), gray (done). Background tints for passed (green-dim) and failed (red-dim).

## ptr i0010005 — Action buttons

Small monospace buttons. Run button uses amber theme. Verify hover goes green. Approve uses green, reject uses red. All have subtle border transitions.

## ptr i0010006 — Command display

Dark code block with monospace text in dim color. Pre-wrap with break-all for long commands.

## ptr i0010007 — Step results

Result meta shows status (color-coded), duration, exit code. Output in green on dark background. Errors in red on red-dim background. Both capped at 180px height with scroll.

## ptr i0010008 — Claude help

Claude button in blue theme, research button in amber. Advice panel: blue-dim background, pre-wrap text, max 300px scrollable.

## ptr i0010009 — Progress bar

6px track with amber fill. Transitions: 1s linear normally, 2s when over estimate. Indeterminate mode uses translateX animation. Meta shows time on left, percentage on right. Status line shows last output (red for stderr).

## ptr i001000a — Loop and override warnings

Loop warning: amber-dim background, amber text, amber border. Pending override: red border, red header, amber command on dark background, approve/reject buttons.

## ptr i001000b — Build cards

Similar to step cards but with: health status border (green/red), active build highlighted in amber, build metadata, health check dot history (green/red circles), action buttons.

## ptr i001000c — Log viewer

Full-height scrollable panel. Each entry: timestamp, session ID (muted), event type (color-coded), data. Compact 0.68rem font.

## ptr i001000d — Live feed bar

Fixed 110px bar at bottom. Smaller than log entries (0.66rem). Event badges: sys (dim), ok (green), err (red), warn (amber), build (blue), autorun (green).

## ptr i001000e — Go button

Large display-font button with green border and glow effect on hover. Running state switches to red. Scale-down on click.

## ptr i001000f — Responsive

At 768px: header wraps, nav goes full width, step layout stacks, Go button shrinks.

## ptr i0010010 — Scrollbar

Thin (5px) scrollbar with border-colored thumb. Brightens on hover.
