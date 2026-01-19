"""
Weather tool - OpenWeatherMap 天气获取工具

使用 OpenWeatherMap API 获取全球任意城市的实时天气信息。
支持多种查询方式：城市名、城市ID、经纬度坐标。

业界最佳实践：
- API Key 通过环境变量配置，避免硬编码
- 支持多语言输出（默认中文）
- 包含完整的错误处理和重试机制
- 返回结构化数据，便于 Agent 解析和使用
"""
from __future__ import annotations

import os
import time
import logging
from typing import Literal, Optional, Any
from dataclasses import dataclass
from enum import Enum

from clude_code.tooling.types import ToolResult, ToolError

# P1-1: 模块级 logger（延迟初始化，在 set_weather_config() 中配置）
_logger: logging.Logger | None = None

# 可选依赖：requests
try:
    import requests  # type: ignore
except ImportError:
    requests = None  # type: ignore


class WeatherUnits(str, Enum):
    """温度单位枚举"""
    METRIC = "metric"      # 摄氏度
    IMPERIAL = "imperial"  # 华氏度
    STANDARD = "standard"  # 开尔文


@dataclass
class WeatherData:
    """天气数据结构"""
    city: str
    country: str
    temperature: float
    feels_like: float
    temp_min: float
    temp_max: float
    humidity: int
    pressure: int
    visibility: int
    wind_speed: float
    wind_deg: int
    clouds: int
    weather_main: str
    weather_description: str
    weather_icon: str
    sunrise: int
    sunset: int
    timezone: int
    dt: int  # 数据更新时间戳
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "city": self.city,
            "country": self.country,
            "temperature": self.temperature,
            "feels_like": self.feels_like,
            "temp_min": self.temp_min,
            "temp_max": self.temp_max,
            "humidity": self.humidity,
            "pressure": self.pressure,
            "visibility": self.visibility,
            "wind_speed": self.wind_speed,
            "wind_deg": self.wind_deg,
            "clouds": self.clouds,
            "weather_main": self.weather_main,
            "weather_description": self.weather_description,
            "weather_icon": self.weather_icon,
            "sunrise": self.sunrise,
            "sunset": self.sunset,
            "timezone": self.timezone,
            "dt": self.dt,
        }
    
    def to_human_readable(self, units: str = "metric") -> str:
        """
        生成人类可读的天气描述
        
        Args:
            units: 温度单位 (metric=摄氏度, imperial=华氏度)
        
        Returns:
            格式化的天气描述字符串
        """
        from datetime import datetime, timezone, timedelta
        
        unit_symbol = "°C" if units == "metric" else ("°F" if units == "imperial" else "K")
        speed_unit = "m/s" if units == "metric" else ("mph" if units == "imperial" else "m/s")
        
        # 风向转换
        wind_directions = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
        wind_dir_idx = int((self.wind_deg + 22.5) / 45) % 8
        wind_dir = wind_directions[wind_dir_idx]
        
        # 时间格式化
        local_tz = timezone(offset=timedelta(seconds=self.timezone))
        sunrise_time = datetime.fromtimestamp(self.sunrise, tz=local_tz).strftime("%H:%M")
        sunset_time = datetime.fromtimestamp(self.sunset, tz=local_tz).strftime("%H:%M")
        update_time = datetime.fromtimestamp(self.dt, tz=local_tz).strftime("%Y-%m-%d %H:%M")
        
        return f"""📍 {self.city}, {self.country}
🌡️ 温度: {self.temperature}{unit_symbol} (体感 {self.feels_like}{unit_symbol})
   最低/最高: {self.temp_min}{unit_symbol} ~ {self.temp_max}{unit_symbol}
☁️ 天气: {self.weather_description}
💧 湿度: {self.humidity}%
🌬️ 风速: {self.wind_speed} {speed_unit} ({wind_dir}风)
👁️ 能见度: {self.visibility // 1000} km
🌅 日出: {sunrise_time} | 🌇 日落: {sunset_time}
⏰ 更新时间: {update_time}"""


# OpenWeatherMap API 配置
OPENWEATHERMAP_BASE_URL = "https://api.openweathermap.org/data/2.5"
OPENWEATHERMAP_GEO_URL = "https://api.openweathermap.org/geo/1.0"

# 环境变量名（用于无配置文件时的备用方案）
ENV_API_KEY = "OPENWEATHERMAP_API_KEY"

# 全局配置缓存（由 AgentLoop 初始化时注入）
_config_cache: dict[str, Any] = {}


def _ensure_logger_initialized(cfg: Any | None = None) -> logging.Logger:
    """
    确保 logger 已初始化（延迟初始化）。
    
    如果 logger 未初始化，则使用统一日志系统创建并配置 logger。
    优先使用传入的配置，如果没有配置则使用默认值。
    
    Args:
        cfg: CludeConfig 或 WeatherConfig 对象（可选）
    
    Returns:
        已配置的 Logger 实例
    """
    global _logger
    
    if _logger is None:
        from clude_code.observability.logger import get_logger
        
        # 确定 workspace_root
        workspace_root = "."
        if cfg is not None:
            if hasattr(cfg, "workspace_root"):
                workspace_root = cfg.workspace_root
            elif hasattr(cfg, "weather") and hasattr(cfg.weather, "workspace_root"):
                # 从 CludeConfig 获取
                workspace_root = cfg.workspace_root
        
        # 确定日志配置
        if cfg is not None:
            if hasattr(cfg, "logging"):
                # 从 CludeConfig 获取日志配置
                logging_cfg = cfg.logging
            elif hasattr(cfg, "weather"):
                # 从 CludeConfig 获取（通过 weather 属性判断）
                from clude_code.config import CludeConfig
                if isinstance(cfg, CludeConfig):
                    logging_cfg = cfg.logging
                else:
                    from clude_code.config import LoggingConfig
                    logging_cfg = LoggingConfig()
            else:
                from clude_code.config import LoggingConfig
                logging_cfg = LoggingConfig()
        else:
            # 使用默认配置
            from clude_code.config import LoggingConfig
            logging_cfg = LoggingConfig()
        
        # 确定是否写入文件（从天气配置获取，如果未配置则默认 True）
        log_to_file = True
        if cfg is not None:
            if hasattr(cfg, "weather") and hasattr(cfg.weather, "log_to_file"):
                log_to_file = cfg.weather.log_to_file
            elif hasattr(cfg, "log_to_file"):
                log_to_file = cfg.log_to_file
        # 也可以从已缓存的配置中获取（如果已调用过 set_weather_config）
        if _config_cache and "log_to_file" in _config_cache:
            log_to_file = _config_cache.get("log_to_file", True)
        
        # 创建并配置 logger
        # 如果 log_to_file=False，则不传入 workspace_root，这样就不会创建文件 handler
        # get_logger() 的逻辑：如果 log_file 为 None 且 workspace_root 为 None，则不会创建文件 handler
        logger_workspace_root = workspace_root if log_to_file else None
        logger_file_path = None
        if log_to_file and hasattr(logging_cfg, "file_path") and logging_cfg.file_path:
            logger_file_path = logging_cfg.file_path
        
        _logger = get_logger(
            __name__,
            workspace_root=logger_workspace_root,
            log_file=logger_file_path,
            log_to_console=logging_cfg.log_to_console,
            level=logging_cfg.level,
            log_format=logging_cfg.log_format,
            date_format=logging_cfg.date_format,
        )
    
    return _logger


def _get_logger() -> logging.Logger:
    """
    获取 logger（如果未初始化则使用默认配置初始化）。
    
    这是一个包装函数，确保在使用 logger 前已初始化。
    如果 set_weather_config() 还未调用，则使用默认配置初始化。
    
    Returns:
        Logger 实例
    """
    global _logger
    if _logger is None:
        # 使用默认配置初始化（向后兼容）
        return _ensure_logger_initialized(None)
    return _logger


def set_weather_config(cfg: Any) -> None:
    """
    设置天气配置（由 AgentLoop 在初始化时调用）
    
    此函数会初始化 logger（如果尚未初始化），确保日志能够写入文件。
    
    Args:
        cfg: CludeConfig 对象或其 weather 属性
    """
    global _config_cache
    
    # 确保 logger 已初始化（使用传入的配置）
    logger = _ensure_logger_initialized(cfg)
    logger.debug(f"[Weather] 开始加载天气配置, 配置类型: {type(cfg).__name__}")
    
    if hasattr(cfg, "weather"):
        # 传入的是 CludeConfig
        _config_cache = {
            "api_key": cfg.weather.api_key,
            "default_units": cfg.weather.default_units,
            "default_lang": cfg.weather.default_lang,
            "timeout_s": cfg.weather.timeout_s,
            "enabled": cfg.weather.enabled,
            "cache_ttl_s": getattr(cfg.weather, "cache_ttl_s", 300),
            "log_to_file": getattr(cfg.weather, "log_to_file", True),
        }
        logger.info(
            f"[Weather] 配置加载完成:\n"
            f"  - enabled: {cfg.weather.enabled}\n"
            f"  - units: {cfg.weather.default_units}\n"
            f"  - lang: {cfg.weather.default_lang}\n"
            f"  - timeout: {cfg.weather.timeout_s}s\n"
            f"  - cache_ttl: {getattr(cfg.weather, 'cache_ttl_s', 300)}s\n"
            f"  - log_to_file: {getattr(cfg.weather, 'log_to_file', True)}\n"
            f"  - api_key: {'已配置 (******)' if cfg.weather.api_key else '未配置'}"
        )
    elif hasattr(cfg, "api_key"):
        # 传入的是 WeatherConfig
        _config_cache = {
            "api_key": cfg.api_key,
            "default_units": cfg.default_units,
            "default_lang": cfg.default_lang,
            "timeout_s": cfg.timeout_s,
            "enabled": cfg.enabled,
            "cache_ttl_s": getattr(cfg, "cache_ttl_s", 300),
            "log_to_file": getattr(cfg, "log_to_file", True),
        }
        logger.info(
            f"[Weather] 配置加载完成:\n"
            f"  - enabled: {cfg.enabled}\n"
            f"  - units: {cfg.default_units}\n"
            f"  - lang: {cfg.default_lang}\n"
            f"  - timeout: {cfg.timeout_s}s\n"
            f"  - cache_ttl: {getattr(cfg, 'cache_ttl_s', 300)}s\n"
            f"  - log_to_file: {getattr(cfg, 'log_to_file', True)}\n"
            f"  - api_key: {'已配置 (******)' if cfg.api_key else '未配置'}"
        )
    else:
        logger.warning(f"[Weather] 无法解析天气配置: {type(cfg)}, 将使用默认值")


def _get_api_key() -> str | None:
    """
    获取 OpenWeatherMap API Key
    
    优先级（从高到低）：
    1. 环境变量 OPENWEATHERMAP_API_KEY
    2. 配置文件 (clude.toml 或 clude.yaml 中的 weather.api_key)
    """
    # 优先使用环境变量
    env_key = os.environ.get(ENV_API_KEY)
    if env_key:
        _get_logger().debug(f"[Weather] API Key 来源: 环境变量 {ENV_API_KEY}")
        return env_key
    
    # 其次使用配置文件
    if _config_cache.get("api_key"):
        _get_logger().debug("[Weather] API Key 来源: 配置文件")
        return _config_cache["api_key"]
    
    _get_logger().debug("[Weather] API Key 未配置")
    return None


def _get_default_units() -> str:
    """获取默认温度单位"""
    return _config_cache.get("default_units", "metric")


def _get_default_lang() -> str:
    """获取默认语言"""
    return _config_cache.get("default_lang", "zh_cn")


def _get_default_timeout() -> int:
    """获取默认超时时间"""
    return _config_cache.get("timeout_s", 10)


def _is_enabled() -> bool:
    """检查天气工具是否启用"""
    return _config_cache.get("enabled", True)


# 简易缓存：{cache_key: (timestamp, result)}
_weather_cache: dict[str, tuple[float, ToolResult]] = {}


def _get_cache_ttl() -> int:
    """获取缓存 TTL（秒）"""
    return _config_cache.get("cache_ttl_s", 300)


def _get_cache_key(city: str | None, lat: float | None, lon: float | None, units: str) -> str:
    """生成缓存键"""
    if city:
        return f"city:{city.lower()}:{units}"
    return f"coord:{lat}:{lon}:{units}"


def get_weather(
    city: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    units: str | None = None,
    lang: str | None = None,
    timeout: int | None = None,
) -> ToolResult:
    """
    获取天气信息
    
    支持两种查询方式：
    1. 城市名查询：提供 city 参数
    2. 经纬度查询：提供 lat 和 lon 参数
    
    Args:
        city: 城市名称（支持中文、英文、拼音），如 "Beijing", "北京", "London"
        lat: 纬度（-90 到 90）
        lon: 经度（-180 到 180）
        units: 温度单位
            - "metric": 摄氏度（默认）
            - "imperial": 华氏度
            - "standard": 开尔文
        lang: 返回语言（默认中文 zh_cn）
        timeout: 请求超时时间（秒）
    
    Returns:
        ToolResult: 包含天气数据的工具结果
        
    Example:
        >>> get_weather(city="Beijing")
        >>> get_weather(lat=39.9042, lon=116.4074)
    """
    # 记录请求开始
    query_desc = city if city else f"({lat}, {lon})"
    _get_logger().info(f"[Weather] 开始获取天气: {query_desc}")
    _get_logger().debug(f"[Weather] 请求参数: city={city}, lat={lat}, lon={lon}, units={units}, lang={lang}, timeout={timeout}")
    
    # 启用检查
    if not _is_enabled():
        _get_logger().warning("[Weather] 天气工具已禁用，拒绝请求")
        return ToolResult(
            ok=False,
            error={
                "code": "E_DISABLED",
                "message": "天气工具已禁用。请在配置文件中设置 weather.enabled=true 启用。",
            },
        )
    
    # 使用配置默认值（如果未指定）
    if units is None:
        units = _get_default_units()
        _get_logger().debug(f"[Weather] 使用默认温度单位: {units}")
    if lang is None:
        lang = _get_default_lang()
        _get_logger().debug(f"[Weather] 使用默认语言: {lang}")
    if timeout is None:
        timeout = _get_default_timeout()
        _get_logger().debug(f"[Weather] 使用默认超时: {timeout}s")
    
    # 缓存检查
    cache_key = _get_cache_key(city, lat, lon, units)
    cache_ttl = _get_cache_ttl()
    if cache_key in _weather_cache:
        cached_time, cached_result = _weather_cache[cache_key]
        cache_age = time.time() - cached_time
        if cache_age < cache_ttl:
            _get_logger().info(f"[Weather] 缓存命中: {cache_key}, 缓存年龄: {cache_age:.1f}s / TTL: {cache_ttl}s")
            return cached_result
        else:
            _get_logger().debug(f"[Weather] 缓存过期: {cache_key}, 缓存年龄: {cache_age:.1f}s > TTL: {cache_ttl}s")
    else:
        _get_logger().debug(f"[Weather] 缓存未命中: {cache_key}")
    
    # 依赖检查
    if requests is None:
        _get_logger().error("[Weather] requests 库未安装，无法发起 HTTP 请求")
        return ToolResult(
            ok=False,
            error={
                "code": "E_DEP_MISSING",
                "message": "requests 未安装，无法获取天气。请安装依赖：pip install requests",
            },
        )
    
    # API Key 检查
    api_key = _get_api_key()
    if not api_key:
        _get_logger().error(f"[Weather] API Key 未配置，请设置环境变量 {ENV_API_KEY} 或配置文件")
        return ToolResult(
            ok=False,
            error={
                "code": "E_CONFIG_MISSING",
                "message": (
                    "OpenWeatherMap API Key 未配置。获取方法：\n"
                    "1. 访问 https://openweathermap.org/api 注册并获取免费 API Key。\n"
                    "2. 配置方式（选其一）：\n"
                    "   - 命令行设置环境变量：export OPENWEATHERMAP_API_KEY='你的KEY' (Linux/macOS) 或 set OPENWEATHERMAP_API_KEY='你的KEY' (Windows)\n"
                    "   - 在 clude.yaml 中添加：\n"
                    "     weather:\n"
                    "       api_key: \"你的KEY\"\n"
                    "   - 在交互式 TUI 中使用内置命令：/config set weather.api_key '你的KEY'"
                ),
            },
        )
    
    # 参数验证
    if city is None and (lat is None or lon is None):
        _get_logger().warning("[Weather] 参数不完整: 必须提供 city 或 lat+lon")
        return ToolResult(
            ok=False,
            error={
                "code": "E_INVALID_ARGS",
                "message": "必须提供 city（城市名）或 lat+lon（经纬度）参数之一",
            },
        )
    
    # 验证经纬度范围
    if lat is not None and (lat < -90 or lat > 90):
        _get_logger().warning(f"[Weather] 纬度超出范围: {lat}")
        return ToolResult(
            ok=False,
            error={
                "code": "E_INVALID_ARGS",
                "message": f"纬度 lat 必须在 -90 到 90 之间，当前值: {lat}",
            },
        )
    if lon is not None and (lon < -180 or lon > 180):
        _get_logger().warning(f"[Weather] 经度超出范围: {lon}")
        return ToolResult(
            ok=False,
            error={
                "code": "E_INVALID_ARGS",
                "message": f"经度 lon 必须在 -180 到 180 之间，当前值: {lon}",
            },
        )
    
    # 验证单位
    valid_units = ["metric", "imperial", "standard"]
    if units not in valid_units:
        _get_logger().warning(f"[Weather] 无效的温度单位: {units}")
        return ToolResult(
            ok=False,
            error={
                "code": "E_INVALID_ARGS",
                "message": f"units 必须是 {valid_units} 之一，当前值: {units}",
            },
        )
    
    try:
        # 构建请求参数
        params: dict[str, Any] = {
            "appid": api_key,
            "units": units,
            "lang": lang,
        }
        
        # 根据查询方式设置参数
        if city:
            # 先通过 Geocoding API 获取城市坐标（更准确）
            _get_logger().debug(f"[Weather] 开始地理编码: {city}")
            geo_result = _geocode_city(city, api_key, timeout)
            if not geo_result["ok"]:
                _get_logger().warning(f"[Weather] 地理编码失败: {geo_result.get('error', {}).get('message', '未知错误')}")
                return ToolResult(ok=False, error=geo_result["error"])
            params["lat"] = geo_result["lat"]
            params["lon"] = geo_result["lon"]
            resolved_city = geo_result.get("name", city)
            resolved_country = geo_result.get("country", "")
            _get_logger().debug(f"[Weather] 地理编码成功: {city} -> ({params['lat']}, {params['lon']}), 解析名称: {resolved_city}")
        else:
            params["lat"] = lat
            params["lon"] = lon
            resolved_city = f"{lat},{lon}"
            resolved_country = ""
            _get_logger().debug(f"[Weather] 使用直接坐标: ({lat}, {lon})")
        
        # 请求天气数据
        url = f"{OPENWEATHERMAP_BASE_URL}/weather"
        start_time = time.time()
        _get_logger().info(f"[Weather] 发起 API 请求: {url}")
        _get_logger().info(f"[Weather] 请求参数: lat={params['lat']}, lon={params['lon']}, units={units}, lang={lang}")
        
        response = requests.get(url, params=params, timeout=timeout)
        elapsed_ms = (time.time() - start_time) * 1000
        
        _get_logger().debug(f"[Weather] API 响应: status={response.status_code}, 耗时={elapsed_ms:.1f}ms")
        
        # 处理 API 错误
        if response.status_code == 401:
            _get_logger().error("[Weather] API 认证失败: API Key 无效或已过期")
            return ToolResult(
                ok=False,
                error={
                    "code": "E_AUTH_FAILED",
                    "message": (
                        "OpenWeatherMap API 认证失败。建议：\n"
                        "1. 检查您的 API Key 是否填写正确（多余空格或字符）。\n"
                        "2. 新申请的 Key 可能需要 1-2 小时才能生效，请稍后再试。\n"
                        "3. 确认您的账号是否有权访问 'Current Weather Data' 接口（通常免费版即支持）。"
                    ),
                },
            )
        elif response.status_code == 404:
            _get_logger().warning(f"[Weather] 未找到位置: {city or f'({lat}, {lon})'}")
            return ToolResult(
                ok=False,
                error={
                    "code": "E_NOT_FOUND",
                    "message": (
                        f"未找到该城市的天气信息: {city or f'({lat}, {lon})'}。\n"
                        "建议：\n"
                        "1. 检查城市名拼写（支持中文，如'北京'，或英文，如'Beijing'）。\n"
                        "2. 如果城市较偏，请尝试提供省份或国家，例如 '浦北,广西,CN'。\n"
                        "3. 尝试使用经纬度坐标（lat, lon）进行查询。"
                    ),
                },
            )
        elif response.status_code == 429:
            _get_logger().error("[Weather] API 请求频率超限")
            return ToolResult(
                ok=False,
                error={
                    "code": "E_RATE_LIMIT",
                    "message": "API 请求频率超限。OpenWeatherMap 免费版限制为 60次/分钟。请稍后再试或检查是否有循环调用的逻辑。",
                },
            )
        
        response.raise_for_status()
        data = response.json()
        _get_logger().debug(f"[Weather] 响应数据大小: {len(response.content)} bytes")
        
        # 解析天气数据
        weather_data = WeatherData(
            city=data.get("name", resolved_city),
            country=data.get("sys", {}).get("country", resolved_country),
            temperature=data["main"]["temp"],
            feels_like=data["main"]["feels_like"],
            temp_min=data["main"]["temp_min"],
            temp_max=data["main"]["temp_max"],
            humidity=data["main"]["humidity"],
            pressure=data["main"]["pressure"],
            visibility=data.get("visibility", 0),
            wind_speed=data.get("wind", {}).get("speed", 0),
            wind_deg=data.get("wind", {}).get("deg", 0),
            clouds=data.get("clouds", {}).get("all", 0),
            weather_main=data["weather"][0]["main"] if data.get("weather") else "",
            weather_description=data["weather"][0]["description"] if data.get("weather") else "",
            weather_icon=data["weather"][0]["icon"] if data.get("weather") else "",
            sunrise=data.get("sys", {}).get("sunrise", 0),
            sunset=data.get("sys", {}).get("sunset", 0),
            timezone=data.get("timezone", 0),
            dt=data.get("dt", 0),
        )
        
        # 返回结果
        result = ToolResult(
            ok=True,
            payload={
                "query": {"city": city, "lat": lat, "lon": lon, "units": units, "lang": lang},
                "data": weather_data.to_dict(),
                "human_readable": weather_data.to_human_readable(units),
                "source": "OpenWeatherMap",
                "api_response_code": response.status_code,
            },
        )
        
        # 写入缓存
        _weather_cache[cache_key] = (time.time(), result)
        _get_logger().debug(f"[Weather] 已写入缓存: {cache_key}, TTL={cache_ttl}s")
        
        _get_logger().info(
            f"[Weather] 获取成功: {weather_data.city}, {weather_data.country} | "
            f"温度={weather_data.temperature}°, 天气={weather_data.weather_description}"
        )
        
        return result
        
    except requests.Timeout:
        _get_logger().error(f"[Weather] 请求超时: {timeout}s")
        return ToolResult(
            ok=False,
            error={
                "code": "E_TIMEOUT",
                "message": (
                    f"获取天气请求超时（限制 {timeout} 秒）。\n"
                    "可能原因：\n"
                    "1. 您的网络连接不稳定。\n"
                    "2. OpenWeatherMap 接口响应慢。\n"
                    "建议：尝试增大超时时间，例如：get_weather(city='...', timeout=20)"
                ),
            },
        )
    except requests.RequestException as e:
        _get_logger().warning(f"天气 API 请求失败: {e}", exc_info=True)
        return ToolResult(
            ok=False,
            error={
                "code": "E_NETWORK",
                "message": (
                    f"网络请求失败: {str(e)}。\n"
                    "建议：\n"
                    "1. 检查您的互联网连接。\n"
                    "2. 如果您在中国境内使用，请检查您的代理/VPN 是否开启并支持访问 api.openweathermap.org。\n"
                    "3. 检查是否有防火墙拦截了请求。"
                ),
            },
        )
    except Exception as e:
        _get_logger().warning(f"获取天气时发生异常: {e}", exc_info=True)
        return ToolResult(
            ok=False,
            error={
                "code": "E_INTERNAL",
                "message": f"内部错误: {str(e)}",
            },
        )


def _geocode_city(city: str, api_key: str, timeout: int = 10) -> dict[str, Any]:
    """
    使用 OpenWeatherMap Geocoding API 将城市名转换为坐标
    
    Args:
        city: 城市名称
        api_key: API Key
        timeout: 超时时间
    
    Returns:
        {"ok": True, "lat": float, "lon": float, "name": str, "country": str}
        或 {"ok": False, "error": {...}}
    """
    url = f"{OPENWEATHERMAP_GEO_URL}/direct"
    params = {
        "q": city,
        "limit": 1,
        "appid": api_key,
    }
    
    _get_logger().debug(f"[Geocoding] 开始查询: {city}")
    start_time = time.time()
    
    try:
        response = requests.get(url, params=params, timeout=timeout)
        elapsed_ms = (time.time() - start_time) * 1000
        _get_logger().debug(f"[Geocoding] API 响应: status={response.status_code}, 耗时={elapsed_ms:.1f}ms")
        
        response.raise_for_status()
        data = response.json()
        
        if not data:
            _get_logger().warning(f"[Geocoding] 未找到城市: {city}")
            return {
                "ok": False,
                "error": {
                    "code": "E_NOT_FOUND",
                    "message": f"未找到城市: {city}",
                },
            }
        
        location = data[0]
        local_name = location.get("local_names", {}).get("zh", location.get("name", city))
        country = location.get("country", "")
        _get_logger().debug(f"[Geocoding] 解析成功: {city} -> {local_name}, {country} ({location['lat']}, {location['lon']})")
        
        return {
            "ok": True,
            "lat": location["lat"],
            "lon": location["lon"],
            "name": local_name,
            "country": country,
        }
        
    except requests.Timeout:
        return {
            "ok": False,
            "error": {
                "code": "E_TIMEOUT",
                "message": f"城市坐标查询超时（{timeout}秒）",
            },
        }
    except requests.RequestException as e:
        _get_logger().warning(f"Geocoding API 请求失败: {e}", exc_info=True)
        return {
            "ok": False,
            "error": {
                "code": "E_NETWORK",
                "message": f"城市坐标查询网络错误: {str(e)}",
            },
        }
    except (KeyError, IndexError, TypeError) as e:
        _get_logger().warning(f"Geocoding API 响应解析失败: {e}", exc_info=True)
        return {
            "ok": False,
            "error": {
                "code": "E_PARSE_FAILED",
                "message": f"城市坐标解析失败: 响应格式异常",
            },
        }
    except Exception as e:
        _get_logger().warning(f"Geocoding 未知异常: {e}", exc_info=True)
        return {
            "ok": False,
            "error": {
                "code": "E_GEOCODE_FAILED",
                "message": f"城市坐标解析失败: {str(e)}",
            },
        }


def get_weather_forecast(
    city: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    units: str | None = None,
    lang: str | None = None,
    days: int = 5,
    timeout: int | None = None,
) -> ToolResult:
    """
    获取天气预报（5天/3小时）
    
    Args:
        city: 城市名称
        lat: 纬度
        lon: 经度
        units: 温度单位（默认从配置读取）
        lang: 语言（默认从配置读取）
        days: 预报天数（最多5天）
        timeout: 超时时间（默认从配置读取）
    
    Returns:
        ToolResult: 包含天气预报数据的工具结果
    """
    query_desc = city if city else f"({lat}, {lon})"
    _get_logger().info(f"[Forecast] 开始获取天气预报: {query_desc}, days={days}")
    
    # 启用检查
    if not _is_enabled():
        _get_logger().warning("[Forecast] 天气工具已禁用，拒绝请求")
        return ToolResult(
            ok=False,
            error={
                "code": "E_DISABLED",
                "message": "天气工具已禁用。请在配置文件中设置 weather.enabled=true 启用。",
            },
        )
    
    # 使用配置默认值（如果未指定）
    if units is None:
        units = _get_default_units()
    if lang is None:
        lang = _get_default_lang()
    if timeout is None:
        timeout = _get_default_timeout()
    
    _get_logger().debug(f"[Forecast] 参数: units={units}, lang={lang}, timeout={timeout}s, days={days}")
    
    # 依赖检查
    if requests is None:
        _get_logger().error("[Forecast] requests 库未安装")
        return ToolResult(
            ok=False,
            error={
                "code": "E_DEP_MISSING",
                "message": "requests 未安装，无法获取天气预报。请安装依赖：pip install requests",
            },
        )
    
    # API Key 检查
    api_key = _get_api_key()
    if not api_key:
        _get_logger().error("[Forecast] API Key 未配置")
        return ToolResult(
            ok=False,
            error={
                "code": "E_CONFIG_MISSING",
                "message": f"OpenWeatherMap API Key 未配置。请设置环境变量 {ENV_API_KEY}。",
            },
        )
    
    # 参数验证
    if city is None and (lat is None or lon is None):
        _get_logger().warning("[Forecast] 参数不完整")
        return ToolResult(
            ok=False,
            error={
                "code": "E_INVALID_ARGS",
                "message": "必须提供 city（城市名）或 lat+lon（经纬度）参数之一",
            },
        )
    
    try:
        cnt = min(days * 8, 40)  # 3小时一个数据点，5天最多40个
        params: dict[str, Any] = {
            "appid": api_key,
            "units": units,
            "lang": lang,
            "cnt": cnt,
        }
        _get_logger().debug(f"[Forecast] 数据点数量: {cnt} (days={days})")
        
        if city:
            _get_logger().debug(f"[Forecast] 开始地理编码: {city}")
            geo_result = _geocode_city(city, api_key, timeout)
            if not geo_result["ok"]:
                _get_logger().warning(f"[Forecast] 地理编码失败: {geo_result.get('error', {}).get('message')}")
                return ToolResult(ok=False, error=geo_result["error"])
            params["lat"] = geo_result["lat"]
            params["lon"] = geo_result["lon"]
            _get_logger().debug(f"[Forecast] 地理编码成功: ({params['lat']}, {params['lon']})")
        else:
            params["lat"] = lat
            params["lon"] = lon
        
        url = f"{OPENWEATHERMAP_BASE_URL}/forecast"
        start_time = time.time()
        _get_logger().debug(f"[Forecast] 发起 API 请求: {url}")
        
        response = requests.get(url, params=params, timeout=timeout)
        elapsed_ms = (time.time() - start_time) * 1000
        _get_logger().debug(f"[Forecast] API 响应: status={response.status_code}, 耗时={elapsed_ms:.1f}ms")
        
        response.raise_for_status()
        data = response.json()
        
        # 解析预报数据
        forecasts = []
        for item in data.get("list", []):
            forecasts.append({
                "dt": item["dt"],
                "dt_txt": item.get("dt_txt", ""),
                "temp": item["main"]["temp"],
                "feels_like": item["main"]["feels_like"],
                "humidity": item["main"]["humidity"],
                "weather": item["weather"][0]["description"] if item.get("weather") else "",
                "wind_speed": item.get("wind", {}).get("speed", 0),
                "pop": item.get("pop", 0),  # 降水概率
            })
        
        city_name = data.get("city", {}).get("name", city or f"{lat},{lon}")
        country = data.get("city", {}).get("country", "")
        _get_logger().info(f"[Forecast] 获取成功: {city_name}, {country} | 预报数据点: {len(forecasts)}")
        
        return ToolResult(
            ok=True,
            payload={
                "query": {"city": city, "lat": lat, "lon": lon, "days": days},
                "city": city_name,
                "country": country,
                "forecasts": forecasts,
                "source": "OpenWeatherMap",
            },
        )
        
    except requests.Timeout:
        _get_logger().error(f"[Forecast] 请求超时: {timeout}s")
        return ToolResult(
            ok=False,
            error={
                "code": "E_TIMEOUT",
                "message": f"请求超时（{timeout}秒），请检查网络或稍后重试",
            },
        )
    except requests.RequestException as e:
        _get_logger().warning(f"[Forecast] 网络请求失败: {e}", exc_info=True)
        return ToolResult(
            ok=False,
            error={
                "code": "E_NETWORK",
                "message": f"网络请求失败: {str(e)}",
            },
        )
    except Exception as e:
        _get_logger().warning(f"[Forecast] 获取天气预报失败: {e}", exc_info=True)
        return ToolResult(
            ok=False,
            error={
                "code": "E_FORECAST_FAILED",
                "message": f"获取天气预报失败: {str(e)}",
            },
        )

