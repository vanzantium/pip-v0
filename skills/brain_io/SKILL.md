# Brain IO Portable Skill

## Purpose

`brain_io` is Pip's portable local-memory skill bundle. It groups small brain-folder operations behind declared permissions so reviewers can see which capabilities are being exposed.

## Included Skills

- `read_brain_file` reads a named file from the configured Pip memory folder and returns truncated content.
- `write_brain_file` writes or appends text inside the configured Pip memory folder only.
- `search_brain` searches the Brain folder through the local Text Hound index when available.
- `record_new_macro` records keyboard events until Escape and saves the result to Pip memory.

## Safety Contract

- `write_brain_file` resolves paths under the configured memory folder and blocks writes outside that sandbox.
- `record_new_macro` is high-risk because it records keyboard events. It must remain approval-gated through `pip_safety`.
- This package should not edit original project files.
- This package should not send data over the network.
- This package should not run arbitrary scripts.

## Declared Permissions

- `read brain file`
- `write brain file`
- `read brain folder`
- `record keyboard`

## Review Notes

The first three skills are useful for local memory inspection and drafting. `record_new_macro` is intentionally present but sensitive; reviewers should confirm that approval gating remains intact before expanding macro or UI automation features.
