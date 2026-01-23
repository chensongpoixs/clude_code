"""
P3-2: 分类准确率监控

功能：
1. 记录分类结果和实际执行
2. 计算准确率统计
3. 提供监控报告

对齐业界最佳实践：
- LangSmith 风格的分类评估
- Prometheus 风格的指标统计
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ClassificationRecord:
    """分类记录"""
    timestamp: str
    user_text: str  # 截断后的用户输入
    predicted_category: str
    confidence: float
    classification_method: str  # "keyword" | "llm" | "hybrid"
    actual_category: str | None = None  # 用户反馈的实际分类
    trace_id: str = ""


@dataclass
class ClassificationStats:
    """分类统计"""
    total_classifications: int = 0
    keyword_hits: int = 0
    llm_classifications: int = 0
    hybrid_classifications: int = 0
    
    # 按类别统计
    category_counts: dict[str, int] = field(default_factory=dict)
    
    # 置信度分布
    high_confidence: int = 0  # >= 0.9
    medium_confidence: int = 0  # 0.7 - 0.9
    low_confidence: int = 0  # < 0.7
    
    # 准确率（需要用户反馈）
    confirmed_correct: int = 0
    confirmed_incorrect: int = 0


class ClassificationMonitor:
    """
    分类准确率监控器
    
    特性：
    - 记录每次分类结果
    - 计算统计指标
    - 支持导出报告
    - 线程安全
    """
    
    def __init__(self, log_dir: str | Path | None = None, max_records: int = 1000):
        """
        初始化监控器。
        
        参数:
            log_dir: 日志目录，None = 使用默认路径
            max_records: 内存中保留的最大记录数
        """
        self._records: list[ClassificationRecord] = []
        self._stats = ClassificationStats()
        self._max_records = max_records
        self._lock = threading.Lock()
        
        # 日志文件
        self._log_dir = Path(log_dir) if log_dir else Path.cwd() / ".clude" / "logs"
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self._log_dir / "classification_monitor.jsonl"
    
    def record(
        self,
        user_text: str,
        predicted_category: str,
        confidence: float,
        classification_method: str = "unknown",
        trace_id: str = "",
    ) -> None:
        """
        记录一次分类结果。
        
        参数:
            user_text: 用户输入（会被截断）
            predicted_category: 预测的分类
            confidence: 置信度
            classification_method: 分类方法（keyword/llm/hybrid）
            trace_id: 追踪 ID
        """
        record = ClassificationRecord(
            timestamp=datetime.utcnow().isoformat(),
            user_text=user_text[:100] + ("..." if len(user_text) > 100 else ""),
            predicted_category=predicted_category,
            confidence=confidence,
            classification_method=classification_method,
            trace_id=trace_id,
        )
        
        with self._lock:
            # 更新统计
            self._stats.total_classifications += 1
            
            # 方法统计
            if classification_method == "keyword":
                self._stats.keyword_hits += 1
            elif classification_method == "llm":
                self._stats.llm_classifications += 1
            elif classification_method == "hybrid":
                self._stats.hybrid_classifications += 1
            
            # 类别统计
            self._stats.category_counts[predicted_category] = \
                self._stats.category_counts.get(predicted_category, 0) + 1
            
            # 置信度分布
            if confidence >= 0.9:
                self._stats.high_confidence += 1
            elif confidence >= 0.7:
                self._stats.medium_confidence += 1
            else:
                self._stats.low_confidence += 1
            
            # 添加记录（LRU）
            self._records.append(record)
            if len(self._records) > self._max_records:
                self._records.pop(0)
        
        # 写入日志文件
        self._write_log(record)
    
    def feedback(
        self,
        trace_id: str,
        actual_category: str,
    ) -> bool:
        """
        记录用户反馈的实际分类。
        
        参数:
            trace_id: 追踪 ID
            actual_category: 用户反馈的实际分类
        
        返回:
            是否找到并更新了记录
        """
        with self._lock:
            for record in reversed(self._records):
                if record.trace_id == trace_id:
                    record.actual_category = actual_category
                    
                    # 更新准确率统计
                    if record.predicted_category == actual_category:
                        self._stats.confirmed_correct += 1
                    else:
                        self._stats.confirmed_incorrect += 1
                    
                    return True
        return False
    
    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            stats = self._stats
            
            # 计算派生指标
            total = stats.total_classifications or 1
            confirmed = stats.confirmed_correct + stats.confirmed_incorrect
            
            return {
                "total_classifications": stats.total_classifications,
                "classification_methods": {
                    "keyword": stats.keyword_hits,
                    "llm": stats.llm_classifications,
                    "hybrid": stats.hybrid_classifications,
                },
                "keyword_hit_rate": round(stats.keyword_hits / total * 100, 1),
                "category_distribution": dict(stats.category_counts),
                "confidence_distribution": {
                    "high": stats.high_confidence,
                    "medium": stats.medium_confidence,
                    "low": stats.low_confidence,
                },
                "accuracy": {
                    "confirmed_samples": confirmed,
                    "correct": stats.confirmed_correct,
                    "incorrect": stats.confirmed_incorrect,
                    "rate": round(stats.confirmed_correct / confirmed * 100, 1) if confirmed > 0 else None,
                },
            }
    
    def get_recent_records(self, limit: int = 10) -> list[dict[str, Any]]:
        """获取最近的分类记录"""
        with self._lock:
            records = self._records[-limit:]
            return [
                {
                    "timestamp": r.timestamp,
                    "user_text": r.user_text,
                    "predicted_category": r.predicted_category,
                    "confidence": r.confidence,
                    "classification_method": r.classification_method,
                    "actual_category": r.actual_category,
                    "trace_id": r.trace_id,
                }
                for r in reversed(records)
            ]
    
    def export_report(self) -> str:
        """导出监控报告（Markdown 格式）"""
        stats = self.get_stats()
        recent = self.get_recent_records(5)
        
        lines = [
            "# 分类准确率监控报告",
            "",
            f"**生成时间**: {datetime.utcnow().isoformat()}",
            "",
            "## 总体统计",
            "",
            f"- **总分类次数**: {stats['total_classifications']}",
            f"- **关键词命中率**: {stats['keyword_hit_rate']}%",
            "",
            "### 分类方法分布",
            "",
            f"- 关键词: {stats['classification_methods']['keyword']}",
            f"- LLM: {stats['classification_methods']['llm']}",
            f"- 混合: {stats['classification_methods']['hybrid']}",
            "",
            "### 置信度分布",
            "",
            f"- 高 (>=0.9): {stats['confidence_distribution']['high']}",
            f"- 中 (0.7-0.9): {stats['confidence_distribution']['medium']}",
            f"- 低 (<0.7): {stats['confidence_distribution']['low']}",
            "",
            "### 类别分布",
            "",
        ]
        
        for cat, count in sorted(stats['category_distribution'].items(), key=lambda x: -x[1]):
            lines.append(f"- {cat}: {count}")
        
        if stats['accuracy']['confirmed_samples'] > 0:
            lines.extend([
                "",
                "### 准确率（基于用户反馈）",
                "",
                f"- **已确认样本数**: {stats['accuracy']['confirmed_samples']}",
                f"- **正确**: {stats['accuracy']['correct']}",
                f"- **错误**: {stats['accuracy']['incorrect']}",
                f"- **准确率**: {stats['accuracy']['rate']}%",
            ])
        
        lines.extend([
            "",
            "## 最近分类记录",
            "",
        ])
        
        for r in recent:
            status = "✓" if r['actual_category'] == r['predicted_category'] else (
                "✗" if r['actual_category'] else "?"
            )
            lines.append(
                f"- [{status}] `{r['predicted_category']}` (置信度: {r['confidence']:.2f}) "
                f"- \"{r['user_text']}\""
            )
        
        return "\n".join(lines)
    
    def _write_log(self, record: ClassificationRecord) -> None:
        """写入日志文件"""
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "timestamp": record.timestamp,
                    "user_text": record.user_text,
                    "predicted_category": record.predicted_category,
                    "confidence": record.confidence,
                    "classification_method": record.classification_method,
                    "trace_id": record.trace_id,
                }, ensure_ascii=False) + "\n")
        except Exception:
            pass  # 日志写入失败不阻塞主流程
    
    def reset(self) -> None:
        """重置统计（用于测试）"""
        with self._lock:
            self._records.clear()
            self._stats = ClassificationStats()


# ============================================================
# 全局实例
# ============================================================

_default_monitor: ClassificationMonitor | None = None


def get_classification_monitor() -> ClassificationMonitor:
    """获取默认监控器（单例）"""
    global _default_monitor
    if _default_monitor is None:
        _default_monitor = ClassificationMonitor()
    return _default_monitor


def reset_classification_monitor() -> None:
    """重置默认监控器（用于测试）"""
    global _default_monitor
    _default_monitor = None

