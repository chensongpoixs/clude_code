#!/bin/bash

# 🧠 大量规划和流程调用合理性测试
# 验证 clude 程序在各种复杂场景下的规划能力和工具调用合理性

TEST_DIR="D:/Work/crtc/PoixsDesk"
LOG_FILE="massive_planning_test.log"

# 测试结果统计
declare -A test_results

# 规划合理性测试函数
test_planning_reasonableness() {
    local test_id="$1"
    local test_name="$2"
    local command="$3"
    local expected_steps="$4"
    local timeout_limit="$5"
    
    echo "🧪 测试 $test_id: $test_name"
    local start_time=$(date +%s)
    
    # 执行测试并捕获输出
    cd "$TEST_DIR" && timeout "$timeout_limit" cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print $command" > "/tmp/test_${test_id}.output" 2>&1
    
    local exit_code=$?
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    # 分析输出中的规划元素
    local plan_keywords=$(grep -c -i "计划\|步骤\|规划\|执行" "/tmp/test_${test_id}.output" 2>/dev/null || echo "0")
    local step_count=$(grep -c -i "step_\|步骤\|工具" "/tmp/test_${test_id}.output" 2>/dev/null || echo "0")
    local completion=$(grep -c -i "完成\|执行完成\|计划执行完成" "/tmp/test_${test_id}.output" 2>/dev/null || echo "0")
    local error_count=$(grep -c -i "错误\|失败\|异常\|超时" "/tmp/test_${test_id}.output" 2>/dev/null || echo "0")
    
    # 判断测试结果
    local test_result="FAIL"
    local test_reason=""
    
    if [ $exit_code -eq 0 ] && [ $completion -ge 1 ]; then
        if [ $plan_keywords -ge 2 ] && [ $step_count -ge $expected_steps ]; then
            test_result="PASS"
            test_reason="规划合理，执行完成"
        elif [ $plan_keywords -ge 1 ] && [ $completion -ge 1 ]; then
            test_result="PARTIAL"
            test_reason="规划部分合理，执行完成"
        else
            test_result="WEAK"
            test_reason="规划不充分，但执行完成"
        fi
    elif [ $error_count -gt 0 ]; then
        test_result="ERROR"
        test_reason="出现错误: $(head -3 "/tmp/test_${test_id}.output" | grep -i "错误\|失败" | head -1)"
    else
        test_result="TIMEOUT"
        test_reason="执行超时 (${timeout_limit}s)"
    fi
    
    # 记录结果
    test_results["$test_id"]="$test_result:$duration:$test_reason"
    
    echo "   结果: $test_result (${duration}s) - $test_reason"
    
    # 清理临时文件
    rm -f "/tmp/test_${test_id}.output" 2>/dev/null
}

# 批量规划测试套件
run_batch_planning_tests() {
    echo "🚀 开始大量规划和流程调用合理性测试"
    echo "测试开始时间: $(date)"
    echo ""
    
    # 简单规划测试套件
    echo "=== 简单规划测试套件 ==="
    
    test_planning_reasonableness "P001" "单步骤规划" "你好" 0 30
    test_planning_reasonableness "P002" "基础文件操作" "列出当前目录" 1 45
    test_planning_reasonableness "P003" "简单查询" "当前时间" 1 30
    test_planning_reasonableness "P004" "基本工具调用" "获取天气" 2 60
    
    echo ""
    echo "=== 中等复杂度规划测试套件 ==="
    
    test_planning_reasonableness "P005" "文件分析" "分析项目结构" 3 90
    test_planning_reasonableness "P006" "代码创建" "创建Python程序" 3 90
    test_planning_reasonableness "P007" "多步骤任务" "获取天气并写入文件" 3 120
    test_planning_reasonableness "P008" "项目重构" "重构代码结构" 4 120
    
    echo ""
    echo "=== 高复杂度规划测试套件 ==="
    
    test_planning_reasonableness "P009" "复杂项目分析" "深入分析整个项目架构" 5 150
    test_planning_reasonableness "P010" "多工具集成" "分析项目并生成报告" 5 150
    test_planning_reasonableness "P011" "复杂重构" "系统性重构项目代码" 6 180
    test_planning_reasonableness "P012" "完整工作流" "创建完整项目结构" 6 180
    
    echo ""
    echo "=== 边界条件规划测试套件 ==="
    
    test_planning_reasonableness "P013" "超长请求" "$(printf '分析%.0s' {1..100})" 3 120
    test_planning_reasonableness "P014" "空输入处理" "" 1 30
    test_planning_reasonableness "P015" "特殊字符" "!@#$%^&*()" 1 30
    test_planning_reasonableness "P016" "多层嵌套任务" "分析项目中的文件并修改并测试" 5 150
    
    echo ""
    echo "=== 工具调用合理性测试套件 ==="
    
    test_planning_reasonableness "P017" "文件工具链" "读取多个文件并合并内容" 4 120
    test_planning_reasonableness "P018" "网络工具链" "获取天气、搜索信息并保存" 5 150
    test_planning_reasonableness "P019" "命令工具链" "执行命令并分析输出" 3 90
    test_planning_reasonableness "P020" "混合工具链" "文件分析+网络查询+命令执行" 6 180
    
    echo ""
    echo "=== 规划逻辑合理性测试套件 ==="
    
    test_planning_reasonableness "P021" "逻辑推理" "根据文件内容推断项目类型" 3 90
    test_planning_reasonableness "P022" "依赖分析" "分析项目依赖关系" 4 120
    test_planning_reasonableness "P023" "风险评估" "识别项目潜在问题" 3 90
    test_planning_reasonableness "P024" "优化建议" "提供性能优化建议" 3 90
    test_planning_reasonableness "P025" "错误诊断" "分析代码错误原因" 4 120
}

# 统计和分析结果
analyze_results() {
    echo ""
    echo "📊 测试结果统计分析"
    echo "===================="
    
    local total_tests=0
    local passed_tests=0
    local partial_tests=0
    local weak_tests=0
    local error_tests=0
    local timeout_tests=0
    
    local total_duration=0
    local avg_duration=0
    
    # 统计各类测试数量
    for test_id in "${!test_results[@]}"; do
        local result="${test_results[$test_id]}"
        local test_type="${result%%:*}"
        local duration="${result#*:}"
        duration="${duration%%:*}"
        
        total_tests=$((total_tests + 1))
        total_duration=$((total_duration + duration))
        
        case "$test_type" in
            "PASS") passed_tests=$((passed_tests + 1)) ;;
            "PARTIAL") partial_tests=$((partial_tests + 1)) ;;
            "WEAK") weak_tests=$((weak_tests + 1)) ;;
            "ERROR") error_tests=$((error_tests + 1)) ;;
            "TIMEOUT") timeout_tests=$((timeout_tests + 1)) ;;
        esac
    done
    
    # 计算平均时间
    if [ $total_tests -gt 0 ]; then
        avg_duration=$((total_duration / total_tests))
    fi
    
    # 输出统计结果
    echo "总测试数: $total_tests"
    echo "通过: $passed_tests"
    echo "部分通过: $partial_tests"
    echo "弱通过: $weak_tests"
    echo "错误: $error_tests"
    echo "超时: $timeout_tests"
    echo "平均执行时间: ${avg_duration}s"
    
    # 计算成功率
    local success_rate=0
    local acceptable_rate=0
    
    if [ $total_tests -gt 0 ]; then
        success_rate=$(( (passed_tests * 100) / total_tests ))
        acceptable_rate=$(( ((passed_tests + partial_tests) * 100) / total_tests ))
    fi
    
    echo ""
    echo "📈 成功率分析:"
    echo "完全成功率: $success_rate%"
    echo "可接受率: $acceptable_rate%"
    
    # 详细失败分析
    if [ $error_tests -gt 0 ] || [ $timeout_tests -gt 0 ]; then
        echo ""
        echo "❌ 失败详情:"
        for test_id in "${!test_results[@]}"; do
            local result="${test_results[$test_id]}"
            local test_type="${result%%:*}"
            local test_reason="${result#*:*:}"
            
            if [ "$test_type" = "ERROR" ] || [ "$test_type" = "TIMEOUT" ]; then
                echo "  $test_id: $test_type - $test_reason"
            fi
        done
    fi
    
    # 生成评估结论
    echo ""
    echo "🏆 评估结论:"
    if [ $success_rate -ge 80 ]; then
        echo "🎉 规划和流程调用: 优秀"
        echo "   - 规划能力强，逻辑清晰"
        echo "   - 工具调用合理，执行稳定"
        echo "   - 适合生产环境使用"
    elif [ $success_rate -ge 60 ]; then
        echo "✅ 规划和流程调用: 良好"
        echo "   - 规划能力基本满足要求"
        echo "   - 工具调用基本合理"
        echo "   - 建议继续优化"
    elif [ $success_rate -ge 40 ]; then
        echo "⚠️ 规划和流程调用: 一般"
        echo "   - 规划能力有待提升"
        echo "   - 工具调用需要改进"
        echo "   - 建议重点优化"
    else
        echo "❌ 规划和流程调用: 需要改进"
        echo "   - 规划能力严重不足"
        echo "   - 工具调用存在严重问题"
        echo "   - 需要立即修复"
    fi
    
    echo ""
    echo "💡 改进建议:"
    if [ $weak_tests -gt 0 ]; then
        echo "   - $weak_tests 个测试规划不充分，需要增强规划深度"
    fi
    if [ $error_tests -gt 0 ]; then
        echo "   - $error_tests 个测试出现错误，需要改进错误处理"
    fi
    if [ $timeout_tests -gt 0 ]; then
        echo "   - $timeout_tests 个测试超时，需要优化执行效率"
    fi
}

# 主函数
main() {
    # 创建日志文件
    echo "大量规划和流程调用合理性测试" > "$LOG_FILE"
    echo "开始时间: $(date)" >> "$LOG_FILE"
    echo "========================" >> "$LOG_FILE"
    
    # 运行批量测试
    run_batch_planning_tests
    
    # 分析结果
    analyze_results
    
    # 记录到日志
    echo "" >> "$LOG_FILE"
    echo "完成时间: $(date)" >> "$LOG_FILE"
    echo "测试数量: $total_tests" >> "$LOG_FILE"
    echo "完全成功率: $success_rate%" >> "$LOG_FILE"
    
    echo ""
    echo "详细日志: $LOG_FILE"
    echo "测试完成时间: $(date)"
}

# 执行主函数
main "$@"