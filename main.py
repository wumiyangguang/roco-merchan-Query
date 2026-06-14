#!/usr/bin/env python3
"""远行商人查询 — 青龙面板脚本入口。"""
import logging
import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from core.logger import setup_logging
from core.config import load_config, get_api_config, get_push_config
from core.fetcher import fetch_merchant_data
from core.processor import get_beijing_time, process_merchant_data
from core.push import send

logger = logging.getLogger(__name__)


def build_message(processed: dict) -> str:
    """将结构化数据组装为纯文本推送内容。"""
    round_info = processed.get("round_info", {})
    active_groups = processed.get("active_groups", [])

    now_str = get_beijing_time().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"北京时间: {now_str}",
        f"",
        f"第 {round_info.get('current', '?')}/{round_info.get('total', '?')} 轮 "
        f"| 剩余 {round_info.get('countdown', '未知')}",
        "",
    ]

    if active_groups:
        for p in active_groups:
            prefix = "⭐" if p.get("is_special") else "  "
            lines.append(f"{prefix}{p['name']}（剩余{p['remaining_str']}）")
    else:
        lines.append("当前暂无商品")

    return "\n".join(lines)


def main():
    start_ts = time.time()

    # 0. 初始化日志系统
    setup_logging()
    logger.info("===== 远行商人查询开始 =====")

    # 1. 加载配置
    t0 = time.time()
    cfg = load_config()
    api_url, api_key = get_api_config(cfg)
    push_cfg = get_push_config(cfg)
    logger.info("配置加载完成（%.0fms），API 地址: %s",
                (time.time() - t0) * 1000, api_url)

    # 2. 获取数据
    t0 = time.time()
    logger.info("获取 API 数据...")
    try:
        raw = fetch_merchant_data(api_url, api_key)
    except Exception as e:
        logger.exception("API 请求失败（%.0fms）", (time.time() - t0) * 1000)
        send(f"{push_cfg['title']} ⚠️ 监控异常", f"请求失败: {e}", push_cfg)
        return
    logger.info("API 请求完成（%.0fms）", (time.time() - t0) * 1000)

    if raw.get("code") != 0:
        logger.error("API 返回错误: code=%s, message=%s",
                     raw.get("code"), raw.get("message"))
        send(
            f"{push_cfg['title']} ⚠️ API 错误",
            raw.get("message", "未知错误"),
            push_cfg,
        )
        return

    data = raw.get("data")
    if not data:
        logger.warning("API 返回的 data 字段为空")
        send(f"{push_cfg['title']} ⚠️ 数据为空", "API 返回的 data 字段为空", push_cfg)
        return

    # 3. 解析处理
    t0 = time.time()
    logger.info("解析数据...")
    processed = process_merchant_data(data)
    product_count = processed.get("product_count", 0)
    logger.info("解析完成（%.0fms），活跃商品: %d 个",
                (time.time() - t0) * 1000, product_count)

    # 4. 组装内容并推送
    t0 = time.time()
    body = build_message(processed)
    logger.info("推送消息...")
    send(push_cfg["title"], body, push_cfg)
    logger.info("推送完成（%.0fms）", (time.time() - t0) * 1000)

    elapsed = (time.time() - start_ts) * 1000
    logger.info("===== 查询完成，总耗时 %.0fms =====", elapsed)


if __name__ == "__main__":
    main()
