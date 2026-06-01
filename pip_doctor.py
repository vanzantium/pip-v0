#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path


REQUIRED_FILES = [
    "pip_engine.py",
    "generate_synthetic_usage.py",
    "run_demo.py",
    "run_scenario_pack.py",
    "test_scenarios.py",
    "pip_skills.py",
    "pip_phone_bridge.py",
    "pip_workspace.py",
    "pip_control_panel.py",
    "pip_safety.py",
    "pip_jobs.py",
    "pip_app_skills.py",
    "pip_blender_recipes.py",
    "pip_flow_master.py",
    "pip_traces.py",
    "pip_task_runs.py",
    "pip_system_manifest.py",
    "pip_scheduler.py",
    "pip_background_tasks.py",
    "pip_dynamic_prompt.py",
    "pip_embeddings.py",
    "pip_finetune_curator.py",
    "pip_model_registry.py",
    "pip_self_model.py",
    "pip_self_reflection.py",
    "pip_skill_registry.py",
    "pip_token_guard.py",
    "pip_platform.py",
    "pip_goal_engine.py",
    "pip_pc_bridge.py",
    "pip_pc_tracker.py",
    "pip_hardware_scanner.py",
    "pip_fairy_window.py",
    "approved_workspaces.json",
    "README.md",
    "S25_ROADMAP.md",
    "DEPLOYMENT_OPTIONS.md",
    "ANDROID_TELEMETRY_SCHEMA.md",
    "HERMES_OPENMYTHOS_COMPARISON.md",
    "OPENJARVIS_COMPARISON.md",
    "ODYSSEUS_COMPARISON.md",
    "SECURITY.md",
]


def check_json(path: Path) -> tuple[bool, str]:
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, str(exc)
    return True, "ok"


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Pip v0 project health.")
    parser.add_argument("--root", default=".", help="Pip v0 project root")
    parser.add_argument("--scenarios", default="scenarios", help="Scenario directory relative to root")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    failures: list[str] = []

    for filename in REQUIRED_FILES:
        if not (root / filename).exists():
            failures.append(f"missing required file: {filename}")

    with tempfile.TemporaryDirectory() as compile_cache:
        compile_cache_path = Path(compile_cache)
        for path in root.glob("*.py"):
            try:
                py_compile.compile(
                    str(path),
                    cfile=str(compile_cache_path / f"{path.stem}.pyc"),
                    doraise=True,
                )
            except py_compile.PyCompileError as exc:
                failures.append(f"python compile failed for {path.name}: {exc.msg}")
            except OSError as exc:
                failures.append(f"python compile failed for {path.name}: {exc}")

    scenario_dir = root / args.scenarios
    if scenario_dir.exists():
        scenario_files = [
            path for path in scenario_dir.glob("*.json")
            if path.name != "manifest.json" and not path.name.endswith(".memory.json")
        ]
        if not scenario_files:
            failures.append("scenario directory exists but contains no scenario JSON files")
        for path in scenario_files:
            ok, message = check_json(path)
            if not ok:
                failures.append(f"invalid JSON in {path.name}: {message}")
    else:
        failures.append(f"missing scenario directory: {args.scenarios}")

    test_script = root / "test_scenarios.py"
    if test_script.exists() and scenario_dir.exists():
        result = subprocess.run(
            [sys.executable, str(test_script), "--scenarios", str(scenario_dir)],
            cwd=str(root),
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            output = (result.stdout + result.stderr).strip()
            failures.append(f"scenario assertions failed: {output}")

    try:
        sys.path.insert(0, str(root))
        from pip_workspace import classify_action_permission

        for action_type in [
            "autonomous_goal",
            "arbitrary_python",
            "ui_automation",
            "keyboard_recording",
            "system_optimization",
        ]:
            classification = classify_action_permission(action_type)
            if classification.get("tier") != "requires_permission":
                failures.append(f"{action_type} should require permission")
    except Exception as exc:
        failures.append(f"permission policy check failed: {exc}")

    try:
        control_source = (root / "pip_control_panel.py").read_text(encoding="utf-8")
        if control_source.count('elif parsed.path == "/save-apps"') != 1:
            failures.append("dashboard should define exactly one /save-apps POST route")
        if 'Path("PipMemory") / "apps.json"' in control_source:
            failures.append("dashboard should use configured memory path, not hard-coded PipMemory/apps.json")
        if 'creationflags=0x08000000' in control_source:
            failures.append("dashboard should use pip_platform.hidden_subprocess_kwargs for hidden Windows processes")
        if 'Dashboard started Nightwatch background loop.' in control_source:
            failures.append("dashboard should request approval before starting Nightwatch")
        if 'Dashboard ran efficiency script.' in control_source:
            failures.append("dashboard should request approval before running efficiency scripts")
        if "/task-runs" not in control_source:
            failures.append("dashboard should expose task-run receipts at /task-runs")
        if "validate_post_token" not in control_source or "_pip_token" not in control_source:
            failures.append("dashboard POST routes should require a per-server token")
        if 'parsed.path == "/system/enable-startup"' in control_source and "request_safety_permission(\n                    \"enable_startup\"" not in control_source:
            failures.append("dashboard startup enable should be permission-gated")
    except Exception as exc:
        failures.append(f"dashboard source consistency check failed: {exc}")

    try:
        dashboard_template = (root / "dashboard_ui" / "template.html").read_text(encoding="utf-8")
        if "Task Run Receipts" not in dashboard_template:
            failures.append("dashboard should render task-run receipts")
        if "_pip_token" not in dashboard_template:
            failures.append("dashboard forms should include token injection")
    except Exception as exc:
        failures.append(f"dashboard template consistency check failed: {exc}")

    try:
        workspace_source = (root / "pip_workspace.py").read_text(encoding="utf-8")
        if "DEBUG:" in workspace_source:
            failures.append("workspace path resolution should not print DEBUG lines during normal use")
    except Exception as exc:
        failures.append(f"workspace source consistency check failed: {exc}")

    try:
        import pip_platform
        platform_status = pip_platform.feature_status()
        required_feature_keys = {"control_panel", "token_governor", "hardware_scan", "installed_app_scan"}
        missing = required_feature_keys.difference(platform_status.get("features", {}))
        if missing:
            failures.append(f"platform feature status missing keys: {sorted(missing)}")
    except Exception as exc:
        failures.append(f"platform compatibility check failed: {exc}")

    try:
        skill_registry_source = (root / "pip_skill_registry.py").read_text(encoding="utf-8")
        if "_lazy_runner" not in skill_registry_source or "BUILTIN_TRUSTED_PACKAGES" not in skill_registry_source:
            failures.append("portable skills should be manifest-listed and lazily imported from trusted packages only")
        if "spec.loader.exec_module(module)" in skill_registry_source.split("def load_portable_skills", 1)[-1].split("def list_skill_packages", 1)[0]:
            failures.append("load_portable_skills should not execute portable skill code during CLI startup")
    except Exception as exc:
        failures.append(f"portable skill registry consistency check failed: {exc}")

    try:
        import pip_app_skills
        import pip_skills
        import pip_skill_registry

        if "list_skill_packages" not in pip_skills.SKILLS:
            failures.append("list_skill_packages handler should be registered in SKILLS")
        packages = pip_skill_registry.list_skill_packages().get("packages", [])
        package_names = {package.get("name") or package.get("folder") for package in packages}
        if "dummy_portable_skill" in package_names or "dummy_skill" in package_names:
            failures.append("dummy portable skill should not be exposed in production skill registry")

        shells = pip_app_skills.inspect_developer_shells().get("shells", [])
        shell_names = {shell.get("name") for shell in shells}
        expected_shells = {"Codex", "Claude Code", "Antigravity"}
        missing_shells = expected_shells.difference(shell_names)
        if missing_shells:
            failures.append(f"developer shell registry missing: {sorted(missing_shells)}")
        for shell in shells:
            if shell.get("name") in expected_shells and shell.get("safety_mode") != "approval_required_for_ui_handoff":
                failures.append(f"{shell.get('name')} shell should be UI-handoff approval gated")
    except Exception as exc:
        failures.append(f"developer shell consistency check failed: {exc}")

    try:
        import pip_flow_master
        flow = pip_flow_master.inspect_flow_master()
        if flow.get("contract") != "ingest -> validate -> transform -> emit":
            failures.append("Flow Master contract should be ingest -> validate -> transform -> emit")
        if not flow.get("source_exists"):
            failures.append("Flow Master source folder should exist under the brain folder")
        boundaries = " ".join(flow.get("safety_boundaries", []))
        if "does not block apps" not in boundaries and "No keyboard" not in boundaries:
            failures.append("Flow Master v0 should document safe non-invasive boundaries")
        sample = pip_flow_master.assess_flow_pressure(
            "This is urgent, everyone must act now before it is too late.",
            source_name="Pip doctor Flow Master sample",
            record=False,
        )
        if sample.get("flow_state") not in {"AUDIT", "DWELL", "SHED"}:
            failures.append("Flow Master should escalate high-pressure sample text")
    except Exception as exc:
        failures.append(f"Flow Master consistency check failed: {exc}")

    try:
        import pip_config
        import pip_traces
        import pip_task_runs
        import pip_system_manifest

        original_memory_path = pip_config.get_memory_path
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            pip_config.get_memory_path = lambda: temp_root
            trace = pip_traces.record_trace(
                "doctor_check",
                actor="pip_doctor",
                action="trace_roundtrip",
                summary="Doctor trace spine roundtrip.",
            )
            trace_status = pip_traces.inspect_traces(limit=3)
            latest_ids = {event.get("id") for event in trace_status.get("latest", [])}
            if trace.get("id") not in latest_ids:
                failures.append("trace spine should return the event it just wrote")
            task_run = pip_task_runs.start_task_run(
                "doctor_check",
                "task_run_roundtrip",
                summary="Doctor task-run receipt roundtrip.",
                source="pip_doctor",
            )
            pip_task_runs.finish_task_run(
                task_run["id"],
                "doctor_check",
                "task_run_roundtrip",
                "completed",
                summary="Doctor task-run receipt completed.",
                source="pip_doctor",
            )
            task_run_status = pip_task_runs.inspect_task_runs(limit=5)
            task_run_ids = {event.get("id") for event in task_run_status.get("latest", [])}
            if task_run["id"] not in task_run_ids:
                failures.append("task-run receipts should return the run they just wrote")
            if not task_run_status.get("bounded_read"):
                failures.append("task-run inspection should use bounded reads")
            manifest = pip_system_manifest.save_manifest()
            primitives = manifest.get("primitives", {})
            for primitive in ["skills", "workspace_loop", "control_panel", "trace_spine", "task_runs", "governors"]:
                if primitive not in primitives:
                    failures.append(f"system manifest missing primitive: {primitive}")
            if not (temp_root / "pip_system_manifest.json").exists():
                failures.append("system manifest should write to configured memory folder")
        pip_config.get_memory_path = original_memory_path
    except Exception as exc:
        failures.append(f"trace/system manifest consistency check failed: {exc}")
    finally:
        try:
            pip_config.get_memory_path = original_memory_path
        except Exception:
            pass

    try:
        import pip_model_registry
        registry_status = pip_model_registry.inspect_registry()
        if not registry_status.get("fit_examples"):
            failures.append("model registry should expose fit examples")
        if pip_model_registry.available_vram_mb() < 0:
            failures.append("model registry VRAM estimate should never be negative")
        route = pip_model_registry.run_route(argparse.Namespace(task_type="coding"))
        if not route.get("recommended_model") or not route.get("candidates"):
            failures.append("model registry should return a recommendation and scored candidates")
        if "score" not in route["candidates"][0]:
            failures.append("model registry candidates should include fit scores")
    except Exception as exc:
        failures.append(f"model registry consistency check failed: {exc}")

    try:
        app_scanner_source = (root / "pip_app_scanner.py").read_text(encoding="utf-8")
        if 'shell_entry["enabled"] = True' in app_scanner_source or '"Cursor", "enabled": True' in app_scanner_source:
            failures.append("app scanner should suggest developer tools instead of auto-enabling them")
    except Exception as exc:
        failures.append(f"app scanner consistency check failed: {exc}")

    try:
        import pip_config
        import pip_token_guard
        import pip_jobs

        original_memory_path = pip_config.get_memory_path
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            pip_config.get_memory_path = lambda: temp_root
            status = pip_token_guard.record_event(
                "blocked_doctor",
                estimated_tokens=1000,
                actual_tokens=0,
                saved_tokens=1000,
                note="doctor blocked-accounting check",
            )
            if status["daily_used_tokens"] != 0 or status["daily_saved_tokens"] != 1000:
                failures.append("blocked token-governor events should save tokens without spending them")
            if pip_jobs.request_stop("missing-job").get("ok"):
                failures.append("stopping an unknown job should not succeed")
            if (temp_root / "jobs" / "missing-job.stop").exists():
                failures.append("stopping an unknown job should not create an orphan stop file")
        pip_config.get_memory_path = original_memory_path
    except Exception as exc:
        failures.append(f"token governor/job consistency check failed: {exc}")
    finally:
        try:
            pip_config.get_memory_path = original_memory_path
        except Exception:
            pass

    if failures:
        print("Pip doctor found issues:")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)

    print("Pip doctor passed.")


if __name__ == "__main__":
    main()
