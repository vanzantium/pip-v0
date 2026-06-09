# Portable Skills Contract

## Purpose

- Own portable Pip skill packages and their declared capabilities.

## Ownership

- Each package owns its `skill.json`, implementation entry point, and package documentation.
- `pip_skill_registry.py` owns discovery, trust restrictions, and lazy loading.

## Local Contracts

- Skill manifests must declare inputs, outputs, and permissions accurately.
- Listing skills must not execute arbitrary package code.
- New third-party packages remain untrusted until explicitly reviewed and allowlisted.
- High-risk capabilities such as UI automation, keyboard recording, arbitrary execution, messaging, or external writes must remain permission-gated.
- Portable skills must not silently escape configured memory/workspace boundaries.

## Work Guidance

- Keep packages narrow and independently reviewable.
- Update package documentation when permissions or behavior change.
- Prefer a new focused skill over expanding an existing skill into unrelated authority.

## Verification

- Run `python pip_skills.py list`.
- Run `python pip_doctor.py`.
- Exercise the selected skill directly with synthetic or temporary inputs.

## Child DOX Index
