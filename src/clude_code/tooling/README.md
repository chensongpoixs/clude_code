# 工具箱与回馈模块 (Tooling)

负责具体的本地能力实现，并对结果进行语义化加工。

## 核心能力
- **Patch Engine**: 支持 `apply_patch` (模糊匹配/多点替换) 与 `undo_patch` (哈希校验回滚)。
- **高效搜索**: 集成 `ripgrep` (rg) 进行高性能代码搜索，并支持 `glob_file_search`。
- **用户可见输出（display）**: 支持 `display` 工具（业界对标 `message_user`），用于长任务进度/中间结论输出，并在 `--live` 下进入思考滑动窗口。
- **语义采样 (Semantic Sampling)**: 在 `feedback.py` 中实现了 ±10 行动态窗口，并优先保留逻辑锚点（if/for/return）。
- **仓库地图 (Repo Map)**: 利用 `ctags` 生成轻量级的符号拓扑，为模型提供全局视野。
- **天气查询 (Weather API)**: 集成 OpenWeatherMap API，支持全球城市实时天气和5天预报查询。

## 关键文件
- `local_tools.py`: 包含文件读写、Grep 搜索、Patch 应用及 Repo Map 生成等核心能力。
- `feedback.py`: 将工具执行的原始 Payload 转化为模型更易理解的结构化回馈。
- `tools/display.py`: `display` 工具实现（事件广播 + 控制台降级 + 审计记录），用于提升执行过程可观测性。
- `tools/weather.py`: OpenWeatherMap 天气 API 集成，支持实时天气和天气预报。

## 外部 API 工具

### 天气工具 (Weather Tools)

使用 OpenWeatherMap API 获取全球天气信息。

**配置方式（二选一）**：

**方式 1：配置文件（推荐）**
```yaml
# clude.yaml
weather:
  api_key: "your_api_key_here"
  default_units: metric    # 摄氏度
  default_lang: zh_cn      # 中文
  timeout_s: 10
```

**方式 2：环境变量**
```bash
# Windows PowerShell
$env:OPENWEATHERMAP_API_KEY = "your_api_key_here"

# Linux/macOS
export OPENWEATHERMAP_API_KEY="your_api_key_here"
```

> 获取免费 API Key: https://openweathermap.org/api

**工具列表**：
| 工具名 | 功能 | 示例 |
|--------|------|------|
| `get_weather` | 获取实时天气 | `{"city": "Beijing"}` 或 `{"lat": 39.9, "lon": 116.4}` |
| `get_weather_forecast` | 获取5天预报 | `{"city": "Shanghai", "days": 3}` |

**返回数据**：
- 温度（当前/体感/最低/最高）
- 湿度、气压、能见度
- 风速和风向
- 天气描述（中文）
- 日出/日落时间
- 人类可读的格式化描述

## 模块流程
![Tooling Flow](module_flow.svg)

