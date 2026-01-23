"""
全局模型管理器（Global Model Manager）

功能：
1. 管理 LLM 模型的全局状态
2. 提供动态模型切换能力
3. 支持模型变更通知

设计原则：
- 单例模式，确保全局唯一
- 与 LlamaCppHttpClient 解耦，通过接口交互
- 支持多个监听者
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Any

if TYPE_CHECKING:
    from clude_code.llm.llama_cpp_http import LlamaCppHttpClient

logger = logging.getLogger(__name__)


class ModelManager:
    """
    全局模型管理器（单例）
    
    职责：
    - 跟踪当前使用的 LLM 模型
    - 提供模型切换能力
    - 管理模型变更通知
    """
    
    _instance: "ModelManager | None" = None
    
    def __init__(self) -> None:
        """初始化（私有，请使用 get_instance()）"""
        self._llm_client: "LlamaCppHttpClient | None" = None
        self._on_changed_callbacks: list[Callable[[str, str], None]] = []
        self._model_history: list[str] = []  # 模型切换历史
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
    
    def bind(self, llm_client: "LlamaCppHttpClient") -> None:
        """
        绑定 LLM 客户端。
        
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
    
    def switch_model(self, model: str, validate: bool = True) -> tuple[bool, str]:
        """
        切换模型。
        
        参数:
            model: 目标模型名称
            validate: 是否验证模型可用性
        
        返回:
            (success, message) 元组
        """
        if not self._llm_client:
            return False, "LLM 客户端未绑定"
        
        # 获取旧模型
        old_model = self._llm_client.model
        
        # 如果是同一个模型，直接返回
        if old_model == model:
            return True, f"已经在使用模型: {model}"
        
        # 验证模型可用性（可选）
        if validate:
            available = self.list_models()
            if available and model not in available:
                # 尝试模糊匹配
                matches = [m for m in available if model.lower() in m.lower()]
                if matches:
                    suggestion = matches[0]
                    return False, f"模型 '{model}' 不可用。您是否想要: {suggestion}?"
                return False, f"模型 '{model}' 不可用。可用模型: {', '.join(available[:5])}..."
        
        # 执行切换
        self._llm_client.set_model(model)
        
        # 记录历史
        self._model_history.append(old_model)
        if len(self._model_history) > self._max_history:
            self._model_history.pop(0)
        
        # 触发回调
        for callback in self._on_changed_callbacks:
            try:
                callback(old_model, model)
            except Exception as e:
                logger.warning(f"模型切换回调执行失败: {e}")
        
        logger.info(f"模型已切换: {old_model} → {model}")
        return True, f"已切换到模型: {model}"
    
    def list_models(self) -> list[str]:
        """获取可用模型列表"""
        if not self._llm_client:
            return []
        return self._llm_client.list_model_ids()
    
    def get_current_model(self) -> str:
        """获取当前模型名称"""
        if not self._llm_client:
            return ""
        return self._llm_client.model
    
    def get_model_history(self) -> list[str]:
        """获取模型切换历史"""
        return list(self._model_history)
    
    def rollback_model(self) -> tuple[bool, str]:
        """
        回滚到上一个模型。
        
        返回:
            (success, message) 元组
        """
        if not self._model_history:
            return False, "没有模型切换历史"
        
        previous_model = self._model_history[-1]
        return self.switch_model(previous_model, validate=False)
    
    def on_model_changed(self, callback: Callable[[str, str], None]) -> None:
        """
        注册模型变更回调。
        
        参数:
            callback: 回调函数，签名 (old_model, new_model) -> None
        """
        self._on_changed_callbacks.append(callback)
    
    def get_model_info(self) -> dict[str, Any]:
        """
        获取当前模型信息。
        
        返回:
            包含模型信息的字典
        """
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


def get_current_model() -> str:
    """便捷函数：获取当前模型"""
    return get_model_manager().get_current_model()


def list_available_models() -> list[str]:
    """便捷函数：列出可用模型"""
    return get_model_manager().list_models()

