#!/usr/bin/env python3
"""
LLM Provider 命名规范检查脚本

检查规则:
1. 文件名必须全小写
2. 只允许字母、数字和下划线
3. 不能以数字或下划线开头
4. PROVIDER_ID 必须与文件名一致
5. 必须包含 PROVIDER_NAME、PROVIDER_TYPE、REGION 属性

用法:
    python scripts/check_provider_naming.py
    python scripts/check_provider_naming.py --verbose
    python scripts/check_provider_naming.py --fix  # 显示修复建议

返回码:
    0: 所有检查通过
    1: 发现命名问题
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import NamedTuple


class CheckResult(NamedTuple):
    """检查结果"""
    file: str
    passed: bool
    errors: list[str]
    warnings: list[str]


def check_filename(filename: str) -> list[str]:
    """检查文件名格式"""
    errors = []
    name = filename.replace(".py", "")
    
    # 跳过特殊文件
    if name.startswith("_"):
        return []
    
    # 规则 1: 全小写
    if name != name.lower():
        errors.append(f"文件名包含大写字母: {filename} → 建议: {name.lower()}.py")
    
    # 规则 2: 只允许字母、数字和下划线
    if not re.match(r'^[a-z][a-z0-9_]*$', name):
        errors.append(f"文件名格式不规范: {filename} (只允许小写字母、数字和下划线，且不能以数字开头)")
    
    return errors


def check_provider_class(filepath: Path, verbose: bool = False) -> tuple[list[str], list[str]]:
    """检查 Provider 类定义"""
    errors = []
    warnings = []
    
    filename = filepath.stem  # 不含 .py
    
    # 跳过特殊文件
    if filename.startswith("_"):
        return [], []
    
    try:
        content = filepath.read_text(encoding="utf-8")
        tree = ast.parse(content)
    except Exception as e:
        errors.append(f"无法解析文件: {e}")
        return errors, warnings
    
    # 查找 Provider 类
    provider_class = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name.endswith("Provider"):
            provider_class = node
            break
    
    if not provider_class:
        warnings.append("未找到 *Provider 类")
        return errors, warnings
    
    # 检查类属性
    required_attrs = {
        "PROVIDER_ID": None,
        "PROVIDER_NAME": None,
        "PROVIDER_TYPE": None,
        "REGION": None,
    }
    
    for node in provider_class.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in required_attrs:
                    if isinstance(node.value, ast.Constant):
                        required_attrs[target.id] = node.value.value
    
    # 规则 4: PROVIDER_ID 与文件名一致
    provider_id = required_attrs.get("PROVIDER_ID")
    if provider_id and provider_id != filename:
        errors.append(f"PROVIDER_ID ('{provider_id}') 与文件名 ('{filename}') 不一致")
    
    # 规则 5: 检查必要属性
    for attr, value in required_attrs.items():
        if value is None:
            warnings.append(f"缺少类属性: {attr}")
    
    # 检查 PROVIDER_TYPE 值
    valid_types = {"cloud", "local", "aggregator"}
    provider_type = required_attrs.get("PROVIDER_TYPE")
    if provider_type and provider_type not in valid_types:
        warnings.append(f"PROVIDER_TYPE 值不规范: '{provider_type}' (应为 {valid_types})")
    
    # 检查 REGION 值
    valid_regions = {"海外", "国内", "通用", "海外/合规"}
    region = required_attrs.get("REGION")
    if region and region not in valid_regions:
        warnings.append(f"REGION 值不规范: '{region}' (应为 {valid_regions})")
    
    return errors, warnings


def check_provider(filepath: Path, verbose: bool = False) -> CheckResult:
    """检查单个 Provider 文件"""
    errors = []
    warnings = []
    
    # 检查文件名
    filename_errors = check_filename(filepath.name)
    errors.extend(filename_errors)
    
    # 检查类定义
    class_errors, class_warnings = check_provider_class(filepath, verbose)
    errors.extend(class_errors)
    warnings.extend(class_warnings)
    
    return CheckResult(
        file=str(filepath.name),
        passed=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


def main():
    parser = argparse.ArgumentParser(description="检查 LLM Provider 命名规范")
    parser.add_argument("--verbose", "-v", action="store_true", help="显示详细信息")
    parser.add_argument("--fix", action="store_true", help="显示修复建议")
    parser.add_argument("--path", default="src/clude_code/llm/providers", help="Provider 目录路径")
    args = parser.parse_args()
    
    providers_dir = Path(args.path)
    if not providers_dir.exists():
        print(f"❌ 目录不存在: {providers_dir}")
        sys.exit(1)
    
    # 扫描所有 .py 文件
    files = list(providers_dir.glob("*.py"))
    files = [f for f in files if not f.name.startswith("__")]
    
    results: list[CheckResult] = []
    for filepath in sorted(files):
        result = check_provider(filepath, args.verbose)
        results.append(result)
    
    # 输出结果
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    
    print(f"\n{'='*60}")
    print(f"LLM Provider 命名规范检查")
    print(f"{'='*60}")
    print(f"扫描文件: {total}")
    print(f"通过: {passed} ✅")
    print(f"失败: {failed} {'❌' if failed else ''}")
    print(f"{'='*60}\n")
    
    # 详细输出
    has_issues = False
    for result in results:
        if result.errors or (args.verbose and result.warnings):
            has_issues = True
            status = "❌" if result.errors else "⚠️"
            print(f"{status} {result.file}")
            for err in result.errors:
                print(f"   错误: {err}")
            if args.verbose:
                for warn in result.warnings:
                    print(f"   警告: {warn}")
            print()
    
    if not has_issues:
        print("✅ 所有 Provider 命名规范检查通过！\n")
    
    # 修复建议
    if args.fix and failed > 0:
        print(f"\n{'='*60}")
        print("修复建议")
        print(f"{'='*60}")
        for result in results:
            if result.errors:
                print(f"\n📝 {result.file}:")
                for err in result.errors:
                    print(f"   {err}")
    
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()

