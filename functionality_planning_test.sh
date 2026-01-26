#!/bin/bash

# 🧠 功能性和规划流程合理性测试
# 验证 clude 程序在性能优化的同时保持功能完整性

TEST_DIR="D:/Work/crtc/PoixsDesk"
STANDARD_CONFIG="D:/Work/AI/clude_code/.clude.yaml"
LOG_FILE="functionality_planning_test.log"

# 恢复标准配置
restore_standard_config() {
    cp "$STANDARD_CONFIG" "$TEST_DIR/.clude.yaml" 2>/dev/null || echo "使用默认配置"
}

# 功能性测试
test_functionality() {
    local test_name="$1"
    local command="$2"
    local timeout_limit="$3"
    
    echo "🧠 功能性测试: $test_name"
    local start_time=$(date +%s)
    
    cd "$TEST_DIR" && timeout "$timeout_limit" cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print $command" > /dev/null 2>&1
    
    local exit_code=$?
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    if [ $exit_code -eq 0 ] && [ $duration -le $timeout_limit ]; then
        echo "✅ 功能正常: $test_name (${duration}s)"
        return 0
    else
        echo "❌ 功能异常: $test_name (exit_code: $exit_code, ${duration}s)"
        return 1
    fi
}

# 规划流程合理性测试
test_planning_reasonableness() {
    local test_name="$1"
    local command="$2"
    local timeout_limit="$3"
    
    echo "📋 规划合理性测试: $test_name"
    local start_time=$(date +%s)
    
    # 检查输出中是否包含合理的规划关键词
    cd "$TEST_DIR" && timeout "$timeout_limit" cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print $command" 2>&1 | grep -E "计划|步骤|执行|分析|创建|完成" | head -3 > /tmp/planning_check.txt
    
    local exit_code=$?
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    if [ $exit_code -eq 0 ] && [ -s /tmp/planning_check.txt ]; then
        echo "✅ 规划合理: $test_name (${duration}s)"
        return 0
    else
        echo "⚠️ 规划异常: $test_name (${duration}s)"
        return 1
    fi
}

# 复杂任务执行测试
test_complex_task_execution() {
    local test_name="$1"
    local command="$2"
    local timeout_limit="$3"
    
    echo "🔧 复杂任务测试: $test_name"
    local start_time=$(date +%s)
    
    cd "$TEST_DIR" && timeout "$timeout_limit" cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print $command" 2>&1 | grep -E "步骤|工具|完成|计划执行完成" | wc -l > /tmp/complex_task_count.txt
    
    local exit_code=$?
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local step_count=$(cat /tmp/complex_task_count.txt 2>/dev/null || echo "0")
    
    if [ $exit_code -eq 0 ] && [ $step_count -ge 1 ]; then
        echo "✅ 复杂任务正常: $test_name (${duration}s, ${step_count}步骤)"
        return 0
    else
        echo "❌ 复杂任务异常: $test_name (${duration}s, ${step_count}步骤)"
        return 1
    fi
}

# 工具调用完整性测试
test_tool_calling_completeness() {
    local test_name="$1"
    local command="$2"
    local timeout_limit="$3"
    
    echo "🛠️ 工具调用测试: $test_name"
    local start_time=$(date +%s)
    
    cd "$TEST_DIR" && timeout "$timeout_limit" cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print $command" 2>&1 | grep -E "工具|tool|list_dir|get_weather|write_file" | head -3 > /tmp/tool_check.txt
    
    local exit_code=$?
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    if [ $exit_code -eq 0 ] && [ -s /tmp/tool_check.txt ]; then
        echo "✅ 工具调用正常: $test_name (${duration}s)"
        return 0
    else
        echo "❌ 工具调用异常: $test_name (${duration}s)"
        return 1
    fi
}

# 主测试函数
main() {
    echo "🧠 开始功能性和规划流程合理性测试"
    echo "测试目录: $TEST_DIR"
    echo "开始时间: $(date)"
    echo ""
    
    # 恢复标准配置进行功能性测试
    restore_standard_config
    
    # 初始化计数器
    local functionality_passed=0
    local functionality_failed=0
    local planning_passed=0
    local planning_failed=0
    local complex_passed=0
    local complex_failed=0
    local tool_passed=0
    local tool_failed=0
    
    # 功能性测试套件
    echo "=== 功能性测试套件 ==="
    if test_functionality "基础对话" "你好世界" 60; then
        functionality_passed=$((functionality_passed + 1))
    else
        functionality_failed=$((functionality_failed + 1))
    fi
    
    if test_functionality "天气查询" "获取北京的天气" 90; then
        functionality_passed=$((functionality_passed + 1))
    else
        functionality_failed=$((functionality_failed + 1))
    fi
    
    if test_functionality "文件操作" "列出当前目录的文件" 60; then
        functionality_passed=$((functionality_passed + 1))
    else
        functionality_failed=$((functionality_failed + 1))
    fi
    
    # 规划合理性测试套件
    echo ""
    echo "=== 规划合理性测试套件 ==="
    if test_planning_reasonableness "项目分析" "分析当前项目的结构" 90; then
        planning_passed=$((planning_passed + 1))
    else
        planning_failed=$((planning_failed + 1))
    fi
    
    if test_planning_reasonableness "代码创建" "创建一个Python Hello World程序" 90; then
        planning_passed=$((planning_passed + 1))
    else
        planning_failed=$((planning_failed + 1))
    fi
    
    # 复杂任务执行测试套件
    echo ""
    echo "=== 复杂任务执行测试套件 ==="
    if test_complex_task_execution "多步骤任务" "分析项目并创建报告" 120; then
        complex_passed=$((complex_passed + 1))
    else
        complex_failed=$((complex_failed + 1))
    fi
    
    if test_complex_task_execution "集成任务" "获取天气信息并保存到文件" 120; then
        complex_passed=$((complex_passed + 1))
    else
        complex_failed=$((complex_failed + 1))
    fi
    
    # 工具调用完整性测试套件
    echo ""
    echo "=== 工具调用完整性测试套件 ==="
    if test_tool_calling_completeness "文件工具" "读取和分析当前目录" 90; then
        tool_passed=$((tool_passed + 1))
    else
        tool_failed=$((tool_failed + 1))
    fi
    
    if test_tool_calling_completeness "网络工具" "获取实时天气信息" 90; then
        tool_passed=$((tool_passed + 1))
    else
        tool_failed=$((tool_failed + 1))
    fi
    
    # 输出结果统计
    echo ""
    echo "📊 测试结果统计:"
    
    # 功能性统计
    local functionality_total=$((functionality_passed + functionality_failed))
    local functionality_success_rate=0
    if [ $functionality_total -gt 0 ]; then
        functionality_success_rate=$(( (functionality_passed * 100) / functionality_total ))
    fi
    echo "🧠 功能性测试: $functionality_passed/$functionality_total ($functionality_success_rate%)"
    
    # 规划合理性统计
    local planning_total=$((planning_passed + planning_failed))
    local planning_success_rate=0
    if [ $planning_total -gt 0 ]; then
        planning_success_rate=$(( (planning_passed * 100) / planning_total ))
    fi
    echo "📋 规划合理性: $planning_passed/$planning_total ($planning_success_rate%)"
    
    # 复杂任务统计
    local complex_total=$((complex_passed + complex_failed))
    local complex_success_rate=0
    if [ $complex_total -gt 0 ]; then
        complex_success_rate=$(( (complex_passed * 100) / complex_total ))
    fi
    echo "🔧 复杂任务执行: $complex_passed/$complex_total ($complex_success_rate%)"
    
    # 工具调用统计
    local tool_total=$((tool_passed + tool_failed))
    local tool_success_rate=0
    if [ $tool_total -gt 0 ]; then
        tool_success_rate=$(( (tool_passed * 100) / tool_total ))
    fi
    echo "🛠️ 工具调用完整性: $tool_passed/$tool_total ($tool_success_rate%)"
    
    # 总体评估
    local total_passed=$((functionality_passed + planning_passed + complex_passed + tool_passed))
    local total_failed=$((functionality_failed + planning_failed + complex_failed + tool_failed))
    local total_tests=$((total_passed + total_failed))
    local overall_success_rate=0
    if [ $total_tests -gt 0 ]; then
        overall_success_rate=$(( (total_passed * 100) / total_tests ))
    fi
    
    echo ""
    echo "🏆 总体评估:"
    echo "总测试数: $total_tests"
    echo "通过: $total_passed"
    echo "失败: $total_failed"
    echo "总体成功率: $overall_success_rate%"
    
    if [ $overall_success_rate -ge 90 ]; then
        echo "🎉 功能性和规划流程: 优秀"
    elif [ $overall_success_rate -ge 75 ]; then
        echo "✅ 功能性和规划流程: 良好"
    elif [ $overall_success_rate -ge 60 ]; then
        echo "⚠️ 功能性和规划流程: 一般"
    else
        echo "❌ 功能性和规划流程: 需要改进"
    fi
    
    echo ""
    echo "完成时间: $(date)"
    echo "功能性和规划流程合理性测试完成"
}

# 执行测试
main "$@"