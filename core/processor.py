"""数据解析处理模块。"""
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def get_beijing_time():
    return datetime.now(timezone(timedelta(hours=8)))


def format_timestamp(ts_ms):
    if not ts_ms:
        return "--:--"
    dt = datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone(timedelta(hours=8)))
    return dt.strftime("%H:%M")


def get_round_info():
    now = get_beijing_time()
    start_time = now.replace(hour=8, minute=0, second=0, microsecond=0)

    if now < start_time:
        logger.debug("当前时间早于 08:00，尚未开市")
        return {"current": "未开放", "total": 4, "countdown": "尚未开市"}

    delta_seconds = int((now - start_time).total_seconds())
    round_index = (delta_seconds // (4 * 3600)) + 1

    if round_index > 4:
        logger.debug("当前为第 %d 轮，今日已收市", round_index)
        return {"current": 4, "total": 4, "countdown": "今日已收市"}

    round_end = start_time + timedelta(hours=round_index * 4)
    remaining = round_end - now
    hours, rem = divmod(int(remaining.total_seconds()), 3600)
    minutes, _ = divmod(rem, 60)

    countdown_str = f"{hours}小时{minutes}分钟" if hours > 0 else f"{minutes}分钟"

    logger.debug("当前第 %d/%d 轮，剩余 %s", round_index, 4, countdown_str)

    return {
        "current": round_index,
        "total": 4,
        "countdown": countdown_str,
    }


def _calc_remaining_str(end_ms: int, now_ms: int) -> str:
    """计算剩余时间的中文描述。"""
    remaining_ms = max(end_ms - now_ms, 0)
    total_seconds = remaining_ms // 1000
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60

    parts = []
    if days > 0:
        parts.append(f"{days}天")
    if hours > 0 or days > 0:
        parts.append(f"{hours}小时")
    if minutes > 0 or not parts:
        parts.append(f"{minutes}分钟")
    return "".join(parts)



def process_merchant_data(data: dict) -> dict:
    if not data:
        logger.warning("传入的 data 为空，返回空结果")
        return {}

    now_ms = int(get_beijing_time().timestamp() * 1000)
    round_info = get_round_info()

    activities = data.get("merchantActivities") or data.get("merchant_activities") or []
    activity = activities[0] if activities else {}
    logger.debug("活动名称: %s, 商品列表数: %d",
                 activity.get("name", "未知"), len(activities))

    buckets = [
        ("道具", activity.get("get_props") or []),
        ("额外道具", activity.get("get_extra_props") or []),
        ("精灵", activity.get("get_pets") or []),
    ]

    random_goods = data.get("random_goods") if isinstance(data.get("random_goods"), list) else []
    goods_meta_by_name = {
        str(item.get("goods_name", "") or item.get("name", "")).strip(): item
        for item in random_goods
        if isinstance(item, dict) and str(item.get("goods_name", "") or item.get("name", "")).strip()
    }
    logger.debug("元数据字典条目数: %d", len(goods_meta_by_name))

    all_products = []
    active_products = []

    for category, items in buckets:
        for item in items:
            if not isinstance(item, dict):
                continue

            goods_meta = goods_meta_by_name.get(str(item.get("name", "")).strip(), {})

            s_time = item.get("start_time")
            e_time = item.get("end_time")

            if s_time is None:
                s_time = activity.get("start_time")
            if e_time is None:
                e_time = activity.get("end_time")

            start_ms = int(s_time) if s_time else None
            end_ms = int(e_time) if e_time else None

            is_active = True
            if start_ms is not None and end_ms is not None:
                is_active = start_ms <= now_ms < end_ms

            status_label = "当前轮次"
            if start_ms is not None and now_ms < start_ms:
                status_label = "未开始"
            elif end_ms is not None and now_ms >= end_ms:
                status_label = "已结束"

            start_str = format_timestamp(start_ms)
            end_str = format_timestamp(end_ms)
            if start_str[:5] == end_str[:5] and start_str != "--:--":
                time_label = f"{start_str} - {end_str[6:]}" if len(end_str) > 6 else f"{start_str} - {end_str}"
            else:
                time_label = f"{start_str} - {end_str}"

            price = item.get("price") if item.get("price") not in (None, "") else goods_meta.get("price")
            buy_limit_num = item.get("buy_limit_num") if item.get("buy_limit_num") not in (None, "") else goods_meta.get("buy_limit_num")

            product = {
                "name": item.get("name", "未知商品"),
                "image": item.get("icon_url", ""),
                "time_label": time_label,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "is_active": is_active,
                "status_label": status_label,
                "price": price,
                "buy_limit_num": buy_limit_num,
            }

            all_products.append(product)
            if is_active:
                active_products.append(product)

    logger.debug("商品总数: %d, 活跃商品: %d", len(all_products), len(active_products))

    # ========== 构建活跃道具列表（仅从 get_props，按结束时间排序）==========
    get_props_items = []
    for item in (activity.get("get_props") or []):
        if not isinstance(item, dict):
            continue

        s_time = item.get("start_time") or activity.get("start_time")
        e_time = item.get("end_time") or activity.get("end_time")
        start_ms = int(s_time) if s_time else None
        end_ms = int(e_time) if e_time else None

        # 只保留当前活跃的道具（已结束的不输出）
        if start_ms is None or end_ms is None:
            continue
        if not (start_ms <= now_ms < end_ms):
            continue

        name = item.get("name", "未知商品")
        get_props_items.append({
            "name": name,
            "end_ms": end_ms,
            "remaining_str": _calc_remaining_str(end_ms, now_ms),
            "is_special": name in ("国王球", "棱镜球", "炫彩精灵蛋"),
        })

    # 特殊物品优先，再按结束时间升序排列
    get_props_items.sort(key=lambda x: (not x["is_special"], x["end_ms"]))

    # 去重：同时间段的同名商品合并，后缀标注剩余时间
    active_groups = []
    seen_keys = set()
    for p in get_props_items:
        key = (p["name"], p["end_ms"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        active_groups.append({
            "name": p["name"],
            "remaining_str": p["remaining_str"],
            "is_special": p["is_special"],
        })

    today = datetime.fromtimestamp(now_ms / 1000, tz=timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    grouped = {}

    for product in all_products:
        if product["is_active"]:
            continue
        start_ms = product["start_ms"]
        if not start_ms:
            continue

        start_dt = datetime.fromtimestamp(start_ms / 1000, tz=timezone(timedelta(hours=8)))
        if start_dt.strftime("%Y-%m-%d") != today:
            continue

        key = f"{start_ms}-{product['end_ms'] or ''}"
        if key not in grouped:
            grouped[key] = {
                "time_label": product["time_label"] or "--:--",
                "status_label": product["status_label"] or "其他时段",
                "sort": start_ms,
                "products": [],
            }
        group = grouped[key]
        names = {p["name"] for p in group["products"]}
        if product["name"] not in names and len(group["products"]) < 5:
            group["products"].append(product)

    history_groups = [
        {k: v for k, v in g.items() if k != "sort"}
        for g in sorted(grouped.values(), key=lambda x: x["sort"])
        if g["products"]
    ]

    logger.debug("历史分组数: %d", len(history_groups))

    return {
        "title": activity.get("name", "远行商人"),
        "subtitle": activity.get("start_date", "每日 08:00 / 12:00 / 16:00 / 20:00 刷新"),
        "product_count": len(active_products),
        "round_info": round_info,
        "products": active_products,
        "history_groups": history_groups,
        "active_groups": active_groups,
    }
