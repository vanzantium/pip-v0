#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from pip_phone_bridge import (
    apply_phone_feedback,
    get_phone_status,
    import_manual_summary_text,
    import_phone_usage_text,
)
from pip_pc_bridge import get_pc_status, import_pc_usage_text
from pip_workspace import (
    draft_next_actions,
    export_control_status,
    load_workspace,
    record_feedback,
    resolve_permission,
    run_ambient_cycle,
    queue_next_wake,
)
from pip_safety import request_safety_permission
import pip_app_skills
import pip_blender_recipes
import pip_flow_master
import pip_jobs
import pip_scheduler
import pip_platform
import pip_system_manifest
import pip_token_guard
import pip_traces
import pip_background_tasks

class QuietThreadingHTTPServer(ThreadingHTTPServer):
    def handle_error(self, request: object, client_address: tuple[str, int]) -> None:
        # Mobile browsers sometimes close keep-alive sockets after a page transition.
        # That is normal and should not print a traceback that looks like a Pip failure.
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)):
            print(f"{client_address[0]} - connection closed by client")
            return
        super().handle_error(request, client_address)


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def start_nightwatch_loop() -> dict[str, Any]:
    import subprocess

    nw_path = Path(__file__).resolve().parent / "pip_nightwatch_loop.py"
    if not nw_path.exists():
        return {"ok": False, "message": "pip_nightwatch_loop.py not found."}
    subprocess.Popen(
        [sys.executable, str(nw_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        **pip_platform.hidden_subprocess_kwargs(),
    )
    return {"ok": True, "message": "Nightwatch background loop started."}


def _safe_form_int(form: dict[str, list[str]], key: str, default: int = -1) -> int:
    try:
        return int((form.get(key) or [str(default)])[0])
    except (TypeError, ValueError):
        return default


def page(status: dict[str, Any]) -> str:
    import json
    from pathlib import Path
    import html
    
    proposal = status.get("latest_proposal") or {}
    status_label = proposal.get("status", "idle")
    proposal_text = proposal.get("proposal", "Pip is resting. Tap Run Scan to wake her.")
    
    import pip_config
    memory_path = pip_config.get_memory_path()
    
    # Load apps
    apps = []
    try:
        with open(memory_path / "apps.json", "r", encoding="utf-8") as f:
            apps = json.load(f)
    except Exception:
        pass
        
    apps_html = ""
    for app in apps:
        checked = "checked" if app.get("enabled") else ""
        level = app.get("level", 1)
        xp = app.get("xp", 0)
        apps_html += f"""
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
            <label><input type="checkbox" name="app_{html.escape(app['name'])}" {checked}> {html.escape(app['name'])}</label>
            <span class="small" style="background: var(--leaf); padding: 2px 6px; border-radius: 4px;">Lvl {level} ({xp}xp)</span>
        </div>
        """
    if not apps_html:
        apps_html = "<p class='small'>No apps scanned yet. Run the scanner first.</p>"

    # Load hardware report
    hw = {}
    try:
        with open(memory_path / "hardware.json", "r", encoding="utf-8") as f:
            hw = json.load(f)
    except Exception:
        pass
        
    hw_html = ""
    if hw:
        rec = hw.get("recommendation", {})
        hw_html = f"""
        <div style="margin-top: 15px; padding: 10px; background: rgba(255,255,255,0.7); border-radius: 8px;">
            <p style="margin: 0 0 5px 0;"><strong>CPU:</strong> {html.escape(hw.get('cpu', ''))}</p>
            <p style="margin: 0 0 5px 0;"><strong>RAM:</strong> {hw.get('ram_gb', 0)} GB</p>
            <p style="margin: 0 0 5px 0;"><strong>GPU:</strong> {html.escape(hw.get('gpu', ''))}</p>
            <hr style="border: 0; border-top: 1px solid rgba(0,0,0,0.1); margin: 10px 0;">
            <p style="margin: 0 0 5px 0; color: #10b981; font-weight: bold;">Pip's Recommendation ({rec.get('tier', '')})</p>
            <p style="margin: 0 0 5px 0;"><strong>Model:</strong> {html.escape(rec.get('model', ''))}</p>
            <p style="margin: 0 0 5px 0; font-size: 0.9em; line-height: 1.4;">{html.escape(rec.get('reason', ''))}</p>
            <p style="margin: 0; font-size: 0.8em; font-style: italic; color: #666;">{html.escape(rec.get('prompt_strategy', ''))}</p>
        </div>
        """

    permissions = status.get("permissions") or {}
    pending_permissions = permissions.get("pending") or []
    if pending_permissions:
        permission_cards = []
        for item in pending_permissions:
            request_id = html.escape(item.get("id", ""))
            title = html.escape(item.get("title", "Permission request"))
            action_type = html.escape(item.get("action_type", "unknown"))
            rationale = html.escape(item.get("rationale", ""))
            permission_cards.append(f"""
            <div style="margin-bottom:12px;padding:12px;background:rgba(255,255,255,.62);border-radius:12px;border:1px solid rgba(92,111,67,.25);">
              <p style="margin:0 0 6px 0;"><strong>{title}</strong></p>
              <p class="small" style="margin:0 0 8px 0;">{action_type}: {rationale}</p>
              <form method="post" action="/permission" style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
                <input type="hidden" name="request_id" value="{request_id}">
                <input type="hidden" name="note" value="Resolved from Pip dashboard.">
                <button type="submit" name="decision" value="approved">Approve</button>
                <button class="secondary" type="submit" name="decision" value="denied">Deny</button>
              </form>
            </div>
            """)
        permissions_html = "\n".join(permission_cards)
    else:
        permissions_html = "<p class='small'>No pending permissions. Pip is staying inside her safe lane.</p>"

    jobs = pip_jobs.list_jobs().get("jobs", [])
    recent_jobs = list(reversed(jobs[-5:]))
    if recent_jobs:
        job_cards = []
        for job in recent_jobs:
            job_id = html.escape(job.get("id", ""))
            title = html.escape(job.get("title", "Untitled job"))
            kind = html.escape(job.get("kind", "job"))
            job_status = html.escape(job.get("status", "unknown"))
            latest_log = "<br>".join(html.escape(line) for line in job.get("latest_log", [])[-4:])
            stop_button = ""
            if job.get("status") in {"running", "stop_requested"}:
                stop_button = f"""
                <form method="post" action="/jobs/stop" style="margin-top:8px;">
                  <input type="hidden" name="job_id" value="{job_id}">
                  <button class="secondary" type="submit">Request Stop</button>
                </form>
                """
            job_cards.append(f"""
            <div style="margin-bottom:12px;padding:12px;background:rgba(255,255,255,.62);border-radius:12px;border:1px solid rgba(92,111,67,.25);">
              <p style="margin:0 0 6px 0;"><strong>{title}</strong></p>
              <p class="small" style="margin:0 0 8px 0;">{kind} | {job_status} | {job_id}</p>
              <div class="small" style="font-family:monospace;background:rgba(255,255,255,.65);padding:8px;border-radius:8px;min-height:32px;">{latest_log or "No log lines yet."}</div>
              {stop_button}
            </div>
            """)
        jobs_html = "\n".join(job_cards)
    else:
        jobs_html = "<p class='small'>No jobs yet. Approved autonomous goals will show up here.</p>"

    blender = pip_app_skills.assess_app("Blender")
    blender_summary = blender.get("summary", {})
    blender_domains = blender.get("app", {}).get("domains", {})
    blender_domain_html = ""
    for domain_key, domain in blender_domains.items():
        blender_domain_html += f"""
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;gap:12px;">
          <span>{html.escape(domain.get('label', domain_key))}</span>
          <span class="small" style="background:var(--leaf);padding:2px 6px;border-radius:4px;">Lvl {domain.get('level', 1)} ({domain.get('xp', 0)}xp)</span>
        </div>
        """
    blender_focus = "".join(f"<li>{html.escape(step)}</li>" for step in blender_summary.get("next_focus", []))
    if not blender_focus:
        blender_focus = "<li>Record a Blender action to build Pip's first evidence trail.</li>"

    blender_recipes = pip_blender_recipes.list_recipes()
    recipe_buttons = ""
    for recipe in blender_recipes.get("recipes", [])[:5]:
        key = html.escape(recipe.get("key", ""))
        title = html.escape(recipe.get("title", key))
        domain = html.escape(recipe.get("domain", "general"))
        intent = html.escape(recipe.get("intent", ""))
        recipe_buttons += f"""
        <form method="post" action="/blender/recipe-draft" style="margin-bottom:10px;padding:10px;background:rgba(255,255,255,.55);border-radius:12px;">
          <input type="hidden" name="recipe" value="{key}">
          <input type="hidden" name="project" value="Blender practice">
          <p style="margin:0 0 4px 0;"><strong>{title}</strong></p>
          <p class="small" style="margin:0 0 8px 0;">{domain}: {intent}</p>
          <button type="submit">Draft This Recipe</button>
        </form>
        """
    latest_recipe = ""
    history = blender_recipes.get("history", [])
    if history:
        item = history[-1]
        latest_recipe = f"""
        <p class="small"><strong>Latest draft:</strong> {html.escape(item.get('title', 'Recipe'))} | {html.escape(item.get('status', 'drafted'))}</p>
        <p class="small" style="word-break:break-all;">{html.escape(item.get('path', ''))}</p>
        """
    else:
        latest_recipe = "<p class='small'>No Blender recipes drafted yet.</p>"

    governor = pip_token_guard.status()
    gov_pct = int(governor.get("remaining_ratio", 0) * 100)
    gov_mode = html.escape(governor.get("mode", "BUILD"))
    gov_last = governor.get("last_assessment") or {}
    gov_nudge = html.escape(gov_last.get("nudge") or "Pip is watching the budget and will nudge when work gets wasteful.")
    gov_signal = html.escape((gov_last.get("signal") or {}).get("triage_summary", "No recent Signal Sieve assessment."))
    gov_events = ""
    for event in governor.get("recent_events", [])[-5:]:
        gov_events += f"""
        <div class="small" style="display:flex;justify-content:space-between;gap:8px;margin-bottom:4px;">
          <span>{html.escape(event.get('intent', 'event'))}</span>
          <span>{event.get('actual_tokens', 0)} spent / {event.get('saved_tokens', 0)} saved</span>
        </div>
        """
    if not gov_events:
        gov_events = "<p class='small'>No token events recorded yet.</p>"

    flow = pip_flow_master.inspect_flow_master()
    flow_latest = flow.get("latest_assessment") or {}
    flow_state = html.escape(flow_latest.get("flow_state") or "STAND")
    flow_pressure = flow_latest.get("composite_threat_score")
    flow_pressure_text = "not assessed" if flow_pressure is None else f"{int(float(flow_pressure) * 100)}%"
    flow_digest = flow_latest.get("receipts_digest") or {}
    flow_action = html.escape(flow_digest.get("action") or "Run a Flow check to convert pressure into a receipts digest.")
    flow_summary = html.escape((flow_latest.get("signal") or {}).get("triage_summary") or "No Flow Master assessment yet.")
    flow_sources = flow.get("source_files", [])
    flow_source_text = f"{len(flow_sources)} source files found" if flow_sources else "Flow Master source folder not found"

    trace_status = pip_traces.inspect_traces(limit=5)
    trace_events = trace_status.get("latest", [])
    trace_html = ""
    for event in reversed(trace_events):
        event_kind = html.escape(event.get("kind", "event"))
        event_status = html.escape(event.get("status", "ok"))
        event_action = html.escape(event.get("action", ""))
        event_summary = html.escape(event.get("summary", ""))
        event_at = html.escape(event.get("at", ""))
        trace_html += f"""
        <div style="margin-bottom:10px;padding:10px;background:rgba(255,255,255,.58);border-radius:10px;">
          <p class="small" style="margin:0 0 4px 0;"><strong>{event_kind}</strong> | {event_status} | {event_action}</p>
          <p class="small" style="margin:0 0 4px 0;">{event_summary}</p>
          <p class="small" style="margin:0;">{event_at}</p>
        </div>
        """
    if not trace_html:
        trace_html = "<p class='small'>No trace events yet. Pip will start leaving receipts as skills and dashboard actions run.</p>"

    system_status = pip_system_manifest.inspect_manifest(refresh=False)
    system_manifest = system_status.get("manifest") or {}
    system_primitives = system_manifest.get("primitives") or {}
    system_manifest_path = html.escape(system_status.get("manifest_path", ""))
    primitive_names = ", ".join(name.replace("_", " ") for name in system_primitives.keys())
    primitive_text = html.escape(primitive_names or "Manifest not generated yet.")

    platform_status = pip_platform.feature_status()
    platform_features = platform_status.get("features", {})
    platform_html = ""
    for feature, enabled in platform_features.items():
        label = feature.replace("_", " ").title()
        platform_html += f"""
        <div class="small" style="display:flex;justify-content:space-between;gap:8px;margin-bottom:4px;">
          <span>{html.escape(label)}</span>
          <span>{'available' if enabled else 'not yet'}</span>
        </div>
        """

    developer_shells = pip_app_skills.inspect_developer_shells().get("shells", [])
    shell_cards = ""
    for shell in developer_shells:
        domains = shell.get("domains", {})
        domain_labels = ", ".join(
            domain.get("label", key.replace("_", " ").title())
            for key, domain in list(domains.items())[:3]
        )
        guidance = shell.get("handoff_guidance", ["Keep handoffs scoped and permission-gated."])[0]
        shell_cards += f"""
      <div style="background: var(--clay); border: 1px solid rgba(255,255,255,0.05); border-radius: 8px; padding: 10px; margin-bottom: 8px;">
        <strong>{html.escape(shell['name'])}</strong> <span class="small" style="color:var(--text-muted);">&middot; {html.escape(shell.get('engine', 'Local Model'))}</span>
        <p class="small" style="margin-top:4px;">"{html.escape(shell.get('role', ''))}"</p>
        <p class="small" style="margin-top:4px; font-family:monospace; color:var(--text-muted);">Persona: {html.escape(shell.get('persona', ''))}</p>
      </div>
        """
    if not shell_cards:
        shell_cards = "<p class='small'>No developer shells generated. Click bootstrap below.</p>"

    scheduler_status = pip_scheduler.get_status()
    jobs = scheduler_status.get("jobs", [])
    scheduler_html = ""
    for job in jobs:
        scheduler_html += f"""
        <div style="background: var(--clay); border-radius: 8px; padding: 10px; margin-bottom: 8px;">
            <strong>{html.escape(job.get('name', 'Job'))}</strong> <span class="small pill">{html.escape(job.get('status', 'unknown'))}</span>
            <p class="small" style="margin-top: 4px;">{html.escape(job.get('goal', ''))}</p>
            <div class="actions" style="margin-top: 8px;">
                <form method="post" action="/scheduler/pause?id={html.escape(job['id'])}" style="display:inline;">
                    <button class="quiet" style="padding: 4px 8px; font-size: 11px;">Pause</button>
                </form>
                <form method="post" action="/scheduler/resume?id={html.escape(job['id'])}" style="display:inline;">
                    <button class="quiet" style="padding: 4px 8px; font-size: 11px;">Resume</button>
                </form>
            </div>
        </div>
        """
    if not scheduler_html:
        scheduler_html = "<p class='small'>No jobs scheduled.</p>"

    scripts_html = ""
    try:
        import pip_background_tasks
        scripts = pip_background_tasks.list_scripts()
        for script in scripts:
            name = html.escape(script.get('name', ''))
            scripts_html += f"""
            <div style="background: rgba(255,255,255,0.6); border: 1px solid rgba(92,111,67,0.3); border-radius: 8px; padding: 10px; margin-bottom: 8px;">
                <strong>{name}</strong>
                <div class="actions" style="margin-top: 8px;">
                    <form method="post" action="/scripts/run" style="display:inline;">
                        <input type="hidden" name="script" value="{name}">
                        <input type="hidden" name="silent" value="false">
                        <button class="quiet" style="padding: 4px 8px; font-size: 11px;">Run Tracked</button>
                    </form>
                    <form method="post" action="/scripts/run" style="display:inline;">
                        <input type="hidden" name="script" value="{name}">
                        <input type="hidden" name="silent" value="true">
                        <button class="quiet" style="padding: 4px 8px; font-size: 11px;">Run Silent</button>
                    </form>
                </div>
            </div>
            """
    except Exception as e:
        scripts_html = f"<p class='small'>Error loading scripts: {e}</p>"
    if not scripts_html:
        scripts_html = "<p class='small'>No background scripts found in pip-v0/scripts.</p>"

    import pip_self_model
    self_model_data = pip_self_model.load_self_model()
    self_model_html = ""
    
    beliefs = self_model_data.get("beliefs", [])
    if beliefs:
        self_model_html += "<h4>Beliefs</h4><ul style='padding-left:20px;'>"
        for i, b in enumerate(beliefs):
            self_model_html += f"""
            <li style="margin-bottom:8px;">
              {html.escape(b)}
              <form method="post" action="/self-model/prune-belief" style="display:inline; margin-left:8px;">
                <input type="hidden" name="index" value="{i}">
                <button type="submit" class="quiet" style="padding:2px 6px; font-size:10px; color:#ef4444; border-color:#ef4444;">Prune</button>
              </form>
            </li>
            """
        self_model_html += "</ul>"
        
    rules = self_model_data.get("learned_rules", [])
    if rules:
        self_model_html += "<h4>Learned Rules</h4><ul style='padding-left:20px;'>"
        for i, r in enumerate(rules):
            self_model_html += f"""
            <li style="margin-bottom:8px;">
              {html.escape(r)}
              <form method="post" action="/self-model/prune-rule" style="display:inline; margin-left:8px;">
                <input type="hidden" name="index" value="{i}">
                <button type="submit" class="quiet" style="padding:2px 6px; font-size:10px; color:#ef4444; border-color:#ef4444;">Prune</button>
              </form>
            </li>
            """
        self_model_html += "</ul>"
        
    if not beliefs and not rules:
        self_model_html = "<p class='small' style='color:var(--text-muted);'>No beliefs or rules have been extracted yet.</p>"

    
    # --- Pre-computations for Template ---
    escaped_memory_path = html.escape(str(memory_path))
    escaped_proposal_text = html.escape(proposal_text)
    platform_os = html.escape(platform_status.get('os', 'Unknown'))
    blender_role = html.escape(blender_summary.get('role', 'app teammate'))
    escaped_status_label = html.escape(status_label)
    escaped_flow_source = html.escape(flow_source_text)
    blender_level = blender_summary.get('level', 1)
    blender_xp = blender_summary.get('xp', 0)
    trace_total_events = trace_status.get('total_events', 0)

    # --- Eval Scorecard ---
    eval_html = "<p class='small' style='color:var(--text-muted);'>No evaluation run yet.</p>"
    try:
        import pip_eval
        report = pip_eval.build_eval_report(memory_path=str(memory_path))
        if report.get("feedback") and report["feedback"].get("summary"):
            f_sum = report["feedback"]["summary"]
            eval_html = f"""
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px;">
                <div style="background: rgba(255,255,255,0.7); padding: 8px; border-radius: 6px;">
                    <strong style="display:block; font-size: 0.8rem; color: #666;">Acceptance Rate</strong>
                    <span style="font-size: 1.1rem; color: var(--moss);">{f_sum.get('acceptance_rate', 'N/A')}</span>
                </div>
                <div style="background: rgba(255,255,255,0.7); padding: 8px; border-radius: 6px;">
                    <strong style="display:block; font-size: 0.8rem; color: #666;">Repeat Rejections</strong>
                    <span style="font-size: 1.1rem; color: #ef4444;">{f_sum.get('repeat_rejection_rate', 'N/A')}</span>
                </div>
                <div style="background: rgba(255,255,255,0.7); padding: 8px; border-radius: 6px;">
                    <strong style="display:block; font-size: 0.8rem; color: #666;">Rank Quality (MRR)</strong>
                    <span style="font-size: 1.1rem; color: var(--moss);">{f_sum.get('rank_quality_mrr', 'N/A')}</span>
                </div>
                <div style="background: rgba(255,255,255,0.7); padding: 8px; border-radius: 6px;">
                    <strong style="display:block; font-size: 0.8rem; color: #666;">Total Proposals</strong>
                    <span style="font-size: 1.1rem; color: var(--ink);">{f_sum.get('ever_proposed', '0')}</span>
                </div>
            </div>
            """
    except Exception as e:
        eval_html = f"<p class='small' style='color:var(--text-muted);'>Eval error: {{e}}</p>"

    # --- Render Template ---
    template_file = Path("dashboard_ui/template.html")
    if template_file.exists():
        tpl = template_file.read_text(encoding="utf-8")
        return tpl.format(**locals())
    else:
        return "<html><body><h1>Missing template.html</h1></body></html>"


def fairy_page() -> str:
    from pathlib import Path
    has_avatar = False
    for ext in ["png", "jpg", "jpeg", "gif"]:
        if Path(f"avatar.{ext}").exists():
            has_avatar = True
            break

    if has_avatar:
        sprite_html = '<img class="sprite" id="fairy" src="/avatar" width="112" height="179" style="object-fit: contain; filter: drop-shadow(0 5px 14px rgba(16,185,129,0.5));" onclick="tap()">'
    else:
        sprite_html = """<svg class="sprite" id="fairy" viewBox="0 0 100 140" width="112" height="179" onclick="tap()">
    <defs>
      <radialGradient id="hgrad" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stop-color="#fff" stop-opacity=".9"/>
        <stop offset="60%" stop-color="#fff" stop-opacity=".7"/>
        <stop offset="100%" stop-color="#fff" stop-opacity="0"/>
      </radialGradient>
    </defs>
    
    <!-- back wings -->
    <path class="wll" d="M47 89 Q22 60 10 75 Q28 105 47 89" fill="rgba(16,185,129,.5)"/>
    <path class="wrl" d="M53 89 Q78 60 90 75 Q72 105 53 89" fill="rgba(139,92,246,.5)"/>

    <!-- front wings -->
    <path class="wl" d="M47 82 Q15 45 4 64 Q25 100 47 82" fill="rgba(16,185,129,.8)"/>
    <path class="wr" d="M53 82 Q85 45 96 64 Q75 100 53 82" fill="rgba(139,92,246,.8)"/>

    <!-- body/dress -->
    <path d="M45 80 Q35 110 32 125 Q50 135 68 125 Q65 110 55 80 Z" fill="#8b5cf6"/>
    <path d="M47 80 Q39 110 36 123 Q50 130 64 123 Q61 110 53 80 Z" fill="#6d28d9"/>

    <!-- head -->
    <circle cx="50" cy="72" r="13.5" fill="url(#hgrad)"/>

    <!-- leaf crown -->
    <path d="M37 65 C35 54 43 50 46 61" fill="#0f172a" opacity=".95"/>
    <path d="M42 62 C41 51 51 48 51 60" fill="#1e1b4b" opacity=".95"/>
    <path d="M50 61 C51 50 61 50 60 61" fill="#0f172a" opacity=".95"/>
    <path d="M56 64 C60 54 66 55 64 64" fill="#1e1b4b" opacity=".9"/>
    <!-- crown highlight -->
    <path d="M38 64 C36 55 43 52 46 60" fill="rgba(16,185,129,.3)"/>
    <path d="M51 61 C52 52 60 52 59 61" fill="rgba(16,185,129,.3)"/>

    <!-- eyes -->
    <circle cx="45" cy="73" r="2.4" fill="#0d1810"/>
    <circle cx="55" cy="73" r="2.4" fill="#0d1810"/>
    <circle cx="45.9" cy="72.2" r=".9" fill="white"/>
    <circle cx="55.9" cy="72.2" r=".9" fill="white"/>

    <!-- blush -->
    <ellipse cx="41.5" cy="77" rx="3.2" ry="1.6" fill="rgba(139,92,246,.5)"/>
    <ellipse cx="58.5" cy="77" rx="3.2" ry="1.6" fill="rgba(139,92,246,.5)"/>

    <!-- smile -->
    <path d="M45.5 78 Q50 82 54.5 78" stroke="#0d1810" stroke-width="1.3"
          fill="none" stroke-linecap="round"/>

    <!-- legs -->
    <line x1="46" y1="116" x2="43" y2="133" stroke="#312e81" stroke-width="2.6" stroke-linecap="round"/>
    <line x1="54" y1="116" x2="57" y2="133" stroke="#312e81" stroke-width="2.6" stroke-linecap="round"/>
    <ellipse cx="42"  cy="134.5" rx="5.5" ry="2.2" fill="#312e81"/>
    <ellipse cx="58"  cy="134.5" rx="5.5" ry="2.2" fill="#312e81"/>
  </svg>"""

    html_str = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Pip</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    :root{
      --moss:#8b5cf6;--leaf:#10b981;--silk:#0f172a;
      --clay:#f59e0b;--ink:#e0e6ff;--quiet:#94a3b8;
    }
    html,body{
      height:100%;overflow:hidden;
      font-family:Georgia,"Times New Roman",serif;
      background:
        radial-gradient(circle at 30% 20%,rgba(16,185,129,.5),transparent 60%),
        linear-gradient(160deg,#0f172a 0%,#1e1b4b 60%,#064e3b 100%);
      -webkit-app-region:drag;
      -webkit-user-select:none;user-select:none;
    }
    body{
      display:flex;flex-direction:column;
      align-items:center;justify-content:center;
      min-height:100vh;padding:16px;
    }
    /* close btn */
    .closebtn{
      position:fixed;top:8px;left:10px;
      width:20px;height:20px;border-radius:50%;
      background:rgba(92,111,67,.22);border:0;
      cursor:pointer;font-size:11px;line-height:20px;text-align:center;
      color:var(--quiet);transition:background .15s;
      -webkit-app-region:no-drag;
    }
    .closebtn:hover{background:rgba(185,111,77,.5);color:#fff;}

    /* stage */
    .stage{position:relative;display:flex;flex-direction:column;align-items:center;}

    /* speech bubble */
    .bubble{
      width:252px;
      background:rgba(30,41,59,.92);
      border:1.5px solid rgba(16,185,129,.4);
      border-radius:22px;
      padding:14px 15px 12px;
      box-shadow:0 6px 28px rgba(139,92,246,.4);
      margin-bottom:12px;
      display:none;
      animation:bubble-in .38s cubic-bezier(.34,1.56,.64,1) both;
      -webkit-app-region:no-drag;
    }
    .bubble::after{
      content:"";display:block;
      width:0;height:0;margin:8px auto 0;
      border:10px solid transparent;
      border-top-color:rgba(30,41,59,.92);
    }
    .show .bubble{display:block;}

    @keyframes bubble-in{
      from{opacity:0;transform:scale(.88) translateY(8px);}
      to  {opacity:1;transform:scale(1)   translateY(0);}
    }

    .prop{font-size:.88rem;color:var(--ink);line-height:1.44;margin-bottom:7px;font-weight:700;}
    .evid{font-size:.76rem;color:#94a3b8;line-height:1.32;margin-bottom:11px;}

    .btns{display:flex;gap:7px;}
    .btn{
      flex:1;border:0;border-radius:14px;padding:9px 4px;
      cursor:pointer;font:700 .74rem Georgia,serif;
      transition:filter .14s,transform .1s;
    }
    .btn:active{filter:brightness(.86);transform:scale(.95);}
    .yes {background:var(--moss);color:#fff;}
    .wait{background:var(--quiet);color:#fff;}
    .no  {background:var(--clay);color:#fff;}

    /* idle dots */
    .idle{display:flex;gap:5px;margin-top:8px;height:14px;align-items:center;}
    .show .idle{visibility:hidden;}
    .d{
      width:6px;height:6px;border-radius:50%;
      background:var(--leaf);animation:bounce 1.5s ease-in-out infinite;opacity:.8;
    }
    .d:nth-child(2){animation-delay:.22s;}
    .d:nth-child(3){animation-delay:.44s;}
    @keyframes bounce{
      0%,80%,100%{transform:translateY(0);opacity:.35;}
      40%{transform:translateY(-5px);opacity:.9;}
    }

    /* fairy float */
    .sprite{
      animation:float 3.6s ease-in-out infinite;
      filter:drop-shadow(0 5px 14px rgba(55,75,35,.25));
      cursor:pointer;
    }
    @keyframes float{
      0%,100%{transform:translateY(0);}
      50%    {transform:translateY(-11px);}
    }
    @keyframes pop{
      0%,100%{transform:translateY(0) rotate(0);}
      25%    {transform:translateY(-4px) rotate(-5deg);}
      75%    {transform:translateY(-4px) rotate(5deg);}
    }
    .popping .sprite{animation:float 3.6s ease-in-out infinite,pop .5s ease-in-out;}

    /* wings */
    .wl {transform-origin:47px 82px;animation:wf 1.1s ease-in-out infinite;}
    .wr {transform-origin:53px 82px;animation:wf 1.1s ease-in-out infinite .08s;}
    .wll{transform-origin:47px 89px;animation:wf 1.3s ease-in-out infinite .15s;}
    .wrl{transform-origin:53px 89px;animation:wf 1.3s ease-in-out infinite .23s;}
    @keyframes wf{
      0%,100%{transform:scaleX(1);}
      50%    {transform:scaleX(.8);}
    }

    /* sparkles */
    .sp{
      position:absolute;border-radius:50%;
      background:var(--leaf);pointer-events:none;
      opacity:0;transition:opacity .4s;
    }
    .show .sp{animation:sparkle 2.2s ease-in-out infinite;}
    @keyframes sparkle{
      0%,100%{opacity:0;transform:scale(.4);}
      50%    {opacity:.75;transform:scale(1.1);}
    }

    /* status dot */
    .badge{
      position:fixed;top:10px;right:10px;
      width:9px;height:9px;border-radius:50%;
      background:var(--moss);animation:pulse 2.2s ease-in-out infinite;
    }
    .show ~ .badge,.show+.badge{background:var(--clay);}
    @keyframes pulse{
      0%,100%{opacity:1;transform:scale(1);}
      50%    {opacity:.35;transform:scale(.65);}
    }

    /* full panel link */
    .fulllink{
      position:fixed;bottom:10px;
      font-size:.7rem;color:var(--quiet);
      text-decoration:none;opacity:.5;
      -webkit-app-region:no-drag;
    }
    .fulllink:hover{opacity:1;}
  </style>
</head>
<body>

<div id="root" class="stage">

  <div class="bubble">
    <p class="prop" id="ptxt">…</p>
    <p class="evid" id="etxt"></p>
    <div class="btns">
      <button class="btn yes"  onclick="fb('accepted')">Accept</button>
      <button class="btn wait" onclick="fb('deferred')">Later</button>
      <button class="btn no"   onclick="fb('rejected')">Nope</button>
    </div>
  </div>

  <!-- sparkles (activate via .show on parent) -->
  <div class="sp" style="width:7px;height:7px;top:4px;left:22px;animation-delay:0s"></div>
  <div class="sp" style="width:5px;height:5px;top:18px;right:20px;animation-delay:.8s"></div>
  <div class="sp" style="width:6px;height:6px;top:-4px;right:38px;animation-delay:1.5s"></div>

  __SPRITE_HTML__

  <!-- idle breathing dots -->
  <div class="idle">
    <div class="d"></div><div class="d"></div><div class="d"></div>
  </div>

  <div id="chatbox" style="display:none; width: 280px; margin-top: 15px; background: rgba(251,248,234,.9); border-radius: 12px; padding: 10px; box-shadow: 0 4px 12px rgba(28,36,23,.1); -webkit-app-region:no-drag; position:relative; z-index: 10;">
    <div id="chatlog" style="height: 120px; overflow-y: auto; font-size: 0.8rem; margin-bottom: 8px; display: flex; flex-direction: column; gap: 4px; user-select: text; -webkit-user-select: text; cursor: auto;"></div>
    <div style="display: flex; gap: 5px;">
      <input type="text" id="chatinput" placeholder="Say hi..." style="flex: 1; border: 1px solid rgba(92,111,67,.3); border-radius: 8px; padding: 6px; box-sizing: border-box; font-family: inherit; font-size: 0.8rem;" onkeydown="if(event.key === 'Enter') sendChat()">
      <label for="chatfile" style="cursor: pointer; background: rgba(92,111,67,.1); border-radius: 8px; padding: 6px 10px; display: flex; align-items: center; justify-content: center; font-size: 0.8rem;" title="Attach a text file">📎</label>
      <input type="file" id="chatfile" style="display: none;">
    </div>
  </div>

</div>

<button class="closebtn" onclick="closePip()" title="Hide Pip">✕</button>
<button class="chatbtn" onclick="toggleChat()" title="Chat with Pip" style="position:fixed;top:8px;left:35px;width:20px;height:20px;border-radius:50%;background:rgba(92,111,67,.22);border:0;cursor:pointer;font-size:11px;line-height:20px;text-align:center;color:var(--quiet);transition:background .15s;-webkit-app-region:no-drag;">💬</button>
<div class="badge" id="badge"></div>
<a class="fulllink" href="/" target="_blank" style="left:10px;">open full panel</a>

<script>
  async function uploadAvatar() {
    const file = document.getElementById('avatar_file').files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async function() {
      const b64 = reader.result.split(',')[1];
      await fetch('/upload-avatar', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({image: b64, filename: file.name})
      });
      location.reload();
    };
    reader.readAsDataURL(file);
  }

  const root  = document.getElementById('root');
  const badge = document.getElementById('badge');

  async function revertAvatar() {
    await fetch('/revert-avatar', {method: 'POST'});
    location.reload();
  }

  async function poll() {
    try {
      const d = await fetch('/pip/latest').then(r => r.json());
      const live = d && d.proposal
                   && d.status !== 'accepted'
                   && d.status !== 'rejected'
                   && d.status !== 'none';
      if (live) {
        document.getElementById('ptxt').textContent = d.proposal  || '';
        document.getElementById('etxt').textContent = d.evidence  || '';
        root.classList.add('show');
        badge.style.background = 'var(--clay)';
      } else {
        root.classList.remove('show');
        badge.style.background = 'var(--moss)';
      }
    } catch(_) {}
  }

  async function fb(status) {
    root.classList.remove('show');
    badge.style.background = 'var(--moss)';
    try {
      await fetch('/feedback', {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: 'status=' + status + '&note='
      });
    } catch(_) {}
  }

  function tap() {
    root.classList.add('popping');
    setTimeout(() => root.classList.remove('popping'), 520);
    poll();
  }

  function toggleChat() {
    const cb = document.getElementById('chatbox');
    cb.style.display = cb.style.display === 'none' ? 'block' : 'none';
  }

  async function sendChat() {
    const inp = document.getElementById('chatinput');
    const finp = document.getElementById('chatfile');
    let txt = inp.value.trim();
    let displayTxt = txt;
    
    if (finp.files.length > 0) {
      try {
        const file = finp.files[0];
        const content = await file.text();
        txt += "\\n\\n[Attached File: " + file.name + "]\\n" + content;
        displayTxt += " [📎 " + file.name + "]";
        finp.value = "";
      } catch (e) {
        console.error("Failed to read file", e);
      }
    }
    
    if (!txt) return;
    inp.value = '';
    
    const log = document.getElementById('chatlog');
    const umsg = document.createElement('div');
    umsg.textContent = "You: " + displayTxt;
    umsg.style.alignSelf = "flex-end";
    umsg.style.color = "var(--moss)";
    log.appendChild(umsg);
    log.scrollTop = log.scrollHeight;

    try {
      const res = await fetch('/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: 'msg=' + encodeURIComponent(txt)
      }).then(r => r.json());

      const pmsg = document.createElement('div');
      pmsg.textContent = "Pip: " + (res.response || "...");
      pmsg.style.alignSelf = "flex-start";
      pmsg.style.fontWeight = "bold";
      log.appendChild(pmsg);
      log.scrollTop = log.scrollHeight;
    } catch(e) {}
  }

  poll();
  setInterval(poll, 30000);

  function closePip() {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.hide_window();
    } else {
      window.close();
    }
  }
</script>
</body>
</html>"""
    return html_str.replace("__SPRITE_HTML__", sprite_html)


class PipHandler(BaseHTTPRequestHandler):
    workspace_key = "garden_spiders"
    manifest_path = "approved_workspaces.json"

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")

    def send_json(self, payload: Any, status: int = 200) -> None:
        encoded = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def redirect_home(self) -> None:
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

    def read_body(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length else ""
        return parse_qs(body)

    def trace_dashboard_action(
        self,
        action: str,
        summary: str,
        status: str = "ok",
        details: dict[str, Any] | None = None,
    ) -> None:
        try:
            pip_traces.record_trace(
                kind="dashboard_action",
                actor="phone_dashboard",
                action=action,
                status=status,
                summary=summary,
                details={
                    "client": self.client_address[0] if self.client_address else "",
                    **(details or {}),
                },
                source="pip_control_panel",
                workspace=self.workspace_key,
                tags=["dashboard", action],
            )
        except Exception as exc:
            print(f"Trace write failed: {exc}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                status = export_control_status(self.workspace_key, self.manifest_path)
                encoded = page(status).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            elif parsed.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
            elif parsed.path == "/status":
                self.send_json(export_control_status(self.workspace_key, self.manifest_path))
            elif parsed.path == "/apps":
                import pip_evolution
                self.send_json(pip_evolution.load_apps())
            elif parsed.path == "/proposal/latest":
                status = export_control_status(self.workspace_key, self.manifest_path)
                self.send_json(status.get("latest_proposal") or {})
            elif parsed.path == "/memory/latest":
                status = export_control_status(self.workspace_key, self.manifest_path)
                self.send_json(status.get("latest_memory") or {})
            elif parsed.path == "/ambient/latest":
                status = export_control_status(self.workspace_key, self.manifest_path)
                self.send_json(status.get("ambient") or {})
            elif parsed.path == "/permissions":
                status = export_control_status(self.workspace_key, self.manifest_path)
                self.send_json(status.get("permissions") or {})
            elif parsed.path == "/scheduler/status":
                self.send_json(pip_scheduler.get_status())
            elif parsed.path == "/jobs":
                self.send_json(pip_jobs.list_jobs())
            elif parsed.path == "/app-skills":
                self.send_json(pip_app_skills.list_profiles())
            elif parsed.path == "/developer-shells":
                self.send_json(pip_app_skills.inspect_developer_shells())
            elif parsed.path == "/blender/recipes":
                self.send_json(pip_blender_recipes.list_recipes())
            elif parsed.path == "/token-governor":
                self.send_json(pip_token_guard.status())
            elif parsed.path == "/flow-master":
                self.send_json(pip_flow_master.inspect_flow_master())
            elif parsed.path == "/traces":
                self.send_json(pip_traces.inspect_traces(limit=50))
            elif parsed.path == "/system-manifest":
                self.send_json(pip_system_manifest.inspect_manifest(refresh=False))
            elif parsed.path == "/platform":
                self.send_json(pip_platform.feature_status())
            elif parsed.path == "/phone/status":
                self.send_json(get_phone_status())
            elif parsed.path == "/pc/status":
                self.send_json(get_pc_status())
            elif parsed.path == "/default-fairy":
                try:
                    with open("default_fairy.png", "rb") as f:
                        self.send_response(200)
                        self.send_header("Content-Type", "image/png")
                        self.send_header("Content-Length", str(Path("default_fairy.png").stat().st_size))
                        self.end_headers()
                        self.wfile.write(f.read())
                except Exception:
                    self.send_json({"error": "not found"}, status=404)
            elif parsed.path == "/avatar":
                from pathlib import Path
                avatar_path = None
                for ext in ["png", "jpg", "jpeg", "gif"]:
                    p = Path(f"avatar.{ext}")
                    if p.exists():
                        avatar_path = p
                        break
                if avatar_path:
                    self.send_response(200)
                    self.send_header("Content-Type", f"image/{avatar_path.suffix[1:]}")
                    self.send_header("Content-Length", str(avatar_path.stat().st_size))
                    self.end_headers()
                    with open(avatar_path, "rb") as f:
                        self.wfile.write(f.read())
                else:
                    self.send_json({"error": "not found"}, status=404)
            elif parsed.path == "/pip/latest":
                # Combined endpoint: workspace proposal OR phone proposal, whichever is active
                status = export_control_status(self.workspace_key, self.manifest_path)
                wp = status.get("latest_proposal") or {}
                phone = get_phone_status()
                phone_proposal = phone.get("proposal") or {}
                phone_card = phone_proposal.get("proposal_card") or phone_proposal
                pc = get_pc_status()
                pc_proposal = pc.get("proposal") or {}
                pc_card = pc_proposal.get("proposal_card") or pc_proposal
                # Prefer workspace proposal if it has text; fall back to phone
                if wp.get("proposal"):
                    self.send_json(wp)
                elif phone_card.get("proposal"):
                    self.send_json(phone_card)
                elif pc_card.get("proposal"):
                    self.send_json(pc_card)
                else:
                    self.send_json({})
            elif parsed.path == "/fairy":
                encoded = fairy_page().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            else:
                self.send_json({"error": "not found"}, status=404)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self.send_json({"error": str(exc)}, status=500)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/run-scan":
                draft_next_actions(self.workspace_key, self.manifest_path)
                self.trace_dashboard_action("run_scan", "Dashboard requested a workspace scan and next-action draft.")
                self.redirect_home()
            elif parsed.path == "/scheduler/pause":
                query = parse_qs(parsed.query)
                if "id" in query:
                    pip_scheduler.pause_job(query["id"][0])
                self.redirect_home()
            elif parsed.path == "/scheduler/resume":
                query = parse_qs(parsed.query)
                if "id" in query:
                    pip_scheduler.resume_job(query["id"][0])
                self.redirect_home()
            elif parsed.path == "/run-goal":
                form = self.read_body()
                goal_text = form.get("goal_text", [""])[0]
                trace_status = "empty"
                if goal_text:
                    assessment = pip_token_guard.assess_interaction(
                        goal_text,
                        intent="autonomous_goal",
                        source_type="first_hand",
                        source_name="Pip dashboard goal",
                    )
                    if assessment["allowed"]:
                        request_safety_permission(
                            "autonomous_goal",
                            title="Approve autonomous Pip goal",
                            rationale=goal_text,
                            workspace_key=self.workspace_key,
                            manifest_path=self.manifest_path,
                            details={"goal": goal_text, "source": "dashboard", "token_governor": assessment},
                        )
                        trace_status = "permission_requested"
                    else:
                        pip_token_guard.record_event(
                            "autonomous_goal",
                            estimated_tokens=assessment["estimated_tokens"],
                            actual_tokens=0,
                            saved_tokens=assessment["estimated_tokens"],
                            note=f"Blocked by Token Governor: {assessment['reason']}",
                        )
                        trace_status = "blocked"
                    self.trace_dashboard_action(
                        "run_goal",
                        "Dashboard submitted an autonomous goal for governor review.",
                        status=trace_status,
                        details={"goal": goal_text[:240], "allowed": assessment["allowed"]},
                    )
                self.redirect_home()
            elif parsed.path == "/nightwatch/start":
                request_safety_permission(
                    "nightwatch_start",
                    title="Approve Nightwatch sleep cycle",
                    rationale="Nightwatch starts a long-running background loop that may read memory files, call local models, and write dream/reflection memory.",
                    workspace_key=self.workspace_key,
                    manifest_path=self.manifest_path,
                    details={"source": "dashboard"},
                )
                self.trace_dashboard_action(
                    "nightwatch_start",
                    "Dashboard requested Nightwatch approval.",
                    status="permission_requested",
                )
                self.redirect_home()
            elif parsed.path == "/scripts/run":
                form = self.read_body()
                script_name = (form.get("script") or [""])[0]
                silent_val = (form.get("silent") or ["false"])[0].lower() == "true"
                if script_name:
                    request_safety_permission(
                        "efficiency_script",
                        title=f"Approve efficiency script: {script_name}",
                        rationale="Dashboard script execution can run local Python code and must be approved before it starts.",
                        workspace_key=self.workspace_key,
                        manifest_path=self.manifest_path,
                        details={"script": script_name, "silent": silent_val, "source": "dashboard"},
                    )
                    self.trace_dashboard_action(
                        "script_run",
                        "Dashboard requested script execution approval.",
                        status="permission_requested",
                        details={"script": script_name, "silent": silent_val},
                    )
                self.redirect_home()
            elif parsed.path == "/self-model/prune-belief":
                form = self.read_body()
                idx = _safe_form_int(form, "index")
                if idx >= 0:
                    import pip_self_model
                    import pip_finetune_curator
                    import pip_dynamic_prompt
                    
                    data = pip_self_model.load_self_model()
                    beliefs = data.get("beliefs", [])
                    if idx < len(beliefs):
                        bad_belief = beliefs[idx]
                        pip_self_model.remove_belief(idx)
                        
                        # Create lesson artifact
                        lesson_text = f"I previously believed: '{bad_belief}', but the user pruned this. I must learn from this mistake and avoid adopting similar beliefs."
                        pip_finetune_curator.append_interaction(
                            instruction=f"Evaluate this pruned belief: {bad_belief}",
                            system_prompt=pip_dynamic_prompt.generate_system_prompt(),
                            response_text=lesson_text,
                            source="user_correction"
                        )
                self.redirect_home()
            elif parsed.path == "/self-model/prune-rule":
                form = self.read_body()
                idx = _safe_form_int(form, "index")
                if idx >= 0:
                    import pip_self_model
                    import pip_finetune_curator
                    import pip_dynamic_prompt
                    
                    data = pip_self_model.load_self_model()
                    rules = data.get("learned_rules", [])
                    if idx < len(rules):
                        bad_rule = rules[idx]
                        pip_self_model.remove_rule(idx)
                        
                        # Create lesson artifact
                        lesson_text = f"I previously adopted the rule: '{bad_rule}', but the user rejected it. I must learn from this mistake."
                        pip_finetune_curator.append_interaction(
                            instruction=f"Evaluate this pruned rule: {bad_rule}",
                            system_prompt=pip_dynamic_prompt.generate_system_prompt(),
                            response_text=lesson_text,
                            source="user_correction"
                        )
                self.redirect_home()
            elif parsed.path == "/apps/scan":
                import pip_app_scanner
                pip_app_scanner.scan_and_save()
                self.trace_dashboard_action("apps_scan", "Dashboard scanned installed apps.")
                self.redirect_home()
            elif parsed.path == "/hardware/scan":
                import pip_hardware_scanner
                pip_hardware_scanner.scan_and_save(optimize=False)
                self.trace_dashboard_action("hardware_scan", "Dashboard scanned hardware.")
                self.redirect_home()
            elif parsed.path == "/developer-shells/bootstrap":
                pip_app_skills.bootstrap_developer_shells(write_personas=True)
                self.trace_dashboard_action("developer_shells_bootstrap", "Dashboard refreshed developer shell profiles.")
                self.redirect_home()
            elif parsed.path == "/flow-master/bootstrap":
                pip_flow_master.save_doctrine()
                self.trace_dashboard_action("flow_master_bootstrap", "Dashboard refreshed Flow Master doctrine.")
                self.redirect_home()
            elif parsed.path == "/flow-master/assess":
                form = self.read_body()
                content = (form.get("content") or [""])[0]
                if content:
                    assessment = pip_flow_master.assess_flow_pressure(
                        content,
                        intent="dashboard_flow_check",
                        source_type="first_hand",
                        source_name="Pip dashboard Flow Master",
                    )
                    self.trace_dashboard_action(
                        "flow_master_assess",
                        "Dashboard ran a Flow Master pressure check.",
                        status=assessment.get("flow_state", "ok").lower(),
                        details={"flow_state": assessment.get("flow_state"), "pressure": assessment.get("composite_threat_score")},
                    )
                self.redirect_home()
            elif parsed.path == "/system-manifest/refresh":
                pip_system_manifest.save_manifest()
                self.trace_dashboard_action("system_manifest_refresh", "Dashboard refreshed Pip's system map.")
                self.redirect_home()
            elif parsed.path == "/save-apps":
                form = self.read_body()
                import pip_evolution
                apps = pip_evolution.load_apps()
                for app in apps:
                    field_name = f"app_{app['name']}"
                    app['enabled'] = field_name in form
                pip_evolution.save_apps(apps)
                self.trace_dashboard_action("save_apps", "Dashboard saved approved app toggles.")
                self.redirect_home()
            elif parsed.path == "/select-folder":
                if not pip_platform.is_windows():
                    # Folder picking is Windows-only for now; config can still be edited directly.
                    self.redirect_home()
                    return
                import subprocess
                ps_script = """
Add-Type -AssemblyName System.windows.forms
$f = New-Object System.Windows.Forms.FolderBrowserDialog
$f.Description = "Select Pip's Memory Folder"
$f.ShowNewFolderButton = $true
if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
    Write-Output $f.SelectedPath
}
"""
                try:
                    out = subprocess.check_output(
                        ["powershell", "-NoProfile", "-Command", ps_script],
                        text=True,
                        **pip_platform.hidden_subprocess_kwargs(),
                    ).strip()
                    if out:
                        import pip_config
                        pip_config.set_memory_path(out)
                        self.trace_dashboard_action("select_folder", "Dashboard changed Pip memory folder.", details={"path": out})
                except Exception as e:
                    print(f"Folder selection error: {e}")
                self.redirect_home()
            elif parsed.path == "/run-ambient":
                context = "Phone-triggered Garden Spiders ambient cycle."
                assessment = pip_token_guard.assess_interaction(context, intent="ambient_cycle")
                if assessment["allowed"]:
                    run_ambient_cycle(self.workspace_key, 30, context, self.manifest_path)
                    pip_token_guard.record_event("ambient_cycle", estimated_tokens=assessment["estimated_tokens"])
                else:
                    pip_token_guard.record_event(
                        "ambient_cycle",
                        estimated_tokens=assessment["estimated_tokens"],
                        actual_tokens=0,
                        saved_tokens=assessment["estimated_tokens"],
                        note=f"Blocked by Token Governor: {assessment['reason']}",
                    )
                self.trace_dashboard_action(
                    "run_ambient",
                    "Dashboard requested an ambient cycle.",
                    status="ok" if assessment["allowed"] else "blocked",
                    details={"allowed": assessment["allowed"]},
                )
                self.redirect_home()
            elif parsed.path == "/schedule":
                queue_next_wake(self.workspace_key, 30, "Phone-scheduled Garden Spiders ambient cycle.", self.manifest_path)
                self.trace_dashboard_action("schedule", "Dashboard scheduled the next ambient wake.")
                self.redirect_home()
            elif parsed.path == "/feedback":
                form = self.read_body()
                status = (form.get("status") or [""])[0]
                note = (form.get("note") or [""])[0]
                record_feedback(self.workspace_key, status, note, self.manifest_path)
                self.trace_dashboard_action("feedback", "Dashboard recorded proposal feedback.", status=status or "ok")
                self.redirect_home()
            elif parsed.path == "/permission":
                form = self.read_body()
                request_id = (form.get("request_id") or [""])[0]
                decision = (form.get("decision") or [""])[0]
                note = (form.get("note") or [""])[0]
                resolved = resolve_permission(self.workspace_key, request_id, decision, note, self.manifest_path)
                if decision == "approved" and resolved.get("action_type") == "autonomous_goal":
                    goal_text = (resolved.get("details") or {}).get("goal") or resolved.get("rationale", "")
                    if goal_text:
                        pip_jobs.start_autonomous_goal(goal_text)
                elif decision == "approved" and resolved.get("action_type") == "nightwatch_start":
                    start_nightwatch_loop()
                elif decision == "approved" and resolved.get("action_type") == "efficiency_script":
                    details = resolved.get("details") or {}
                    script_name = details.get("script", "")
                    if script_name:
                        pip_background_tasks.run_script(script_name, silent=bool(details.get("silent")))
                self.trace_dashboard_action(
                    "permission",
                    "Dashboard resolved a permission request.",
                    status=decision or "ok",
                    details={"request_id": request_id, "action_type": resolved.get("action_type")},
                )
                self.redirect_home()
            elif parsed.path == "/jobs/stop":
                form = self.read_body()
                job_id = (form.get("job_id") or [""])[0]
                pip_jobs.request_stop(job_id)
                self.trace_dashboard_action("jobs_stop", "Dashboard requested a cooperative job stop.", details={"job_id": job_id})
                self.redirect_home()
            elif parsed.path == "/app-skills/award":
                form = self.read_body()
                pip_app_skills.award_app_xp(
                    (form.get("app") or ["Blender"])[0],
                    int((form.get("amount") or ["10"])[0]),
                    domain=(form.get("domain") or ["general"])[0],
                    evidence=(form.get("evidence") or [""])[0],
                )
                self.trace_dashboard_action("app_skills_award", "Dashboard awarded app skill XP.")
                self.redirect_home()
            elif parsed.path == "/blender/recipe-draft":
                form = self.read_body()
                recipe = (form.get("recipe") or ["simple_character_blockout"])[0]
                project = (form.get("project") or ["Blender practice"])[0]
                goal = (form.get("goal") or [""])[0]
                assessment = pip_token_guard.assess_interaction(
                    f"{project} {recipe} {goal}",
                    intent="blender_recipe",
                    source_type="first_hand",
                    source_name="Pip Blender Recipe Lab",
                )
                if assessment["allowed"]:
                    pip_blender_recipes.draft_recipe(recipe, project=project, goal=goal)
                    pip_token_guard.record_event("blender_recipe", estimated_tokens=assessment["estimated_tokens"])
                else:
                    pip_token_guard.record_event(
                        "blender_recipe",
                        estimated_tokens=assessment["estimated_tokens"],
                        actual_tokens=0,
                        saved_tokens=assessment["estimated_tokens"],
                        note=f"Blocked by Token Governor: {assessment['reason']}",
                    )
                self.trace_dashboard_action(
                    "blender_recipe_draft",
                    "Dashboard requested a Blender recipe draft.",
                    status="ok" if assessment["allowed"] else "blocked",
                    details={"recipe": recipe, "project": project, "allowed": assessment["allowed"]},
                )
                self.redirect_home()
            elif parsed.path == "/phone/usage-import":
                content_type = self.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    length = int(self.headers.get("Content-Length", "0"))
                    usage_json = self.rfile.read(length).decode("utf-8") if length else ""
                else:
                    form = self.read_body()
                    usage_json = (form.get("usage_json") or [""])[0]
                import_phone_usage_text(usage_json, "dashboard_upload.json", run_optimizer=True)
                self.trace_dashboard_action("phone_usage_import", "Dashboard imported phone usage JSON.")
                self.redirect_home()
            elif parsed.path == "/pc/usage-import":
                content_type = self.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    length = int(self.headers.get("Content-Length", "0"))
                    usage_json = self.rfile.read(length).decode("utf-8") if length else ""
                else:
                    form = self.read_body()
                    usage_json = (form.get("usage_json") or [""])[0]
                import_pc_usage_text(usage_json, "pc_dashboard_upload.json", run_optimizer=True)
                self.trace_dashboard_action("pc_usage_import", "Dashboard imported PC usage JSON.")
                self.redirect_home()
            elif parsed.path == "/phone/summary-import":
                form = self.read_body()
                summary_csv = (form.get("summary_csv") or [""])[0]
                import_manual_summary_text(summary_csv, "dashboard_manual_summary.csv")
                self.trace_dashboard_action("phone_summary_import", "Dashboard imported phone summary CSV.")
                self.redirect_home()
            elif parsed.path == "/phone/feedback":
                form = self.read_body()
                feedback = (form.get("feedback") or [""])[0]
                note = (form.get("note") or [""])[0]
                apply_phone_feedback(feedback, note)
                self.trace_dashboard_action("phone_feedback", "Dashboard recorded phone proposal feedback.", status=feedback or "ok")
                self.redirect_home()
            elif parsed.path == "/chat":
                form = self.read_body()
                msg = (form.get("msg") or [""])[0]
                assessment = pip_token_guard.assess_interaction(
                    msg,
                    intent="chat",
                    source_type="first_hand",
                    source_name="Pip dashboard chat",
                )
                if not assessment["allowed"]:
                    pip_token_guard.record_event(
                        "chat",
                        estimated_tokens=assessment["estimated_tokens"],
                        actual_tokens=0,
                        saved_tokens=assessment["estimated_tokens"],
                        note=f"Blocked by Token Governor: {assessment['reason']}",
                    )
                    self.send_json({"response": assessment["nudge"], "token_governor": assessment})
                    return
                from pip_engine import PipEngine
                engine = PipEngine()
                try:
                    response = engine.generate_chat_response(msg)
                except Exception:
                    response = "I'm having trouble processing that right now."
                pip_token_guard.record_event(
                    "chat",
                    estimated_tokens=assessment["estimated_tokens"],
                    actual_tokens=pip_token_guard.estimate_tokens(msg + response, assessment["max_output_tokens"]),
                )
                self.send_json({"response": response, "token_governor": assessment})
            elif parsed.path == "/revert-avatar":
                from pathlib import Path
                for ext in ["png", "jpg", "jpeg", "gif"]:
                    Path(f"avatar.{ext}").unlink(missing_ok=True)
                self.send_json({"status": "success"})
            elif parsed.path == "/upload-avatar":
                import base64
                from pathlib import Path
                import io
                length = int(self.headers.get("Content-Length", "0"))
                if length > 5 * 1024 * 1024:
                    self.send_json({"error": "avatar upload too large"}, status=413)
                    return
                body = self.rfile.read(length).decode("utf-8") if length else "{}"
                data = json.loads(body)
                b64_img = data.get("image", "")
                filename = data.get("filename", "avatar.png")
                
                raw_bytes = base64.b64decode(b64_img)
                
                # Apply vectorization/background removal if rembg is available
                try:
                    from rembg import remove
                    from PIL import Image
                    img = Image.open(io.BytesIO(raw_bytes))
                    out_img = remove(img)
                    out_io = io.BytesIO()
                    out_img.save(out_io, format="PNG")
                    raw_bytes = out_io.getvalue()
                    ext = "png"
                except ImportError:
                    print("rembg not available, saving original image")
                    ext = filename.split(".")[-1].lower()
                    if ext not in ["png", "jpg", "jpeg", "gif"]:
                        ext = "png"

                for old_ext in ["png", "jpg", "jpeg", "gif"]:
                    Path(f"avatar.{old_ext}").unlink(missing_ok=True)
                with open(f"avatar.{ext}", "wb") as f:
                    f.write(raw_bytes)
                self.send_json({"status": "success"})
            else:
                self.send_json({"error": "not found"}, status=404)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Pip's local phone-friendly control panel.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--workspace", default="garden_spiders")
    parser.add_argument("--manifest", default="approved_workspaces.json")
    args = parser.parse_args()

    load_workspace(args.workspace, args.manifest)
    PipHandler.workspace_key = args.workspace
    PipHandler.manifest_path = args.manifest
    server = QuietThreadingHTTPServer((args.host, args.port), PipHandler)
    ip = local_ip()
    print("Pip control panel running.")
    print(f"Laptop URL: http://127.0.0.1:{args.port}")
    print(f"Phone URL on same Wi-Fi: http://{ip}:{args.port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
