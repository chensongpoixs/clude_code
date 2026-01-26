#!/bin/bash

# 🛠️ 工具通用功能完整性测试
# 验证 clude 程序所有工具的基本功能是否正常工作

TEST_DIR="D:/Work/crtc/PoixsDesk"
LOG_FILE="tool_functionality_test.log"

# 工具测试结果统计
declare -A tool_results

# 测试文件操作工具
test_file_tools() {
    echo "📁 测试文件操作工具"
    
    # 测试 list_dir 工具
    echo "  测试 list_dir 工具..."
    local start_time=$(date +%s)
    cd "$TEST_DIR" && timeout 60 cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print 列出当前目录的文件" > /tmp/list_dir_test.log 2>&1
    local exit_code=$?
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    if [ $exit_code -eq 0 ] && [ $duration -le 60 ]; then
        tool_results["list_dir"]="PASS:$duration"
        echo "    ✅ list_dir 工具正常 (${duration}s)"
    else
        tool_results["list_dir"]="FAIL:$duration"
        echo "    ❌ list_dir 工具异常 (${duration}s)"
    fi
    
    # 测试 read_file 工具
    echo "  测试 read_file 工具..."
    start_time=$(date +%s)
    cd "$TEST_DIR" && timeout 60 cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print 读取README文件" > /tmp/read_file_test.log 2>&1
    exit_code=$?
    end_time=$(date +%s)
    duration=$((end_time - start_time))
    
    if [ $exit_code -eq 0 ] && [ $duration -le 60 ]; then
        tool_results["read_file"]="PASS:$duration"
        echo "    ✅ read_file 工具正常 (${duration}s)"
    else
        tool_results["read_file"]="FAIL:$duration"
        echo "    ❌ read_file 工具异常 (${duration}s)"
    fi
}

# 测试网络工具
test_network_tools() {
    echo "🌐 测试网络工具"
    
    # 测试 get_weather 工具
    echo "  测试 get_weather 工具..."
    local start_time=$(date +%s)
    cd "$TEST_DIR" && timeout 90 cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print 获取北京天气" > /tmp/weather_test.log 2>&1
    local exit_code=$?
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    if [ $exit_code -eq 0 ] && [ $duration -le 90 ]; then
        tool_results["get_weather"]="PASS:$duration"
        echo "    ✅ get_weather 工具正常 (${duration}s)"
    else
        tool_results["get_weather"]="FAIL:$duration"
        echo "    ❌ get_weather 工具异常 (${duration}s)"
    fi
}

# 测试搜索工具
test_search_tools() {
    echo "🔍 测试搜索工具"
    
    # 测试 grep 工具
    echo "  测试 grep 工具..."
    local start_time=$(date +%s)
    cd "$TEST_DIR" && timeout 60 cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print 搜索包含import的Python文件" > /tmp/grep_test.log 2>&1
    local exit_code=$?
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    if [ $exit_code -eq 0 ] && [ $duration -le 60 ]; then
        tool_results["grep"]="PASS:$duration"
        echo "    ✅ grep 工具正常 (${duration}s)"
    else
        tool_results["grep"]="FAIL:$duration"
        echo "    ❌ grep 工具异常 (${duration}s)"
    fi
    
    # 测试 glob_search 工具
    echo "  测试 glob_search 工具..."
    start_time=$(date +%s)
    cd "$TEST_DIR" && timeout 60 cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print 查找所有.py文件" > /tmp/glob_test.log 2>&1
    exit_code=$?
    end_time=$(date +%s)
    duration=$((end_time - start_time))
    
    if [ $exit_code -eq 0 ] && [ $duration -le 60 ]; then
        tool_results["glob_search"]="PASS:$duration"
        echo "    ✅ glob_search 工具正常 (${duration}s)"
    else
        tool_results["glob_search"]="FAIL:$duration"
        echo "    ❌ glob_search 工具异常 (${duration}s)"
    fi
}

# 测试命令执行工具
test_command_tools() {
    echo "💻 测试命令执行工具"
    
    # 测试 run_cmd 工具（简单命令）
    echo "  测试 run_cmd 工具..."
    local start_time=$(date +%s)
    cd "$TEST_DIR" && timeout 60 cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print 执行dir命令" > /tmp/cmd_test.log 2>&1
    local exit_code=$?
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    if [ $exit_code -eq 0 ] && [ $duration -le 60 ]; then
        tool_results["run_cmd"]="PASS:$duration"
        echo "    ✅ run_cmd 工具正常 (${duration}s)"
    else
        tool_results["run_cmd"]="FAIL:$duration"
        echo "    ❌ run_cmd 工具异常 (${duration}s)"
    fi
}

# 测试显示工具
test_display_tools() {
    echo "📊 测试显示工具"
    
    # 测试 display 工具
    echo "  测试 display 工具..."
    local start_time=$(date +%s)
    cd "$TEST_DIR" && timeout 45 cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print 显示测试信息" > /tmp/display_test.log 2>&1
    local exit_code=$?
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    if [ $exit_code -eq 0 ] && [ $duration -le 45 ]; then
        tool_results["display"]="PASS:$duration"
        echo "    ✅ display 工具正常 (${duration}s)"
    else
        tool_results["display"]="FAIL:$duration"
        echo "    ❌ display 工具异常 (${duration}s)"
    fi
}

# 测试写操作工具
test_write_tools() {
    echo "✏️ 测试写操作工具"
    
    # 测试 write_file 工具
    echo "  测试 write_file 工具..."
    local start_time=$(date +%s)
    cd "$TEST_DIR" && timeout 60 cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print 创建测试文件" > /tmp/write_test.log 2>&1
    local exit_code=$?
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    if [ $exit_code -eq 0 ] && [ $duration -le 60 ]; then
        tool_results["write_file"]="PASS:$duration"
        echo "    ✅ write_file 工具正常 (${duration}s)"
    else
        tool_results["write_file"]="FAIL:$duration"
        echo "    ❌ write_file 工具异常 (${duration}s)"
    fi
    
    # 清理测试文件
    rm -f "$TEST_DIR/test.txt" 2>/dev/null || true
}

# 测试任务管理工具
test_task_tools() {
    echo "📋 测试任务管理工具"
    
    # 测试 todowrite 工具
    echo "  测试 todowrite 工具..."
    local start_time=$(date +%s)
    cd "$TEST_DIR" && timeout 60 cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print 创建任务列表" > /tmp/todowrite_test.log 2>&1
    local exit_code=$?
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    if [ $exit_code -eq 0 ] && [ $duration -le 60 ]; then
        tool_results["todowrite"]="PASS:$duration"
        echo "    ✅ todowrite 工具正常 (${duration}s)"
    else
        tool_results["todowrite"]="FAIL:$duration"
        echo "    ❌ todowrite 工具异常 (${duration}s)"
    fi
    
    # 测试 todoread 工具
    echo "  测试 todoread 工具..."
    start_time=$(date +%s)
    cd "$TEST_DIR" && timeout 60 cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print 读取任务列表" > /tmp/todoread_test.log 2>&1
    exit_code=$?
    end_time=$(date +%s)
    duration=$((end_time - start_time))
    
    if [ $exit_code -eq 0 ] && [ $duration -le 60 ]; then
        tool_results["todoread"]="PASS:$duration"
        echo "    ✅ todoread 工具正常 (${duration}s)"
    else
        tool_results["todoread"]="FAIL:$duration"
        echo "    ❌ todoread 工具异常 (${duration}s)"
    fi
}

# 测试搜索和AI工具
test_ai_tools() {
    echo "🤖 测试搜索和AI工具"
    
    # 测试 websearch 工具
    echo "  测试 websearch 工具..."
    local start_time=$(date +%s)
    cd "$TEST_DIR" && timeout 90 cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print 搜索Python教程" > /tmp/websearch_test.log 2>&1
    local exit_code=$?
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    if [ $exit_code -eq 0 ] && [ $duration -le 90 ]; then
        tool_results["websearch"]="PASS:$duration"
        echo "    ✅ websearch 工具正常 (${duration}s)"
    else
        tool_results["websearch"]="FAIL:$duration"
        echo "    ❌ websearch 工具异常 (${duration}s)"
    fi
    
    # 测试 codesearch 工具
    echo "  测试 codesearch 工具..."
    start_time=$(date +%s)
    cd "$TEST_DIR" && timeout 90 cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print 搜索Python代码示例" > /tmp/codesearch_test.log 2>&1
    exit_code=$?
    end_time=$(date +%s)
    duration=$((end_time - start_time))
    
    if [ $exit_code -eq 0 ] && [ $duration -le 90 ]; then
        tool_results["codesearch"]="PASS:$duration"
        echo "    ✅ codesearch 工具正常 (${duration}s)"
    else
        tool_results["codesearch"]="FAIL:$duration"
        echo "    ❌ codesearch 工具异常 (${duration}s)"
    fi
}

# 测试分析工具
test_analysis_tools() {
    echo "🔍 测试分析工具"
    
    # 测试 analyze_image 工具（如果没有图片则测试其他）
    echo "  测试项目分析功能..."
    local start_time=$(date +%s)
    cd "$TEST_DIR" && timeout 90 cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print 分析项目结构" > /tmp/analysis_test.log 2>&1
    local exit_code=$?
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    if [ $exit_code -eq 0 ] && [ $duration -le 90 ]; then
        tool_results["project_analysis"]="PASS:$duration"
        echo "    ✅ 项目分析功能正常 (${duration}s)"
    else
        tool_results["project_analysis"]="FAIL:$duration"
        echo "    ❌ 项目分析功能异常 (${duration}s)"
    fi
}

# 分析测试结果
analyze_tool_results() {
    echo ""
    echo "📊 工具测试结果分析"
    echo "===================="
    
    local total_tools=0
    local passed_tools=0
    local failed_tools=0
    local total_duration=0
    
    # 统计结果
    for tool in "${!tool_results[@]}"; do
        local result="${tool_results[$tool]}"
        local status="${result%%:*}"
        local duration="${result#*:}"
        
        total_tools=$((total_tools + 1))
        total_duration=$((total_duration + duration))
        
        case "$status" in
            "PASS") passed_tools=$((passed_tools + 1)) ;;
            "FAIL") failed_tools=$((failed_tools + 1)) ;;
        esac
        
        echo "🛠️ $tool: $status (${duration}s)"
    done
    
    # 计算统计信息
    local success_rate=0
    local avg_duration=0
    
    if [ $total_tools -gt 0 ]; then
        success_rate=$(( (passed_tools * 100) / total_tools ))
        avg_duration=$((total_duration / total_tools ))
    fi
    
    echo ""
    echo "📈 统计摘要:"
    echo "总工具数: $total_tools"
    echo "通过: $passed_tools"
    echo "失败: $failed_tools"
    echo "成功率: $success_rate%"
    echo "平均响应时间: ${avg_duration}s"
    
    # 工具分类统计
    echo ""
    echo "🗂️ 工具分类统计:"
    
    local file_tools_passed=0
    local file_tools_total=0
    local network_tools_passed=0
    local network_tools_total=0
    local ai_tools_passed=0
    local ai_tools_total=0
    
    # 分类统计
    for tool in "${!tool_results[@]}"; do
        local result="${tool_results[$tool]}"
        local status="${result%%:*}"
        
        case "$tool" in
            "list_dir"|"read_file"|"write_file"|"glob_search")
                file_tools_total=$((file_tools_total + 1))
                if [ "$status" = "PASS" ]; then
                    file_tools_passed=$((file_tools_passed + 1))
                fi
                ;;
            "get_weather"|"websearch"|"codesearch"|"webfetch")
                network_tools_total=$((network_tools_total + 1))
                if [ "$status" = "PASS" ]; then
                    network_tools_passed=$((network_tools_passed + 1))
                fi
                ;;
            "grep"|"run_cmd"|"display"|"todowrite"|"todoread")
                ai_tools_total=$((ai_tools_total + 1))
                if [ "$status" = "PASS" ]; then
                    ai_tools_passed=$((ai_tools_passed + 1))
                fi
                ;;
        esac
    done
    
    echo "文件操作工具: $file_tools_passed/$file_tools_total"
    echo "网络工具: $network_tools_passed/$network_tools_total"
    echo "AI工具: $ai_tools_passed/$ai_tools_total"
    
    # 生成评估结论
    echo ""
    echo "🏆 工具完整性评估:"
    if [ $success_rate -ge 90 ]; then
        echo "🎉 工具完整性: 优秀"
        echo "   - 绝大多数工具功能正常"
        echo "   - 系统工具生态完整"
        echo "   - 适合生产环境使用"
    elif [ $success_rate -ge 75 ]; then
        echo "✅ 工具完整性: 良好"
        echo "   - 大部分工具功能正常"
        echo "   - 基本工具生态完整"
        echo "   - 适合一般使用"
    elif [ $success_rate -ge 60 ]; then
        echo "⚠️ 工具完整性: 一般"
        echo "   - 超过一半工具功能正常"
        echo "   - 部分工具存在问题"
        echo "   - 建议优化改进"
    else
        echo "❌ 工具完整性: 需要改进"
        echo "   - 大部分工具存在问题"
        echo "   - 工具生态不完整"
        echo "   - 需要重点修复"
    fi
    
    echo ""
    echo "🔧 改进建议:"
    if [ $failed_tools -gt 0 ]; then
        echo "   - 有 $failed_tools 个工具需要修复"
        echo "   - 建议重点检查失败的工具配置"
        echo "   - 验证工具依赖和网络连接"
    fi
    
    if [ $avg_duration -gt 60 ]; then
        echo "   - 平均响应时间较长 (${avg_duration}s)"
        echo "   - 建议优化工具执行效率"
        echo "   - 考虑增加超时时间配置"
    fi
}

# 主函数
main() {
    echo "🛠️ 开始工具通用功能完整性测试"
    echo "测试目录: $TEST_DIR"
    echo "开始时间: $(date)"
    echo ""
    
    # 初始化日志
    echo "工具通用功能完整性测试" > "$LOG_FILE"
    echo "开始时间: $(date)" >> "$LOG_FILE"
    echo "=========================" >> "$LOG_FILE"
    
    # 执行各类工具测试
    test_file_tools
    test_network_tools
    test_search_tools
    test_command_tools
    test_display_tools
    test_write_tools
    test_task_tools
    test_ai_tools
    test_analysis_tools
    
    # 分析结果
    analyze_tool_results
    
    # 记录到日志
    echo "" >> "$LOG_FILE"
    echo "完成时间: $(date)" >> "$LOG_FILE"
    echo "总工具数: $total_tools" >> "$LOG_FILE"
    echo "通过率: $success_rate%" >> "$LOG_FILE"
    
    echo ""
    echo "详细日志: $LOG_FILE"
    echo "工具通用功能完整性测试完成"
}

# 执行测试
main "$@"