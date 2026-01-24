"""
剩余模块导入迁移脚本

将 llama_cpp_http 导入替换为 http_client
"""

import sys
from pathlib import Path

REMAINING_FILES = [
    # LLM 辅助模块
    "src/clude_code/llm/failover.py",
    "src/clude_code/llm/streaming_client.py",
    # CLI 模块
    "src/clude_code/cli/session_store.py",
    "src/clude_code/cli/info_cmds.py",
    "src/clude_code/cli/doctor_cmd.py",
    "src/clude_code/cli/utils.py",
    # Config
    "src/clude_code/config/config_wizard.py",
    # Plugins
    "src/clude_code/plugins/ui/enhanced_chat_handler.py",
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
        print(f"  [WILL CHANGE] {p}")
        for i, line in enumerate(content.splitlines(), 1):
            if OLD_IMPORT_1 in line:
                print(f"    Line {i}: {line.strip()}")
        return True
    
    new_content = content.replace(OLD_IMPORT_1, NEW_IMPORT_1)
    p.write_text(new_content, encoding="utf-8")
    print(f"  [CHANGED] {p}")
    return True

def main():
    print("=== 剩余模块迁移 (CLI + 辅助) ===\n")
    
    # Dry-run
    print("=== Dry Run ===")
    changed_files = [f for f in REMAINING_FILES if migrate_file(f, dry_run=True)]
    
    if not changed_files:
        print("\n✓ No files need migration.")
        return
    
    print(f"\n{len(changed_files)} files will be changed.")
    
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
    print(f"\n验证：")
    print(f"  python -m compileall -q src")
    print(f"  grep -r 'llama_cpp_http' src/")

if __name__ == "__main__":
    main()

