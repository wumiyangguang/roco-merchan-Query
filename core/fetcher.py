"""API 数据获取模块。"""
import logging

import requests

logger = logging.getLogger(__name__)


def fetch_merchant_data(api_url: str, api_key: str, timeout: int = 30) -> dict:
    """获取远行商人 API 数据。

    Args:
        api_url: API 地址
        api_key: X-API-Key 鉴权密钥
        timeout: 请求超时秒数

    Returns:
        {"code": int, "message": str, "data": dict}

    Raises:
        requests.RequestException: 网络/HTTP 错误
    """
    logger.debug("请求 API: %s，超时 %ds", api_url, timeout)

    try:
        resp = requests.get(
            api_url,
            headers={"X-API-Key": api_key},
            timeout=timeout,
        )
        logger.debug("API 响应状态码: %d", resp.status_code)
        resp.raise_for_status()
        data = resp.json()
        logger.debug("API 响应 code=%s, message=%s",
                     data.get("code"), data.get("message"))
        return data
    except requests.Timeout:
        logger.error("API 请求超时（%ds）: %s", timeout, api_url)
        raise
    except requests.ConnectionError:
        logger.error("无法连接 API 服务器: %s", api_url)
        raise
    except requests.HTTPError as e:
        logger.error("API HTTP 错误: %s", e)
        raise
    except requests.RequestException:
        logger.exception("API 请求异常: %s", api_url)
        raise
