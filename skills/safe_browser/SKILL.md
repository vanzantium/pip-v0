# Safe Browser Portable Skill

## Purpose

`safe_browser` gives Pip read-only "Safe Hands" to explore the web without the ability to click, type, or accidentally alter active sessions.

## Included Skills

- `safe_browser_read` opens a URL using Playwright and extracts the readable text.
- `safe_browser_search` opens Google, searches a query, and extracts the results.

## Safety Contract

- The browser is instantiated completely fresh and detached from the user's personal browser profiles to avoid modifying the user's cookies/history.
- There are no methods exposed to the engine for `click`, `type`, or `evaluate` JavaScript. It is strictly read-only text extraction.
- The browser closes automatically after extraction.

## Declared Permissions

- `safe web read`
- `safe web search`
