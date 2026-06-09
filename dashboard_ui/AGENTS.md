# Dashboard UI Contract

## Purpose

- Own the phone-friendly local dashboard template rendered by `pip_control_panel.py`.

## Ownership

- `template.html` owns the main dashboard layout and forms.
- Route logic, data preparation, escaping, and POST-token validation remain in `pip_control_panel.py`.

## Local Contracts

- Every mutating form must receive `_pip_token`; do not add a bypass around dashboard token validation.
- Escape user-, repository-, email-, memory-, and status-derived text before rendering.
- UI labels must distinguish draft/suggestion modes from actions that actually modify apps, email, repositories, or files.
- Nightwatch and Weekly Update must remain visibly separate controls.
- Unsupported or empty data should render a safe status instead of breaking the page.

## Work Guidance

- Reuse existing template variables and visual language unless intentionally redesigning the whole dashboard.
- Keep the page usable on the S25-sized mobile viewport and desktop.
- Avoid remote runtime dependencies for essential dashboard behavior.

## Verification

- Run `python -c "import pip_control_panel; print(len(pip_control_panel.page({})))"`.
- Run `python pip_doctor.py`.
- Confirm new POST forms contain the injected `_pip_token` after rendering.

## Child DOX Index
