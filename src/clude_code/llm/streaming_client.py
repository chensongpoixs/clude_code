"""
支持流式响应的 LLM 客户端，提供实时进度反馈
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncGenerator, Callable, Dict, List, Optional, Union

import httpx
from pydantic import BaseModel

from clude_code.llm.http_client import ChatMessage
from clude_code.observability.logger import get_logger


class StreamChunk(BaseModel):
    """流式响应块"""
    content: str
    done: bool
    metadata: Optional[Dict] = None


class StreamingLLMClient:
    """支持流式响应的 LLM 客户端"""
    
    def __init__(
        self,
        workspace_root: str,
        base_url: str,
        api_mode: str = "openai_compat",
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        timeout_s: int = 120,
    ):
        self.workspace_root = workspace_root
        self.base_url = base_url
        self.api_mode = api_mode
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s
        self.logger = get_logger(__name__, workspace_root=workspace_root)
        self.client = httpx.AsyncClient(timeout=timeout_s)
        
        # 统计信息
        self.request_count = 0
        self.total_tokens = 0
        self.total_time = 0.0
    
    async def chat_stream(
        self,
        messages: List[ChatMessage],
        on_progress: Optional[Callable[[str, float], None]] = None,
        task_id: Optional[str] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """流式聊天接口"""
        self.request_count += 1
        start_time = time.time()
        
        try:
            if self.api_mode == "openai_compat":
                async for chunk in self._openai_compat_stream(messages, on_progress, task_id):
                    yield chunk
            else:
                # 非流式模式回退到原有实现
                content = await self._non_stream_chat(messages)
                yield StreamChunk(content=content, done=True)
        except Exception as e:
            self.logger.error(f"Error in chat_stream: {e}")
            yield StreamChunk(
                content=f"错误: {str(e)}",
                done=True,
                metadata={"error": str(e)}
            )
        finally:
            # 更新统计信息
            elapsed = time.time() - start_time
            self.total_time += elapsed
            self.logger.debug(f"LLM request completed in {elapsed:.2f}s")
    
    async def _openai_compat_stream(
        self,
        messages: List[ChatMessage],
        on_progress: Optional[Callable[[str, float], None]] = None,
        task_id: Optional[str] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """OpenAI 兼容流式接口"""
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }
        
        accumulated_content = ""
        token_count = 0
        
        try:
            self.logger.debug(f"Sending streaming request to {url}")
            async with self.client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    error_msg = error_text.decode('utf-8', errors='replace')
                    self.logger.error(f"LLM API error: {response.status_code} - {error_msg}")
                    raise Exception(f"LLM API error: {response.status_code} - {error_msg}")
                
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    
                    data_str = line[6:]  # Remove "data: " prefix
                    if data_str.strip() == "[DONE]":
                        break
                    
                    try:
                        data = json.loads(data_str)
                        if "choices" in data and len(data["choices"]) > 0:
                            delta = data["choices"][0].get("delta", {})
                            if "content" in delta:
                                content = delta["content"]
                                accumulated_content += content
                                token_count += 1
                                
                                # 计算进度（基于 token 估算）
                                progress = min(token_count / (self.max_tokens / 4), 0.95)  # 假设平均 1 token = 4 字符
                                
                                # 调用进度回调
                                if on_progress:
                                    on_progress(content, progress)
                                
                                # 发送流式块
                                yield StreamChunk(
                                    content=content,
                                    done=False,
                                    metadata={
                                        "token_count": token_count,
                                        "progress": progress,
                                        "task_id": task_id
                                    }
                                )
                    except json.JSONDecodeError as e:
                        self.logger.warning(f"Failed to parse JSON from streaming response: {e}")
                        continue
            
            # 更新总 token 计数
            self.total_tokens += token_count
            
            # 发送完成信号
            yield StreamChunk(
                content="",
                done=True,
                metadata={
                    "token_count": token_count,
                    "total_tokens": self.total_tokens,
                    "task_id": task_id
                }
            )
            
        except Exception as e:
            self.logger.error(f"Error in OpenAI compatible streaming: {e}")
            yield StreamChunk(
                content=f"流式请求错误: {str(e)}",
                done=True,
                metadata={"error": str(e), "task_id": task_id}
            )
    
    async def _non_stream_chat(self, messages: List[ChatMessage]) -> str:
        """非流式聊天回退实现"""
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        
        self.logger.debug(f"Sending non-streaming request to {url}")
        response = await self.client.post(url, json=payload)
        
        if response.status_code != 200:
            error_text = response.text
            self.logger.error(f"LLM API error: {response.status_code} - {error_text}")
            raise Exception(f"LLM API error: {response.status_code} - {error_text}")
        
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        
        # 更新 token 计数（如果可用）
        if "usage" in data:
            self.total_tokens += data["usage"].get("total_tokens", 0)
        
        return content
    
    async def close(self):
        """关闭客户端"""
        await self.client.aclose()
    
    def get_stats(self) -> Dict[str, Union[int, float]]:
        """获取客户端统计信息"""
        return {
            "request_count": self.request_count,
            "total_tokens": self.total_tokens,
            "total_time": self.total_time,
            "avg_time_per_request": self.total_time / max(1, self.request_count),
            "avg_tokens_per_request": self.total_tokens / max(1, self.request_count),
        }
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        self.request_count = 0
        self.total_tokens = 0
        self.total_time = 0.0


class CachedStreamingLLMClient(StreamingLLMClient):
    """带缓存的流式 LLM 客户端"""
    
    def __init__(
        self,
        workspace_root: str,
        base_url: str,
        api_mode: str = "openai_compat",
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        timeout_s: int = 120,
        cache_size: int = 100,
    ):
        super().__init__(
            workspace_root=workspace_root,
            base_url=base_url,
            api_mode=api_mode,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )
        self.cache_size = cache_size
        self.response_cache: Dict[str, str] = {}
        self.cache_hits = 0
        self.cache_misses = 0
    
    def _get_cache_key(self, messages: List[ChatMessage]) -> str:
        """生成缓存键"""
        # 简单的缓存键生成，实际应用中可能需要更复杂的哈希
        messages_str = json.dumps([{"role": m.role, "content": m.content} for m in messages])
        import hashlib
        return hashlib.md5(messages_str.encode()).hexdigest()
    
    async def chat_stream(
        self,
        messages: List[ChatMessage],
        on_progress: Optional[Callable[[str, float], None]] = None,
        task_id: Optional[str] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """带缓存的流式聊天接口"""
        cache_key = self._get_cache_key(messages)
        
        # 检查缓存
        if cache_key in self.response_cache:
            self.cache_hits += 1
            cached_response = self.response_cache[cache_key]
            
            # 模拟流式输出
            if on_progress:
                for i, char in enumerate(cached_response):
                    progress = (i + 1) / len(cached_response)
                    on_progress(char, progress)
                    yield StreamChunk(
                        content=char,
                        done=False,
                        metadata={"cached": True, "progress": progress}
                    )
                    # 添加小延迟以模拟真实流式输出
                    await asyncio.sleep(0.01)
            
            yield StreamChunk(content="", done=True, metadata={"cached": True})
            return
        
        # 缓存未命中，调用原始实现
        self.cache_misses += 1
        accumulated_response = ""
        
        async for chunk in super().chat_stream(messages, on_progress, task_id):
            if not chunk.done:
                accumulated_response += chunk.content
            yield chunk
        
        # 缓存响应
        if len(self.response_cache) >= self.cache_size:
            # 简单的 LRU 策略：删除第一个元素
            oldest_key = next(iter(self.response_cache))
            del self.response_cache[oldest_key]
        
        self.response_cache[cache_key] = accumulated_response
    
    def get_cache_stats(self) -> Dict[str, Union[int, float]]:
        """获取缓存统计信息"""
        total_requests = self.cache_hits + self.cache_misses
        hit_rate = self.cache_hits / max(1, total_requests)
        
        return {
            "cache_size": len(self.response_cache),
            "max_cache_size": self.cache_size,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate": hit_rate,
        }
    
    def clear_cache(self) -> None:
        """清空缓存"""
        self.response_cache.clear()
        self.cache_hits = 0
        self.cache_misses = 0