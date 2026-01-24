"""
全局模型管理器（Global Model Manager）

功能：
1. 管理 LLM 厂商和模型的全局状态
2. 提供动态厂商/模型切换能力
3. 支持变更通知

设计原则：
- 单例模式，确保全局唯一
- 支持多厂商（通过 ProviderRegistry）
- 向后兼容（保留原有 bind/unbind API）
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Any

if TYPE_CHECKING:
    from clude_code.llm.llama_cpp_http import LlamaCppHttpClient
    from clude_code.llm.base import LLMProvider, ProviderConfig, ModelInfo

logger = logging.getLogger(__name__)


class ModelManager:
    """
    全局模型管理器（单例）
    
    职责：
    - 管理多个 LLM 厂商实例
    - 跟踪当前使用的厂商和模型
    - 提供厂商/模型切换能力
    - 管理变更通知
    """
    
    _instance: "ModelManager | None" = None
    
    def __init__(self) -> None:
        """初始化（私有，请使用 get_instance()）"""
        # 向后兼容：原有单一客户端
        self._llm_client: "LlamaCppHttpClient | None" = None
        
        # 新增：多厂商支持
        self._current_provider_id: str = ""
        self._providers: dict[str, "LLMProvider"] = {}
        
        # 回调和历史
        self._on_changed_callbacks: list[Callable[[str, str], None]] = []
        self._on_provider_changed_callbacks: list[Callable[[str, str], None]] = []
        self._model_history: list[str] = []
        self._provider_history: list[str] = []
        self._max_history = 10
    
    @classmethod
    def get_instance(cls) -> "ModelManager":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """重置单例（用于测试）"""
        cls._instance = None
    
    # ========== 向后兼容 API ==========
    
    def bind(self, llm_client: "LlamaCppHttpClient") -> None:
        """
        绑定 LLM 客户端（向后兼容）。
        
        参数:
            llm_client: LlamaCppHttpClient 实例
        """
        self._llm_client = llm_client
        logger.debug(f"ModelManager 已绑定 LLM 客户端，当前模型: {llm_client.model}")
    
    def unbind(self) -> None:
        """解绑 LLM 客户端"""
        self._llm_client = None
    
    @property
    def is_bound(self) -> bool:
        """是否已绑定 LLM 客户端"""
        return self._llm_client is not None
    
    # ========== 厂商管理 API ==========
    
    def register_provider(
        self,
        provider_id: str,
        provider: "LLMProvider",
        *,
        set_as_current: bool = False,
    ) -> None:
        """
        注册厂商实例。
        
        参数:
            provider_id: 厂商标识符
            provider: 厂商实例
            set_as_current: 是否设为当前厂商
        """
        self._providers[provider_id] = provider
        logger.info(f"已注册厂商: {provider_id} ({provider.PROVIDER_NAME})")
        
        if set_as_current or not self._current_provider_id:
            self._current_provider_id = provider_id
    
    def unregister_provider(self, provider_id: str) -> None:
        """注销厂商"""
        if provider_id in self._providers:
            del self._providers[provider_id]
            if self._current_provider_id == provider_id:
                self._current_provider_id = next(iter(self._providers), "")
    
    def get_provider(self, provider_id: str | None = None) -> "LLMProvider | None":
        """
        获取厂商实例。
        
        参数:
            provider_id: 厂商 ID，None 返回当前厂商
        
        返回:
            厂商实例，不存在返回 None
        """
        pid = provider_id or self._current_provider_id
        return self._providers.get(pid)
    
    def get_current_provider_id(self) -> str:
        """获取当前厂商 ID"""
        return self._current_provider_id
    
    def list_providers(self) -> list[dict[str, Any]]:
        """
        列出所有已注册厂商。
        
        返回:
            厂商信息列表
        """
        result = []
        for pid, provider in self._providers.items():
            result.append({
                "id": pid,
                "name": provider.PROVIDER_NAME,
                "type": provider.PROVIDER_TYPE,
                "region": provider.REGION,
                "is_current": pid == self._current_provider_id,
                "current_model": provider.current_model,
            })
        return result
    
    def switch_provider(
        self,
        provider_id: str,
        *,
        model: str | None = None,
    ) -> tuple[bool, str]:
        """
        切换厂商。
        
        参数:
            provider_id: 目标厂商 ID
            model: 可选，同时切换模型
        
        返回:
            (success, message) 元组
        """
        if provider_id not in self._providers:
            available = ", ".join(self._providers.keys()) or "无"
            return False, f"厂商 '{provider_id}' 未注册。可用: {available}"
        
        old_provider = self._current_provider_id
        
        if old_provider == provider_id:
            if model:
                return self.switch_model(model, validate=False)
            return True, f"已经在使用厂商: {provider_id}"
        
        # 切换厂商
        self._current_provider_id = provider_id
        
        # 记录历史
        if old_provider:
            self._provider_history.append(old_provider)
            if len(self._provider_history) > self._max_history:
                self._provider_history.pop(0)
        
        # 触发回调
        for callback in self._on_provider_changed_callbacks:
            try:
                callback(old_provider, provider_id)
            except Exception as e:
                logger.warning(f"厂商切换回调执行失败: {e}")
        
        logger.info(f"厂商已切换: {old_provider} → {provider_id}")
        
        # 如果指定了模型，同时切换
        if model:
            provider = self._providers[provider_id]
            provider.current_model = model
        
        return True, f"已切换到厂商: {provider_id}"
    
    def on_provider_changed(self, callback: Callable[[str, str], None]) -> None:
        """
        注册厂商变更回调。
        
        参数:
            callback: 回调函数，签名 (old_provider, new_provider) -> None
        """
        self._on_provider_changed_callbacks.append(callback)
    
    # ========== 模型管理 API ==========
    
    def switch_model(self, model: str, validate: bool = True) -> tuple[bool, str]:
        """
        切换模型。
        
        参数:
            model: 目标模型名称
            validate: 是否验证模型可用性
        
        返回:
            (success, message) 元组
        """
        # 优先使用新 API（厂商）
        if self._current_provider_id and self._current_provider_id in self._providers:
            provider = self._providers[self._current_provider_id]
            old_model = provider.current_model
            
            if old_model == model:
                return True, f"已经在使用模型: {model}"
            
            # 验证
            if validate:
                models = provider.list_models()
                model_ids = [m.id for m in models]
                if model_ids and model not in model_ids:
                    matches = [m for m in model_ids if model.lower() in m.lower()]
                    if matches:
                        return False, f"模型 '{model}' 不可用。您是否想要: {matches[0]}?"
                    return False, f"模型 '{model}' 不可用。可用模型: {', '.join(model_ids[:5])}..."
            
            # 切换
            provider.current_model = model
            
            # 历史
            if old_model:
                self._model_history.append(old_model)
                if len(self._model_history) > self._max_history:
                    self._model_history.pop(0)
            
            # 回调
            for callback in self._on_changed_callbacks:
                try:
                    callback(old_model, model)
                except Exception as e:
                    logger.warning(f"模型切换回调执行失败: {e}")
            
            logger.info(f"模型已切换: {old_model} → {model}")
            return True, f"已切换到模型: {model}"
        
        # 向后兼容：使用原有 llm_client
        if not self._llm_client:
            return False, "LLM 客户端未绑定"
        
        old_model = self._llm_client.model
        
        if old_model == model:
            return True, f"已经在使用模型: {model}"
        
        if validate:
            available = self.list_models()
            if available and model not in available:
                matches = [m for m in available if model.lower() in m.lower()]
                if matches:
                    return False, f"模型 '{model}' 不可用。您是否想要: {matches[0]}?"
                return False, f"模型 '{model}' 不可用。可用模型: {', '.join(available[:5])}..."
        
        self._llm_client.set_model(model)
        
        self._model_history.append(old_model)
        if len(self._model_history) > self._max_history:
            self._model_history.pop(0)
        
        for callback in self._on_changed_callbacks:
            try:
                callback(old_model, model)
            except Exception as e:
                logger.warning(f"模型切换回调执行失败: {e}")
        
        logger.info(f"模型已切换: {old_model} → {model}")
        return True, f"已切换到模型: {model}"
    
    def list_models(self) -> list[str]:
        """获取可用模型列表（ID 列表）"""
        # 优先使用新 API
        if self._current_provider_id and self._current_provider_id in self._providers:
            provider = self._providers[self._current_provider_id]
            return [m.id for m in provider.list_models()]
        
        # 向后兼容
        if not self._llm_client:
            return []
        return self._llm_client.list_model_ids()
    
    def list_models_info(self) -> list["ModelInfo"]:
        """获取可用模型列表（完整信息）"""
        if self._current_provider_id and self._current_provider_id in self._providers:
            return self._providers[self._current_provider_id].list_models()
        return []
    
    def get_current_model(self) -> str:
        """获取当前模型名称"""
        # 优先使用新 API
        if self._current_provider_id and self._current_provider_id in self._providers:
            return self._providers[self._current_provider_id].current_model
        
        # 向后兼容
        if not self._llm_client:
            return ""
        return self._llm_client.model
    
    def get_model_history(self) -> list[str]:
        """获取模型切换历史"""
        return list(self._model_history)
    
    def get_provider_history(self) -> list[str]:
        """获取厂商切换历史"""
        return list(self._provider_history)
    
    def rollback_model(self) -> tuple[bool, str]:
        """回滚到上一个模型"""
        if not self._model_history:
            return False, "没有模型切换历史"
        previous_model = self._model_history[-1]
        return self.switch_model(previous_model, validate=False)
    
    def rollback_provider(self) -> tuple[bool, str]:
        """回滚到上一个厂商"""
        if not self._provider_history:
            return False, "没有厂商切换历史"
        previous = self._provider_history[-1]
        return self.switch_provider(previous)
    
    def on_model_changed(self, callback: Callable[[str, str], None]) -> None:
        """
        注册模型变更回调。
        
        参数:
            callback: 回调函数，签名 (old_model, new_model) -> None
        """
        self._on_changed_callbacks.append(callback)
    
    def get_info(self) -> dict[str, Any]:
        """
        获取完整状态信息。
        
        返回:
            包含厂商和模型信息的字典
        """
        return {
            "current_provider": self._current_provider_id,
            "current_model": self.get_current_model(),
            "providers": self.list_providers(),
            "available_models": self.list_models(),
            "model_history": self.get_model_history(),
            "provider_history": self.get_provider_history(),
            "is_bound": self.is_bound,
        }
    
    # 向后兼容别名
    def get_model_info(self) -> dict[str, Any]:
        """获取模型信息（向后兼容）"""
        return {
            "current_model": self.get_current_model(),
            "available_models": self.list_models(),
            "history": self.get_model_history(),
            "is_bound": self.is_bound,
        }


# ============================================================
# 便捷函数
# ============================================================

def get_model_manager() -> ModelManager:
    """获取全局模型管理器"""
    return ModelManager.get_instance()


def switch_model(model: str, validate: bool = True) -> tuple[bool, str]:
    """便捷函数：切换模型"""
    return get_model_manager().switch_model(model, validate)


def switch_provider(provider_id: str, model: str | None = None) -> tuple[bool, str]:
    """便捷函数：切换厂商"""
    return get_model_manager().switch_provider(provider_id, model=model)


def get_current_model() -> str:
    """便捷函数：获取当前模型"""
    return get_model_manager().get_current_model()


def get_current_provider() -> str:
    """便捷函数：获取当前厂商"""
    return get_model_manager().get_current_provider_id()


def list_available_models() -> list[str]:
    """便捷函数：列出可用模型"""
    return get_model_manager().list_models()


def list_available_providers() -> list[dict[str, Any]]:
    """便捷函数：列出可用厂商"""
    return get_model_manager().list_providers()
