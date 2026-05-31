#!/usr/bin/env python3
from __future__ import annotations

import json
import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

import pip_platform

if TYPE_CHECKING:
    import argparse
    from pip_skills import SkillSpec


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
                
            # Dynamically import the entrypoint module
            module_name = f"pip_skill_dynamic_{skill_folder.name}"
            entrypoint = manifest.get("entrypoint", "run.py")
            entrypoint_path = skill_folder / entrypoint
            
            if not entrypoint_path.exists():
                print(f"[pip_skill_registry] Warning: Entrypoint {entrypoint_path} not found for skill package {skill_folder.name}")
                continue
                
            spec = importlib.util.spec_from_file_location(module_name, str(entrypoint_path))
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                
                # Check if it's a multi-skill package or a single skill
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
                        # We pass 'args' to module.run(args)
                        loaded_skills[name] = (skill_spec, module.run)
                else:
                    # Single skill fallback
                    name = manifest.get("name", skill_folder.name)
                    if hasattr(module, "run") and callable(module.run):
                        skill_spec = SkillSpec(
                            name=name,
                            description=manifest.get("description", "A portable skill."),
                            inputs=manifest.get("inputs", []),
                            outputs=manifest.get("outputs", []),
                            permissions=manifest.get("permissions", []),
                        )
                        loaded_skills[name] = (skill_spec, module.run)
                    else:
                        print(f"[pip_skill_registry] Warning: Skill {name} missing run(args) function in {entrypoint}")
                    
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
                        "has_readme": (skill_folder / "SKILL.md").exists()
                    })
                else:
                    packages.append({
                        "folder": skill_folder.name,
                        "name": manifest.get("name"),
                        "description": manifest.get("description"),
                        "permissions": manifest.get("permissions", []),
                        "has_readme": (skill_folder / "SKILL.md").exists()
                    })
            except Exception:
                pass
                
    return {
        "skill": "list_skill_packages",
        "skills_dir": str(skills_dir),
        "packages": packages
    }
