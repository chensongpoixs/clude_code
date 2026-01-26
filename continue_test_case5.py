#!/usr/bin/env python3
"""
继续监控测试案例5的执行状态
"""
import sys
import os
import time
import subprocess
import signal

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def check_test_case_5_status():
    """检查测试案例5的执行状态"""
    print("🔍 检查测试案例5执行状态...\n")
    
    try:
        # 检查工具输出目录中的最新文件
        import glob
        tool_output_dir = r"C:\Users\chen_song\.local\share\opencode\tool-output"
        
        if os.path.exists(tool_output_dir):
            files = glob.glob(os.path.join(tool_output_dir, "tool_*"))
            if files:
                latest_file = max(files, key=os.path.getctime)
                file_time = os.path.getctime(latest_file)
                print(f"最新工具输出文件: {os.path.basename(latest_file)}")
                print(f"修改时间: {time.ctime(file_time)}\n")
                
                # 读取部分内容了解状态
                with open(latest_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(2000)  # 读取前2000字符
                    print("文件内容预览:")
                    print("=" * 50)
                    print(content)
                    print("=" * 50)
            else:
                print("未找到工具输出文件")
        else:
            print("工具输出目录不存在")
            
        # 检查libcommon目录状态
        print(f"\n📁 检查libcommon目录状态:")
        libcommon_dir = r"D:/Work/crtc/PoixsDesk/libcommon"
        if os.path.exists(libcommon_dir):
            target_files = ['casync_log.h', 'casync_log.cpp', 'clog.h', 'clog.cpp']
            for file in target_files:
                file_path = os.path.join(libcommon_dir, file)
                if os.path.exists(file_path):
                    size = os.path.getsize(file_path)
                    print(f"  ✅ {file}: {size:,} bytes")
                else:
                    print(f"  ❌ {file}: 不存在")
        else:
            print("libcommon目录不存在")
            
    except Exception as e:
        print(f"检查失败: {e}")

def restart_test_case_5():
    """重新启动测试案例5"""
    print("\n🚀 重新启动测试案例5...\n")
    
    cmd = [
        r'/d/Anaconda/opencode/Scripts/clude.exe',
        'chat', '--select-model', '-p', 
        '读取当前项目中libcommon目录下casync_log.h/cpp,clog.h/cpp 文件每个函数内容原理说明 列出所有类名中所有函数及其类的成员函数原理说明'
    ]
    
    print("执行命令:", ' '.join(cmd))
    print("工作目录: D:/Work/crtc/PoixsDesk")
    print("\n⚠️ 注意: 这个测试可能需要几分钟完成")
    print("📋 计划步骤:")
    print("  1. 列出libcommon目录文件")
    print("  2. 读取casync_log.h")
    print("  3. 读取casync_log.cpp") 
    print("  4. 读取clog.h")
    print("  5. 读取clog.cpp")
    print("  6. 分析文件内容")
    print("  7. 输出结构化结果")
    print("\n🎯 验收标准:")
    print("  - 找到并读取所有4个目标文件")
    print("  - 提取每个函数及其原理说明")
    print("  - 列出所有类及其成员函数")
    print("  - 输出结构正确，信息完整")
    print("  - 路径检测: 采用'文件定位->并行读取->语法解析->结构化提取->模板化输出'高效路径")
    
    try:
        # 在Windows环境下设置正确的工作目录
        env = os.environ.copy()
        
        # 启动进程
        process = subprocess.Popen(
            cmd,
            cwd=r"D:/Work/crtc/PoixsDesk",
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8'
        )
        
        print(f"\n🔄 进程已启动，PID: {process.pid}")
        print("按 Ctrl+C 中断测试\n")
        
        # 实时输出
        try:
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    print(output.strip())
                    
            # 等待进程结束
            return_code = process.poll()
            if return_code == 0:
                print("\n✅ 测试案例5执行完成")
            else:
                print(f"\n❌ 测试案例5执行失败，返回码: {return_code}")
                
        except KeyboardInterrupt:
            print("\n⏹️ 用户中断测试")
            process.terminate()
            process.wait()
            
    except Exception as e:
        print(f"启动失败: {e}")

def continue_test_suite():
    """继续执行测试套件"""
    print("📋 测试套件当前状态:")
    print("  ✅ 测试案例1: 环境验证 - 完成")
    print("  ✅ 测试案例3: 简单对话 - 完成") 
    print("  ✅ 测试案例4: 天气查询 - 完成")
    print("  🔄 测试案例5: 文件解析 - 进行中")
    print("  ⏳ 测试案例6: 城市数据整合 - 待执行")
    print("  ⏳ 测试案例8: 生成项目文档 - 待执行")
    print("  ⏳ 测试案例9: 代码重构分析 - 待执行")
    print("  ⏳ 测试案例10: 错误调试修复 - 待执行")

if __name__ == "__main__":
    print("🧪 测试案例5状态检查与继续执行")
    print("=" * 60)
    
    # 检查当前状态
    check_test_case_5_status()
    
    # 继续执行测试套件
    continue_test_suite()
    
    print("\n" + "=" * 60)
    choice = input("选择操作:\n1. 检查状态\n2. 重新启动测试案例5\n3. 继续执行下一个测试案例\n请输入选择 (1/2/3): ")
    
    if choice == "2":
        restart_test_case_5()
    elif choice == "3":
        print("准备执行测试案例6...")
        # 这里可以添加测试案例6的执行代码
    else:
        print("仅显示当前状态")