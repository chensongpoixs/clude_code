"""
Providers 模块导入迁移脚本

将 llama_cpp_http 导入替换为 http_client
"""

import re
from pathlib import Path
import sys

PROVIDER_DIR = Path("src/clude_code/llm/providers")
OLD_IMPORT = "from ..llama_cpp_http import"
NEW_IMPORT = "from ..http_client import"

def migrate_file(filepath: Path, dry_run: bool = True) -> bool:
    """迁移单个文件的导入"""
    content = filepath.read_text(encoding="utf-8")
    
    if OLD_IMPORT not in content:
        return False
    
    if dry_run:
        print(f"  [WILL CHANGE] {filepath.name}")
        # 显示具体要修改的行
        for i, line in enumerate(content.splitlines(), 1):
            if OLD_IMPORT in line:
                print(f"    Line {i}: {line.strip()}")
        return True
    
    new_content = content.replace(OLD_IMPORT, NEW_IMPORT)
    filepath.write_text(new_content, encoding="utf-8")
    print(f"  [CHANGED] {filepath.name}")
    return True

def main():
    if not PROVIDER_DIR.exists():
        print(f"Error: {PROVIDER_DIR} not found")
        sys.exit(1)
    
    files = list(PROVIDER_DIR.glob("*.py"))
    files = [f for f in files if not f.name.startswith("__")]
    
    print(f"Found {len(files)} provider files\n")
    
    # Dry-run
    print("=== Dry Run ===")
    changed_files = [f for f in files if migrate_file(f, dry_run=True)]
    
    if not changed_files:
        print("\n✓ No files need migration.")
        return
    
    print(f"\n{len(changed_files)} files will be changed.")
    
    # 检查是否在脚本模式（非交互）
    if "--execute" in sys.argv:
        confirm = "y"
    else:
        try:
            confirm = input("\nProceed with replacement? (y/n): ")
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
    print(f"\nNext steps:")
    print(f"  1. python -m compileall -q {PROVIDER_DIR}")
    print(f"  2. git diff {PROVIDER_DIR}")
    print(f"  3. python -c \"from clude_code.llm.providers import *\"")

if __name__ == "__main__":
    main()

