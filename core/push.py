"""推送通知模块。

渠道设计：
- 每个渠道是一个签名为 (title, content, config) -> bool 的函数
- 通过 register_channel() 注册到全局渠道表
- send() 依次调用所有已注册渠道
- 渠道内部自行判断是否配置完整，未配置则跳过

添加新渠道示例：
    @register_channel
    def my_channel(title, content, config):
        key = os.getenv("MY_KEY") or config.get("my_key", "")
        if not key:
            return False
        # ... 推送逻辑 ...
        return True
"""
import json
import logging
import os

import requests

logger = logging.getLogger(__name__)

# ========== 渠道注册表 ==========

_channels = []


def register_channel(func):
    """注册一个推送渠道（可用作装饰器）。

    渠道函数签名：(title: str, content: str, config: dict) -> bool
    返回 True 表示推送成功，False 表示跳过或失败。
    """
    _channels.append(func)
    return func


# ========== 内置渠道 ==========

@register_channel
def _qmsg_push(title: str, content: str, config: dict) -> bool:
    """QMSG 酱推送。

    配置来源（优先级从高到低）：
    1. 环境变量 QMSG_KEY / QMSG_TYPE
    2. 配置文件 push.qmsg_key / push.qmsg_type

    文档：https://qmsg.zendee.cn/api
    """
    key = os.getenv("QMSG_KEY") or config.get("qmsg_key", "")
    qtype = os.getenv("QMSG_TYPE") or config.get("qmsg_type", "send")

    if not key:
        logger.debug("QMSG_KEY 未配置，跳过 QMSG 推送")
        return False

    url = f"https://qmsg.zendee.cn/{qtype}/{key}"
    msg = f"{title}\n\n{content}"

    logger.debug("QMSG 推送 -> type=%s, url=%s", qtype, url)

    try:
        resp = requests.post(url, params={"msg": msg}, timeout=15)
        data = resp.json()
    except requests.RequestException:
        logger.exception("QMSG 推送网络异常")
        return False
    except json.JSONDecodeError:
        logger.error("QMSG 响应解析失败: %s", resp.text[:200])
        return False

    if data.get("code") == 0:
        logger.info("QMSG 推送成功")
        return True
    else:
        logger.error("QMSG 推送失败: %s", data.get("reason", "未知"))
        return False


# ========== 公共接口 ==========

def send(title: str, content: str, config: dict = None) -> None:
    """推送消息到所有已配置的渠道。

    Args:
        title: 推送标题
        content: 推送正文
        config: 推送配置字典（来自 load_config 的 push 部分）
    """
    if config is None:
        config = {}

    if not content:
        logger.warning("推送内容为空，跳过推送")
        return

    if not _channels:
        logger.warning("无可用推送渠道")
        return

    success_count = 0
    for channel in _channels:
        try:
            if channel(title, content, config):
                success_count += 1
        except Exception:
            logger.exception("推送渠道 %s 异常", channel.__name__)

    if success_count == 0:
        logger.warning("所有推送渠道均未成功（可能未配置或全部失败）")
    else:
        logger.info("推送完成，成功 %d/%d 个渠道", success_count, len(_channels))
