import os
import json
import yaml
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException

router = APIRouter()

# 获取当前文件所在目录的上两级目录，然后拼接一个叫 skills 的文件夹路径
SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")
# 获取当前文件所在目录的上两级目录，然后拼接一个叫 skills_config.json 的配置文件路径
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills", "skills_config.json")

def load_skills_config() -> Dict[str, Any]:
    """
    加载技能配置文件 skills_config.json 的内容。

    输入:
        无

    输出:
        Dict[str, Any]: 解析后的JSON对象，若文件不存在或解析失败则返回空字典。

    中间过程:
        1. 检查 CONFIG_FILE 是否存在。
        2. 若存在则以UTF-8编码打开并调用 json.load 解析。
        3. 若出现异常（文件不存在或JSON格式错误），捕获异常并忽略，返回空字典。
    """
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_skills_config(config: Dict[str, Any]):
    """
    将技能配置保存到 skills_config.json 文件。

    输入:
        config (Dict[str, Any]): 要保存的配置字典。

    输出:
        无（直接写入文件）

    中间过程:
        1. 以UTF-8编码打开 CONFIG_FILE 文件（写模式）。
        2. 使用 json.dump 将配置写入文件，设置缩进为2，不转义非ASCII字符。
    """
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def load_skill_yaml(skill_name: str) -> Dict[str, Any]:
    """
    根据技能名称加载对应的 YAML 文件内容。

    输入:
        skill_name (str): 技能名称（不含扩展名）。

    输出:
        Dict[str, Any]: 解析后的YAML数据，若文件不存在或解析失败则返回空字典。

    中间过程:
        1. 遍历扩展名列表 (".yml", ".yaml")。
        2. 拼接完整文件路径 SKILLS_DIR/{skill_name}{ext}。
        3. 若文件存在，则打开并以UTF-8读取，用 yaml.safe_load 解析。
        4. 若解析结果为空则返回空字典，否则返回解析后的字典。
        5. 若文件均不存在则返回空字典。
    """
    for ext in (".yml", ".yaml"):
        filepath = os.path.join(SKILLS_DIR, f"{skill_name}{ext}")
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    return {}

@router.get("/skills")
def list_skills():
    """
    列出所有技能的基本信息。

    输入:
        无（通过查询参数？不需要）

    输出:
        List[Dict]: 技能列表，每个元素包含 name, description, enabled 字段。

    中间过程:
        1. 检查 SKILLS_DIR 是否存在且为目录，若不存在则返回空列表。
        2. 加载 skills_config.json 配置。
        3. 遍历 SKILLS_DIR 下所有以 .yml 或 .yaml 结尾的文件。
        4. 对每个文件尝试用 yaml.safe_load 解析。
        5. 若解析成功且包含 "name" 字段，则读取 enabled 状态（默认 True）。
        6. 将技能信息追加到结果列表。
        7. 按 name 字段排序后返回。
    """
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
    """
    更新技能的启用状态或参数。

    输入:
        skill_name (str): 路径参数，技能名称。
        payload (Dict[str, Any]): 请求体，可包含 "enabled" (bool) 和 "parameters" (dict)。

    输出:
        Dict: 包含 name 和 enabled 状态的字典。

    中间过程:
        1. 调用 load_skill_yaml 检查技能 YAML 文件是否存在，不存在则返回404。
        2. 加载现有 skills_config。
        3. 若技能名不在配置中，则初始化空字典。
        4. 若 payload 包含 "enabled"，则更新配置中的 enabled 状态。
        5. 若 payload 包含 "parameters"，则遍历其中每一项：
           - 检查该参数是否在 YAML 的 parameters 中定义（安全限制）。
           - 若存在，则更新配置中的对应参数值。
        6. 调用 save_skills_config 保存配置。
        7. 返回技能名称及最新的启用状态。
    """
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
    """
    获取指定技能的原始 YAML 文件内容。

    输入:
        skill_name (str): 路径参数，技能名称。

    输出:
        Dict: 包含 name 和 yaml 字符串的字典。

    中间过程:
        1. 调用 load_skill_yaml 检查技能是否存在，不存在则返回404。
        2. 尝试拼接 .yml 路径，若不存在则尝试 .yaml。
        3. 以UTF-8读取文件全部内容。
        4. 返回技能名称和 YAML 内容字符串。
    """
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
    """
    更新指定技能的 YAML 文件内容。

    输入:
        skill_name (str): 路径参数，技能名称。
        payload (Dict[str, Any]): 请求体，必须包含 "yaml" 字段。

    输出:
        Dict: 包含 name 和成功消息的字典。

    中间过程:
        1. 调用 load_skill_yaml 检查技能是否存在，不存在则返回404。
        2. 从 payload 中获取 yaml 内容，若为空则返回400错误。
        3. 尝试用 yaml.safe_load 验证 YAML 格式，并确保包含 "name" 字段。
        4. 若验证失败则返回400错误，包含具体异常信息。
        5. 将新内容写入 .yml 文件（覆盖）。
        6. 返回成功消息。
    """
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
    """
    创建一个新的技能。

    输入:
        payload (Dict[str, Any]): 请求体，包含:
            - name (str): 技能名称（必需）。
            - description (str): 描述（可选）。
            - yaml (str): 完整 YAML 内容（可选，若不提供则自动生成基础模板）。

    输出:
        Dict: 包含 name, description, enabled 的字典。

    中间过程:
        1. 提取并去除首尾空格的 name，若为空则返回400。
        2. 校验 name 只包含字母数字和下划线，否则返回400。
        3. 调用 load_skill_yaml 检查是否已存在同名技能，若存在则返回409冲突。
        4. 若提供了 yaml 内容，则尝试用 yaml.safe_load 验证格式；若未提供则生成基础模板字符串。
        5. 将内容写入文件 SKILLS_DIR/{name}.yml。
        6. 加载 skills_config，为新技能设置 enabled: True，并保存配置。
        7. 返回新技能的信息。
    """
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
    """
    删除指定的技能（删除 YAML 文件并从配置中移除）。

    输入:
        skill_name (str): 路径参数，技能名称。

    输出:
        Dict: 包含 name 和删除成功消息的字典。

    中间过程:
        1. 调用 load_skill_yaml 检查技能是否存在，不存在则返回404。
        2. 尝试构建 .yml 路径，若不存在则尝试 .yaml。
        3. 调用 os.remove 删除该文件。
        4. 加载 skills_config，若存在该技能配置则删除并保存。
        5. 返回删除成功消息。
    """
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