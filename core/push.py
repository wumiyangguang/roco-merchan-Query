"""推送通知模块。

渠道设计：
- 每个渠道是一个签名为 (title, content, config) -> bool 的函数
- 通过 register_channel() 注册到全局渠道表
- send() 依次调用所有已注册渠道
- 渠道内部自行判断是否配置完整，未配置则跳过
- 所有配置从配置文件 push 段读取，不依赖环境变量

添加新渠道示例：
    @register_channel
    def my_channel(title, content, config):
        key = config.get("my_key", "")
        if not key:
            return False
        # ... 推送逻辑 ...
        return True
"""
import base64
import concurrent.futures
import hashlib
import hmac
import json
import logging
import time as _time
import urllib.parse

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

    配置项：push.qmsg_key / push.qmsg_type
    文档：https://qmsg.zendee.cn/api
    """
    key = config.get("qmsg_key", "")
    qtype = config.get("qmsg_type", "send")

    if not key:
        return False

    url = f"https://qmsg.zendee.cn/{qtype}/{key}"
    logger.debug("QMSG 推送 -> %s", qtype)

    try:
        resp = requests.post(url, params={"msg": f"{title}\n\n{content}"}, timeout=(5, 10))
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


@register_channel
def _pushplus_push(title: str, content: str, config: dict) -> bool:
    """PushPlus（push+ 微信推送）。

    配置项：push.pushplus_token / push.pushplus_topic（可选）
    文档：https://www.pushplus.plus
    """
    token = config.get("pushplus_token", "")
    if not token:
        return False

    url = "http://www.pushplus.plus/send"
    body = {
        "token": token,
        "title": title,
        "content": content,
        "topic": config.get("pushplus_topic", ""),
    }
    logger.debug("PushPlus 推送 -> token=%s...", token[:8])

    try:
        resp = requests.post(url, json=body, timeout=(5, 10))
        data = resp.json()
    except requests.RequestException:
        logger.exception("PushPlus 推送网络异常")
        return False
    except json.JSONDecodeError:
        logger.error("PushPlus 响应解析失败: %s", resp.text[:200])
        return False

    if data.get("code") == 200:
        logger.info("PushPlus 推送成功")
        return True

    # 兜底旧域名
    try:
        resp2 = requests.post("http://pushplus.hxtrip.com/send", json=body, timeout=(5, 10))
        data2 = resp2.json()
        if data2.get("code") == 200:
            logger.info("PushPlus(hxtrip) 推送成功")
            return True
    except Exception:
        pass

    logger.error("PushPlus 推送失败: %s", data)
    return False


@register_channel
def _server_chan_push(title: str, content: str, config: dict) -> bool:
    """Server酱（微信推送）。

    配置项：push.server_key
    文档：https://sct.ftqq.com
    """
    key = config.get("server_key", "")
    if not key:
        return False

    # SCT 开头的 key 使用新域名
    if key.upper().startswith("SCT"):
        url = f"https://sctapi.ftqq.com/{key}.send"
    else:
        url = f"https://sc.ftqq.com/{key}.send"

    data = {"text": title, "desp": content.replace("\n", "\n\n")}
    logger.debug("Server酱 推送")

    try:
        resp = requests.post(url, data=data, timeout=(5, 10))
        result = resp.json()
    except requests.RequestException:
        logger.exception("Server酱 推送网络异常")
        return False
    except json.JSONDecodeError:
        logger.error("Server酱 响应解析失败: %s", resp.text[:200])
        return False

    if result.get("errno") == 0 or result.get("code") == 0:
        logger.info("Server酱 推送成功")
        return True
    else:
        logger.error("Server酱 推送失败: %s", result)
        return False


@register_channel
def _bark_push(title: str, content: str, config: dict) -> bool:
    """Bark（iOS 推送）。

    配置项：push.bark_key / push.bark_server（可选，自建服务地址）
    文档：https://github.com/Finb/Bark
    """
    key = config.get("bark_key", "")
    if not key:
        return False

    server = config.get("bark_server", "")
    if server:
        url = f"{server.rstrip('/')}/{key}"
    else:
        url = f"https://api.day.app/{key}"

    body = {"title": title, "body": content}
    logger.debug("Bark 推送 -> %s", url)

    try:
        resp = requests.post(url, json=body, timeout=(5, 10))
        data = resp.json()
    except requests.RequestException:
        logger.exception("Bark 推送网络异常")
        return False
    except json.JSONDecodeError:
        logger.error("Bark 响应解析失败: %s", resp.text[:200])
        return False

    if data.get("code") == 200:
        logger.info("Bark 推送成功")
        return True
    else:
        logger.error("Bark 推送失败: %s", data)
        return False


@register_channel
def _dingtalk_push(title: str, content: str, config: dict) -> bool:
    """钉钉机器人推送。

    配置项：push.dd_bot_token / push.dd_bot_secret
    文档：https://open.dingtalk.com/document/robots/custom-robot-access
    """
    token = config.get("dd_bot_token", "")
    secret = config.get("dd_bot_secret", "")
    if not token or not secret:
        return False

    timestamp = str(round(_time.time() * 1000))
    sign_str = f"{timestamp}\n{secret}"
    sign = urllib.parse.quote_plus(
        base64.b64encode(hmac.new(
            secret.encode("utf-8"),
            sign_str.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest())
    )
    url = (
        f"https://oapi.dingtalk.com/robot/send"
        f"?access_token={token}&timestamp={timestamp}&sign={sign}"
    )
    body = {"msgtype": "text", "text": {"content": f"{title}\n\n{content}"}}
    logger.debug("钉钉机器人 推送")

    try:
        resp = requests.post(url, json=body, timeout=(5, 10))
        data = resp.json()
    except requests.RequestException:
        logger.exception("钉钉机器人 推送网络异常")
        return False
    except json.JSONDecodeError:
        logger.error("钉钉机器人 响应解析失败: %s", resp.text[:200])
        return False

    if data.get("errcode") == 0:
        logger.info("钉钉机器人 推送成功")
        return True
    else:
        logger.error("钉钉机器人 推送失败: %s", data.get("errmsg", "未知"))
        return False


@register_channel
def _feishu_push(title: str, content: str, config: dict) -> bool:
    """飞书机器人推送。

    配置项：push.fs_key
    文档：https://open.feishu.cn/document/ukTMukTMukTM/ucTM5YjL3ETO24yNxkjN
    """
    key = config.get("fs_key", "")
    if not key:
        return False

    url = f"https://open.feishu.cn/open-apis/bot/v2/hook/{key}"
    body = {"msg_type": "text", "content": {"text": f"{title}\n\n{content}"}}
    logger.debug("飞书 推送")

    try:
        resp = requests.post(url, json=body, timeout=(5, 10))
        data = resp.json()
    except requests.RequestException:
        logger.exception("飞书 推送网络异常")
        return False
    except json.JSONDecodeError:
        logger.error("飞书 响应解析失败: %s", resp.text[:200])
        return False

    if data.get("StatusCode") == 0 or data.get("code") == 0:
        logger.info("飞书 推送成功")
        return True
    else:
        logger.error("飞书 推送失败: %s", data)
        return False


@register_channel
def _telegram_push(title: str, content: str, config: dict) -> bool:
    """Telegram Bot 推送。

    配置项：push.tg_bot_token / push.tg_user_id
    文档：https://core.telegram.org/bots/api
    """
    token = config.get("tg_bot_token", "")
    user_id = config.get("tg_user_id", "")
    if not token or not user_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    params = {
        "chat_id": str(user_id),
        "text": f"{title}\n\n{content}",
        "disable_web_page_preview": "true",
    }
    logger.debug("Telegram 推送 -> chat_id=%s", user_id)

    try:
        resp = requests.post(url, params=params, timeout=(5, 10))
        data = resp.json()
    except requests.RequestException:
        logger.exception("Telegram 推送网络异常")
        return False
    except json.JSONDecodeError:
        logger.error("Telegram 响应解析失败: %s", resp.text[:200])
        return False

    if data.get("ok"):
        logger.info("Telegram 推送成功")
        return True
    else:
        logger.error("Telegram 推送失败: %s", data.get("description", "未知"))
        return False


# ========== 公共接口 ==========

def _fetch_hitokoto() -> str:
    """获取一条一言（随机句子）。

    Returns:
        句子 + 出处，失败时返回空字符串。
    """
    try:
        resp = requests.get("https://v1.hitokoto.cn/", timeout=10)
        data = resp.json()
        hitokoto = data.get("hitokoto", "")
        source = data.get("from", "")
        if hitokoto:
            return f"{hitokoto}    ----{source}"
    except Exception:
        logger.debug("获取一言失败", exc_info=True)
    return ""


def send(title: str, content: str, config: dict = None) -> None:
    """推送消息到所有已配置的渠道（多线程并发）。

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

    # 启用一言时追加到正文末尾
    if config.get("hitokoto"):
        quote = _fetch_hitokoto()
        if quote:
            content += f"\n\n{quote}"
            logger.debug("已追加一言: %s", quote[:30])

    if not _channels:
        logger.warning("无可用推送渠道")
        return

    # 打印推送信息到日志
    logger.info("推送标题: %s", title)
    logger.info("推送内容:\n%s", content)

    # 多线程并发推送所有渠道
    def _run_channel(ch):
        t0 = _time.time()
        try:
            ok = ch(title, content, config)
            elapsed = (_time.time() - t0) * 1000
            if ok:
                logger.debug("%s 成功，耗时 %.0fms", ch.__name__, elapsed)
            return ok
        except Exception:
            elapsed = (_time.time() - t0) * 1000
            logger.exception("%s 异常，耗时 %.0fms", ch.__name__, elapsed)
            return False

    max_workers = min(len(_channels), 7)
    success_count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_run_channel, ch): ch for ch in _channels}
        for future in concurrent.futures.as_completed(futures):
            if future.result():
                success_count += 1

    if success_count == 0:
        logger.warning("所有推送渠道均未成功（可能未配置或全部失败）")
    else:
        logger.info("推送完成，成功 %d/%d 个渠道", success_count, len(_channels))
