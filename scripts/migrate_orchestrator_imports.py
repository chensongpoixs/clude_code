"""
Orchestrator 模块导入迁移脚本（高风险）

将 llama_cpp_http 导入替换为 http_client
"""

import sys
from pathlib import Path

ORCHESTRATOR_FILES = [
    "src/clude_code/orchestrator/agent_loop/llm_io.py",
    "src/clude_code/orchestrator/advanced_context.py",
    "src/clude_code/orchestrator/agent_loop/planning.py",
    "src/clude_code/orchestrator/agent_loop/execution.py",
    "src/clude_code/orchestrator/agent_loop/react.py",
    "src/clude_code/orchestrator/agent_loop/agent_loop.py",
    "src/clude_code/orchestrator/classifier.py",
]

OLD_IMPORT_1 = "from clude_code.llm.llama_cpp_http import"
NEW_IMPORT_1 = "from clude_code.llm.http_client import"

def migrate_file(filepath: str, dry_run: bool = True) -> bool:
    """迁移单个文件的导入"""
    p = Path(filepath)
    if not p.exists():
        print(f"  [SKIP] {p.name} (不存在)")
        return False
    
    content = p.read_text(encoding="utf-8")
    
    if OLD_IMPORT_1 not in content:
        return False
    
    if dry_run:
        print(f"  [WILL CHANGE] {p.name}")
        for i, line in enumerate(content.splitlines(), 1):
            if OLD_IMPORT_1 in line:
                print(f"    Line {i}: {line.strip()}")
        return True
    
    new_content = content.replace(OLD_IMPORT_1, NEW_IMPORT_1)
    p.write_text(new_content, encoding="utf-8")
    print(f"  [CHANGED] {p.name}")
    return True

def main():
    print("=== Orchestrator 模块迁移（高风险）===\n")
    
    # Dry-run
    print("=== Dry Run ===")
    changed_files = [f for f in ORCHESTRATOR_FILES if migrate_file(f, dry_run=True)]
    
    if not changed_files:
        print("\n✓ No files need migration.")
        return
    
    print(f"\n{len(changed_files)} files will be changed.")
    print("\n⚠️  警告：这是核心模块，建议逐个迁移并测试！")
    
    if "--execute" in sys.argv:
        confirm = "y"
    else:
        try:
            confirm = input("\nProceed? (y/n): ")
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            return
    
    if confirm.lower() != 'y':
        print("Aborted.")
        return
    
    # Execute
    print("\n=== Executing ===")
    for f in changed_files:
        migrate_file(f, dry_run=False)
    
    print(f"\n✓ Done! {len(changed_files)} files migrated.")
    print(f"\n⚠️  重要：请立即运行以下验证：")
    print(f"  1. python -m compileall -q src/clude_code/orchestrator")
    print(f"  2. python -c \"from clude_code.orchestrator import agent_loop\"")
    print(f"  3. clude chat  # 完整功能测试")

if __name__ == "__main__":
    main()

