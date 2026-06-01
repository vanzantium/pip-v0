#!/usr/bin/env python3
from __future__ import annotations

import json
import importlib.util
import hashlib
import sys
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

import pip_platform

if TYPE_CHECKING:
    import argparse
    from pip_skills import SkillSpec


BUILTIN_TRUSTED_PACKAGES = {"brain_io"}


def _manifest_hash(manifest_path: Path) -> str:
    return hashlib.sha256(manifest_path.read_bytes()).hexdigest()


def _is_trusted_package(skill_folder: Path, manifest: dict[str, Any]) -> bool:
    return skill_folder.name in BUILTIN_TRUSTED_PACKAGES


def _load_entrypoint(skill_folder: Path, manifest: dict[str, Any]):
    module_name = f"pip_skill_dynamic_{skill_folder.name}"
    entrypoint = manifest.get("entrypoint", "run.py")
    entrypoint_path = (skill_folder / entrypoint).resolve()
    if not entrypoint_path.exists() or not entrypoint_path.is_relative_to(skill_folder.resolve()):
        raise FileNotFoundError(f"Entrypoint {entrypoint_path} not found for skill package {skill_folder.name}")

    spec = importlib.util.spec_from_file_location(module_name, str(entrypoint_path))
    if not spec or not spec.loader:
        raise RuntimeError(f"Could not load skill package {skill_folder.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    if not hasattr(module, "run") or not callable(module.run):
        raise RuntimeError(f"Skill package {skill_folder.name} missing run(args) function")
    return module


def _lazy_runner(skill_folder: Path, manifest: dict[str, Any]) -> Callable[[argparse.Namespace], dict[str, Any]]:
    def run(args: argparse.Namespace) -> dict[str, Any]:
        module = _load_entrypoint(skill_folder, manifest)
        return module.run(args)

    return run


def load_portable_skills() -> dict[str, tuple[SkillSpec, Callable[[argparse.Namespace], dict[str, Any]]]]:
    from pip_skills import SkillSpec
    
    skills_dir = pip_platform.ROOT / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    
    loaded_skills = {}
    
    for skill_folder in skills_dir.iterdir():
        if not skill_folder.is_dir():
            continue
            
        manifest_path = skill_folder / "skill.json"
        if not manifest_path.exists():
            continue
            
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)

            if not _is_trusted_package(skill_folder, manifest):
                print(f"[pip_skill_registry] Skipping untrusted portable skill package {skill_folder.name}")
                continue

            lazy_runner = _lazy_runner(skill_folder, manifest)
            if "skills" in manifest and isinstance(manifest["skills"], dict):
                for skill_id, skill_data in manifest["skills"].items():
                    name = skill_data.get("name", skill_id)
                    skill_spec = SkillSpec(
                        name=name,
                        description=skill_data.get("description", ""),
                        inputs=skill_data.get("inputs", []),
                        outputs=skill_data.get("outputs", []),
                        permissions=skill_data.get("permissions", []),
                    )
                    loaded_skills[name] = (skill_spec, lazy_runner)
            else:
                name = manifest.get("name", skill_folder.name)
                skill_spec = SkillSpec(
                    name=name,
                    description=manifest.get("description", "A portable skill."),
                    inputs=manifest.get("inputs", []),
                    outputs=manifest.get("outputs", []),
                    permissions=manifest.get("permissions", []),
                )
                loaded_skills[name] = (skill_spec, lazy_runner)
                    
        except Exception as e:
            print(f"[pip_skill_registry] Error loading skill package from {skill_folder}: {e}")
            
    return loaded_skills

def list_skill_packages() -> dict[str, Any]:
    skills_dir = pip_platform.ROOT / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    
    packages = []
    for skill_folder in skills_dir.iterdir():
        if skill_folder.is_dir() and (skill_folder / "skill.json").exists():
            try:
                with open(skill_folder / "skill.json", "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                trusted = _is_trusted_package(skill_folder, manifest)
                manifest_sha256 = _manifest_hash(skill_folder / "skill.json")
                
                # Support multi-skill manifests
                if "skills" in manifest:
                    names = list(manifest["skills"].keys())
                    desc = f"Package with {len(names)} skills: {', '.join(names)}"
                    perms = set()
                    for s in manifest["skills"].values():
                        for p in s.get("permissions", []):
                            perms.add(p)
                    
                    packages.append({
                        "folder": skill_folder.name,
                        "name": skill_folder.name,
                        "description": desc,
                        "permissions": list(perms),
                        "has_readme": (skill_folder / "SKILL.md").exists(),
                        "trusted": trusted,
                        "loadable": trusted,
                        "manifest_sha256": manifest_sha256,
                    })
                else:
                    packages.append({
                        "folder": skill_folder.name,
                        "name": manifest.get("name"),
                        "description": manifest.get("description"),
                        "permissions": manifest.get("permissions", []),
                        "has_readme": (skill_folder / "SKILL.md").exists(),
                        "trusted": trusted,
                        "loadable": trusted,
                        "manifest_sha256": manifest_sha256,
                    })
            except Exception:
                pass
                
    return {
        "skill": "list_skill_packages",
        "skills_dir": str(skills_dir),
        "packages": packages
    }
