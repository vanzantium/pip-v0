# Safe Desktop Portable Skill (Safe Eyes)

## Purpose

`safe_desktop` gives Pip visual context of what the user is doing ("Safe Eyes") without crippling the computer's CPU with live video streaming.

## Included Skills

- `get_active_window` fetches the title of the currently focused application window (e.g., "Google Chrome - Wikipedia").
- `take_snapshot` captures a single static screenshot of the screen, processes it for text/context, and returns it.

## Safety Contract

- `take_snapshot` explicitly checks the Biological Operating System (BOS) phase. If the system is in `DWELL` or `SHED`, the snapshot is denied to protect performance.
- These skills are purely observational. There is absolutely no ability to click, type, inject keystrokes, or hook into the input event stream.

## Declared Permissions

- `safe desktop telemetry`
- `safe desktop snapshot`
