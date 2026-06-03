"""配置加载与自动生成模块。"""
import json
import os
import sys

_CONFIG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_PATH = os.path.join(_CONFIG_DIR, "roco-merchant.json")

DEFAULT_CONFIG = {
    "api": {
        "url": "https://wegame.shallow.ink/api/v1/games/rocom/merchant/info",
        "key": "",
    },
    "push": {
        "title": "📢 远行商人",
        "hitokoto": False,
    },
}


def _get_config_path():
    """获取配置文件路径（环境变量优先）。"""
    return os.getenv("ROCOM_CONFIG_PATH", _DEFAULT_PATH)


def _generate_config(path: str):
    """生成默认配置文件。"""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        print(f"配置文件已生成: {path}")
    except PermissionError:
        print(f"无权限创建配置文件 {path}")
    except Exception as e:
        print(f"创建配置文件 {path} 失败: {e}")


def load_config() -> dict:
    """加载配置，按优先级合并：环境变量 > 配置文件 > 默认模板。"""
    config_path = _get_config_path()
    file_config = {}

    # 读取配置文件
    if not os.path.exists(config_path):
        _generate_config(config_path)
    else:
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                file_config = json.load(f)
        except json.JSONDecodeError as e:
            print(f"配置文件 {config_path} JSON 格式错误: {e}，使用默认配置")
        except Exception as e:
            print(f"读取配置文件 {config_path} 失败: {e}，使用默认配置")

    if not isinstance(file_config, dict):
        file_config = {}

    # 深度合并：默认配置 → 文件配置 → 环境变量覆盖
    config = _deep_merge(DEFAULT_CONFIG, file_config)

    # 环境变量覆盖 api.key
    env_key = os.getenv("ROCOM_API_KEY")
    if env_key:
        config.setdefault("api", {})["key"] = env_key

    api_key = config.get("api", {}).get("key", "")
    if not api_key:
        print("api.key 未配置，请设置 ROCOM_API_KEY 环境变量或编辑配置文件")

    return config


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个字典，override 的值覆盖 base。"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_api_config(config: dict) -> tuple:
    """提取 API 配置，返回 (url, key)。"""
    api = config.get("api", {})
    return api.get("url", DEFAULT_CONFIG["api"]["url"]), api.get("key", "")


def get_push_config(config: dict) -> dict:
    """提取推送配置。"""
    push = config.get("push", {})
    return {
        "title": push.get("title", DEFAULT_CONFIG["push"]["title"]),
        "hitokoto": push.get("hitokoto", DEFAULT_CONFIG["push"]["hitokoto"]),
    }
