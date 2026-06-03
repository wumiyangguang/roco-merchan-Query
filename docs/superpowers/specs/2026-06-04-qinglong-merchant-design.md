# 远行商人青龙面板脚本 — 设计规格

## 背景

从零构建适配青龙面板的远行商人查询脚本。`notify.py` 为青龙面板系统文件，项目不包含。

## 项目结构

```
roco-merchan-Query-Qinglong/
├── roco-merchant.json   # 配置文件（不存在则自动创建）
├── main.py              # QingLong 入口脚本
├── core/
│   ├── __init__.py
│   ├── config.py        # 配置加载与自动生成
│   ├── fetcher.py       # API 数据获取
│   └── processor.py     # 数据解析处理
```

## 模块职责

### config.py

参考 `util.py` 的配置模式设计：

- 配置加载优先级：环境变量 > 配置文件 > 默认模板
- `ROCOM_API_KEY` 环境变量可覆盖配置文件中的 api.key，便于青龙面板直接注入密钥
- `ROCOM_CONFIG_PATH` 环境变量可指定配置文件路径
- 若配置文件不存在：生成默认模板，继续运行（不退出）
- 若配置文件中 api.key 为空且无环境变量：提示警告，继续运行（让 API 层报错时推送通知）

### fetcher.py（无变化）

- 接收 api_url 和 api_key
- 发起 GET 请求（30s 超时），请求头 `X-API-Key`
- 返回 `{"code": int, "message": str, "data": dict}` 原始字典
- 网络/HTTP 异常向上抛出

### processor.py（无变化）

- `get_beijing_time()` / `format_timestamp()` / `get_round_info()`
- `process_merchant_data()` — 三类商品提取、活跃判定、价格补全、历史分组

### main.py（无变化）

- 入口：加载配置 → 获取数据 → 解析处理 → 组装纯文本 → 调用 `notify.send()`

## 配置设计（JSON）

```json
{
  "api": {
    "url": "https://wegame.shallow.ink/api/v1/games/rocom/merchant/info",
    "key": ""
  },
  "push": {
    "title": "📢 远行商人",
    "hitokoto": false
  }
}
```

环境变量覆盖规则：

| 环境变量 | 覆盖字段 | 说明 |
|----------|---------|------|
| `ROCOM_API_KEY` | `api.key` | 青龙面板可直接设密钥，无需编辑配置文件 |
| `ROCOM_CONFIG_PATH` | 配置文件路径 | 可自定义配置文件位置 |

## 数据流

```
ROCOM_API_KEY ──→ env ──→ config.py ──→ 配置字典
                               │
roco-merchant.json ───────────┘
                               │
main.py ──→ fetcher.py ──→ API ──→ raw JSON
                │                      │
                └── processor.py ←─────┘
                        │
                        ↓ 结构化数据
                        │
                main.py 组装纯文本
                        │
                        ↓
                notify.send(title, body)
                        │
                        ↓ 青龙面板 notify.py 并行推送到各渠道
```

## 错误处理

| 场景 | 处理 |
|------|------|
| 配置文件不存在 | 生成模板，继续运行 |
| 配置 JSON 格式错误 | 打印错误，继续用空配置运行 |
| api.key 为空（配置+环境变量均无） | 打印提示，继续运行，API 请求会失败并推送通知 |
| API 请求失败 | 捕获异常，推送 "监控异常" 通知 |
| API 返回 code != 0 | 推送 "API 错误: {message}" |
| 无活跃商品 | 推送 "当前暂无商品" |

## 依赖

| 依赖 | 用途 | 备注 |
|------|------|------|
| requests | HTTP 请求 | 青龙面板自带 |
| notify | 推送通知 | 青龙面板自带系统模块 |

> 零额外依赖，无需安装 PyYAML。
