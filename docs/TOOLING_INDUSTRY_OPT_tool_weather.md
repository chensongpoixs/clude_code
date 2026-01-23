## weather（`src/clude_code/tooling/tools/weather.py`）业界优化点

### 当前模块职责

- 通过 OpenWeatherMap API 获取实时天气与预报；支持城市名或经纬度；带简易 TTL 缓存与结构化返回。

### 业界技术原理

- **API Key 不落盘/不进日志**：必须通过环境变量或安全配置注入，并确保日志脱敏。
- **缓存（TTL）**：天气属于强时效数据，但短 TTL（如 60~300s）可以显著降低请求频次与限流概率。
- **依赖可选化**：requests/httpx 之类网络依赖应可选，并在缺失时给出明确错误。

### 现状评估（本项目）

- 已实现：配置注入（`set_weather_config`）、日志初始化、TTL 缓存、结构化数据模型（WeatherData）。
- 仍需注意：本模块内含 emoji 的 human readable 文本，可能导致回喂 token 增加；应主要回喂结构化字段。

### 可优化点（建议优先级）

- **P1：网络层统一（requests→httpx）**
  - **原理**：统一 HTTP 客户端更利于复用超时/重试/代理/证书策略。
  - **建议**：与 webfetch/websearch 对齐使用 `httpx`，并统一重试逻辑。

- **P2：缓存与可观测性**
  - **建议**：记录 cache hit/miss 与 API 429，便于调参与排障。


