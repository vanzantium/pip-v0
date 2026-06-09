# Imports Contract

## Purpose

- Separate tracked example/templates from private phone, PC, Gmail, and future connector data.

## Ownership

- Tracked files in this folder should be synthetic or blank templates suitable for public review.
- Runtime imports, archives, bridge status, and personal usage/email data are local artifacts.

## Local Contracts

- Never commit real email content, contacts, phone usage, PC activity, account identifiers, credentials, or connector tokens.
- Keep templates minimal and obviously synthetic.
- New bridge code must validate imported structure before using it.
- Generated archives and status files must remain covered by `.gitignore`.

## Work Guidance

- Prefer adding a template file over adding a real captured payload.
- When adding a new import type, document its schema and privacy boundary in the root docs or relevant roadmap.

## Verification

- Run `git status --short`.
- Run `git check-ignore -v` against representative runtime filenames for the new import type.
- Run `python pip_doctor.py`.

## Child DOX Index
