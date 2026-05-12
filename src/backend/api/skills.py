import os
import json
import yaml
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException

router = APIRouter()

SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills_config.json")


def load_skills_config() -> Dict[str, Any]:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_skills_config(config: Dict[str, Any]):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def load_skill_yaml(skill_name: str) -> Dict[str, Any]:
    for ext in (".yml", ".yaml"):
        filepath = os.path.join(SKILLS_DIR, f"{skill_name}{ext}")
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    return {}


@router.get("/skills")
def list_skills():
    if not os.path.isdir(SKILLS_DIR):
        return []

    skills_config = load_skills_config()
    result = []

    for filename in os.listdir(SKILLS_DIR):
        if not filename.endswith((".yml", ".yaml")):
            continue
        filepath = os.path.join(SKILLS_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                skill_data = yaml.safe_load(f)
            if skill_data and "name" in skill_data:
                name = skill_data["name"]
                enabled = skills_config.get(name, {}).get("enabled", True)
                result.append({
                    "name": name,
                    "description": skill_data.get("description", ""),
                    "enabled": enabled,
                })
        except Exception:
            continue

    result.sort(key=lambda x: str(x["name"]))
    return result


@router.put("/skills/{skill_name}")
def update_skill(skill_name: str, payload: Dict[str, Any]):
    skill_yaml = load_skill_yaml(skill_name)
    if not skill_yaml:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

    skills_config = load_skills_config()
    if skill_name not in skills_config:
        skills_config[skill_name] = {}

    if "enabled" in payload:
        skills_config[skill_name]["enabled"] = bool(payload["enabled"])

    if "parameters" in payload and isinstance(payload["parameters"], dict):
        for key, value in payload["parameters"].items():
            if key in skill_yaml.get("parameters", {}):
                if "parameters" not in skills_config[skill_name]:
                    skills_config[skill_name]["parameters"] = {}
                skills_config[skill_name]["parameters"][key] = value

    save_skills_config(skills_config)
    return {"name": skill_name, "enabled": skills_config[skill_name].get("enabled", True)}


@router.get("/skills/{skill_name}/yaml")
def get_skill_yaml(skill_name: str):
    skill_yaml = load_skill_yaml(skill_name)
    if not skill_yaml:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

    filepath = os.path.join(SKILLS_DIR, f"{skill_name}.yml")
    if not os.path.exists(filepath):
        filepath = os.path.join(SKILLS_DIR, f"{skill_name}.yaml")

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    return {"name": skill_name, "yaml": content}


@router.put("/skills/{skill_name}/yaml")
def update_skill_yaml(skill_name: str, payload: Dict[str, Any]):
    skill_yaml = load_skill_yaml(skill_name)
    if not skill_yaml:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

    yaml_content = payload.get("yaml", "")
    if not yaml_content:
        raise HTTPException(status_code=400, detail="YAML content is required")

    try:
        parsed = yaml.safe_load(yaml_content)
        if not parsed or "name" not in parsed:
            raise ValueError("Invalid YAML: missing 'name' field")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")

    filepath = os.path.join(SKILLS_DIR, f"{skill_name}.yml")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(yaml_content)

    return {"name": skill_name, "message": "Skill YAML updated successfully"}


@router.post("/skills")
def create_skill(payload: Dict[str, Any]):
    name = payload.get("name", "").strip()
    description = payload.get("description", "").strip()
    yaml_content = payload.get("yaml", "")

    if not name:
        raise HTTPException(status_code=400, detail="Skill name is required")

    if not all(c.isalnum() or c == '_' for c in name):
        raise HTTPException(status_code=400, detail="Skill name can only contain alphanumeric characters and underscores")

    existing = load_skill_yaml(name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Skill '{name}' already exists")

    if yaml_content:
        try:
            parsed = yaml.safe_load(yaml_content)
            if not parsed:
                raise ValueError("Invalid YAML")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")
    else:
        yaml_content = f"name: {name}\ndescription: {description}\nparameters: {{}}\n"

    filepath = os.path.join(SKILLS_DIR, f"{name}.yml")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(yaml_content)

    skills_config = load_skills_config()
    skills_config[name] = {"enabled": True}
    save_skills_config(skills_config)

    return {"name": name, "description": description, "enabled": True}


@router.delete("/skills/{skill_name}")
def delete_skill(skill_name: str):
    skill_yaml = load_skill_yaml(skill_name)
    if not skill_yaml:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

    filepath = os.path.join(SKILLS_DIR, f"{skill_name}.yml")
    if not os.path.exists(filepath):
        filepath = os.path.join(SKILLS_DIR, f"{skill_name}.yaml")

    os.remove(filepath)

    skills_config = load_skills_config()
    if skill_name in skills_config:
        del skills_config[skill_name]
        save_skills_config(skills_config)

    return {"name": skill_name, "message": "Skill deleted successfully"}
