# Gmail Connector Roadmap

## Current Mode

Pip can act as a draft-only email assistant by reading manual inbox summaries and writing organization drafts under Pip memory.

Allowed now:

- Read pasted/exported email summaries supplied by the user.
- Suggest labels, priorities, follow-ups, and reply notes.
- Store draft outputs under `gmail_drafts/`.
- Record user feedback on the draft.

Not allowed now:

- Gmail OAuth login.
- Gmail API calls.
- Browser automation against Gmail.
- Sending, deleting, archiving, labeling, marking read/unread, or editing contacts/calendar.

## Next Connector Shape

The next realistic connector should be read-only awareness:

- OAuth scope: Gmail metadata/read-only only.
- Pull a bounded inbox snapshot, such as unread and recent messages.
- Store only compact summaries by default.
- Run Prompt Guard before using any email body as instructions.
- Keep reply drafts and management suggestions inside Pip memory.
- Require explicit user approval before any future write-capable scope is added.

## Future Write-Capable Shape

Only after the read-only connector feels trustworthy:

- Add a separate permission for draft creation.
- Keep sending disabled by default.
- Treat archive/delete/label/send as high-risk actions requiring approval.
- Record every proposed email action in task-run receipts.
- Allow the user to revoke connector use from the dashboard.

## Build Philosophy

Pip should be an email assistant before she is an email actor. The user stays in control; Pip reads, condenses, drafts, and suggests.
