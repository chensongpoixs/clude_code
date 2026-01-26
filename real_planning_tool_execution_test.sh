#!/bin/bash

# 🔧 规划步骤和工具执行实际能力测试
# 验证 clude 程序是否真正执行规划步骤和工具调用，还是仅仅通过提示词"伪装"

TEST_DIR="D:/Work/crtc/PoixsDesk"
LOG_FILE="real_planning_tool_execution_test.log"

# 测试结果统计
declare -A execution_results

# 检测真实的工具调用
detect_real_tool_execution() {
    local test_id="$1"
    local test_name="$2"
    local command="$3"
    local timeout_limit="$4"
    
    echo "🧪 测试 $test_id: $test_name"
    local start_time=$(date +%s)
    
    # 执行测试并捕获完整输出
    cd "$TEST_DIR" && timeout "$timeout_limit" cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print $command" > "/tmp/execution_${test_id}.full_output" 2>&1
    
    local exit_code=$?
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    # 分析输出中的实际工具调用
    local real_tool_calls=0
    local planning_steps=0
    local json_tool_calls=0
    local step_done_count=0
    local actual_execution=0
    
    # 检测真实的工具调用日志
    if [ -f "/tmp/execution_${test_id}.full_output" ]; then
        # 检测工具执行日志
        real_tool_calls=$(grep -c -E "开始.*工具\|执行.*工具\|调用.*工具\|🔧\|🛠️\|📁\|🌐\|🔍" "/tmp/execution_${test_id}.full_output" 2>/dev/null || echo "0")
        
        # 检测规划步骤
        planning_steps=$(grep -c -E "步骤.*:|step_\|Step.*:|计划\|规划" "/tmp/execution_${test_id}.full_output" 2>/dev/null || echo "0")
        
        # 检测JSON工具调用
        json_tool_calls=$(grep -c -E "\"tool\".*:|\"args\".*:|{\"tool\"" "/tmp/execution_${test_id}.full_output" 2>/dev/null || echo "0")
        
        # 检测step_done
        step_done_count=$(grep -c -E "\"control\".*:.*\"step_done\"" "/tmp/execution_${test_id}.full_output" 2>/dev/null || echo "0")
        
        # 检测实际执行证据
        if [ -f "/tmp/execution_${test_id}.full_output" ]; then
            actual_execution=$(grep -c -E "✓.*工具.*执行\|✓.*步骤.*完成\|工具.*执行成功\|步骤.*执行完成" "/tmp/execution_${test_id}.full_output" 2>/dev/null || echo "0")
            
            # 额外检查文件创建证据
            if [ -f "$TEST_DIR/test_output.txt" ] || [ -f "$TEST_DIR/temp_file.txt" ] || [ -f "$TEST_DIR/result.txt" ]; then
                actual_execution=$((actual_execution + 1))
            fi
        fi
    fi
    
    # 判断执行质量
    local execution_quality="POOR"
    local execution_reason=""
    
    if [ $exit_code -eq 0 ]; then
        if [ $real_tool_calls -ge 1 ] && [ $json_tool_calls -ge 1 ]; then
            if [ $actual_execution -ge 1 ] || [ $step_done_count -ge 1 ]; then
                execution_quality="EXCELLENT"
                execution_reason="真实工具调用并实际执行完成"
            else
                execution_quality="GOOD"
                execution_reason="真实工具调用但执行证据不足"
            fi
        elif [ $json_tool_calls -ge 1 ]; then
            execution_quality="GOOD"
            execution_reason="JSON工具调用存在"
        elif [ $planning_steps -ge 1 ]; then
            execution_quality="FAIR"
            execution_reason="有规划步骤但工具调用不足"
        else
            execution_quality="POOR"
            execution_reason="无实际工具调用证据"
        fi
    else
        execution_quality="FAIL"
        execution_reason="执行失败或超时"
    fi
    
    # 记录详细结果
    execution_results["$test_id"]="$execution_quality:$duration:$real_tool_calls:$json_tool_calls:$planning_steps:$actual_execution:$step_done_count:$execution_reason"
    
    echo "   质量: $execution_quality (${duration}s)"
    echo "   工具调用: $real_tool_calls (日志) / $json_tool_calls (JSON)"
    echo "   规划步骤: $planning_steps"
    echo "   实际执行: $actual_execution / $step_done_count (step_done)"
    echo "   原因: $execution_reason"
    
    # 保存详细输出用于分析
    cp "/tmp/execution_${test_id}.full_output" "/tmp/execution_detail_${test_id}.log" 2>/dev/null
}

# 测试简单工具执行真实性
test_simple_tool_execution() {
    echo "🔧 测试简单工具执行真实性"
    
    # 测试1: 基础文件操作
    detect_real_tool_execution "ST001" "基础文件操作" "创建一个名为test_simple.txt的文件并写入Hello" 60
    
    # 测试2: 目录列表
    detect_real_tool_execution "ST002" "目录列表" "列出当前目录前5个文件的详细信息" 60
    
    # 测试3: 天气查询
    detect_real_tool_execution "ST003" "天气查询" "获取上海和北京两个城市的天气信息并比较" 90
    
    # 测试4: 文件读取
    detect_real_tool_execution "ST004" "文件读取" "读取README文件的内容并总结前100个字符" 60
    
    # 测试5: 简单搜索
    detect_real_tool_execution "ST005" "简单搜索" "在当前目录搜索包含'import'的所有Python文件" 60
}

# 测试复杂多步骤执行真实性
test_complex_multi_step_execution() {
    echo "🏗️ 测试复杂多步骤执行真实性"
    
    # 测试6: 多步骤文件操作
    detect_real_tool_execution "CM001" "多步骤文件操作" "1.创建项目结构 2.创建README.md 3.创建main.py文件" 120
    
    # 测试7: 分析+报告生成
    detect_real_tool_execution "CM002" "分析报告生成" "1.分析当前目录结构 2.统计文件类型 3.生成分析报告" 120
    
    # 测试8: 网络+文件集成
    detect_real_tool_execution "CM003" "网络文件集成" "1.获取天气信息 2.保存到文件 3.读取文件内容" 120
    
    # 测试9: 搜索+分析+总结
    detect_real_tool_execution "CM004" "搜索分析总结" "1.搜索所有配置文件 2.分析配置内容 3.总结配置用途" 150
    
    # 测试10: 错误处理和恢复
    detect_real_tool_execution "CM005" "错误处理恢复" "尝试读取不存在的文件，然后创建文件并重试" 90
}

# 测试规划逻辑的真实性
test_planning_logic_reality() {
    echo "🧠 测试规划逻辑真实性"
    
    # 测试11: 依赖关系处理
    detect_real_tool_execution "PL001" "依赖关系处理" "分析代码文件的依赖关系并生成依赖图" 120
    
    # 测试12: 条件分支执行
    detect_real_tool_execution "PL002" "条件分支执行" "如果存在README文件则读取，否则创建" 90
    
    # 测试13: 循环处理
    detect_real_tool_execution "PL003" "循环处理" "列出所有.py文件，对每个文件进行分析" 120
    
    # 测试14: 错误恢复策略
    detect_real_tool_execution "PL004" "错误恢复策略" "尝试多个可能的方法获取信息" 120
    
    # 测试15: 资源优化
    detect_real_tool_execution "PL005" "资源优化" "高效分析项目，避免重复操作" 120
}

# 测试工具链的真实执行
test_tool_chain_reality() {
    echo "🔗 测试工具链真实执行"
    
    # 测试16: 文件处理链
    detect_real_tool_execution "TC001" "文件处理链" "读取文件->分析内容->修改文件->验证修改" 150
    
    # 测试17: 网络数据链
    detect_real_tool_execution "TC002" "网络数据链" "获取天气->处理数据->格式化->保存结果" 150
    
    # 测试18: 搜索分析链
    detect_real_tool_execution "TC003" "搜索分析链" "搜索关键词->过滤结果->深度分析->总结" 150
    
    # 测试19: 命令执行链
    detect_real_tool_execution "TC004" "命令执行链" "运行命令->分析输出->记录结果->生成报告" 150
    
    # 测试20: 综合处理链
    detect_real_tool_execution "TC005" "综合处理链" "网络搜索->文件创建->代码生成->测试执行" 180
}

# 分析执行质量结果
analyze_execution_quality() {
    echo ""
    echo "📊 规划和工具执行质量分析"
    echo "=================================="
    
    local total_tests=0
    local excellent=0
    local good=0
    local fair=0
    local poor=0
    local fail=0
    local total_duration=0
    local total_real_tools=0
    local total_json_tools=0
    local total_actual_execution=0
    
    # 分类统计
    for test_id in "${!execution_results[@]}"; do
        local result="${execution_results[$test_id]}"
        local quality="${result%%:*}"
        local duration="${result#*:}"
        duration="${duration%%:*}"
        local real_tools="${result#*:*:}"
        real_tools="${real_tools%%:*}"
        local json_tools="${result#*:*:}"
        json_tools="${json_tools%%:*}"
        local actual_exec="${result#*:*:*:}"
        actual_exec="${actual_exec%%:*}"
        
        total_tests=$((total_tests + 1))
        total_duration=$((total_duration + duration))
        total_real_tools=$((total_real_tools + real_tools))
        total_json_tools=$((total_json_tools + json_tools))
        total_actual_execution=$((total_actual_execution + actual_exec))
        
        case "$quality" in
            "EXCELLENT") excellent=$((excellent + 1)) ;;
            "GOOD") good=$((good + 1)) ;;
            "FAIR") fair=$((fair + 1)) ;;
            "POOR") poor=$((poor + 1)) ;;
            "FAIL") fail=$((fail + 1)) ;;
        esac
        
        echo "🧪 $test_id: $quality (工具: $real_tools/$json_tools, 执行: $actual_exec)"
    done
    
    # 计算统计信息
    local avg_duration=0
    local success_rate=0
    local execution_rate=0
    
    if [ $total_tests -gt 0 ]; then
        avg_duration=$((total_duration / total_tests))
        success_rate=$((((excellent + good) * 100) / total_tests))
        execution_rate=$(( (total_actual_execution * 100) / total_tests ))
    fi
    
    echo ""
    echo "📈 质量统计:"
    echo "总测试数: $total_tests"
    echo "优秀: $excellent"
    echo "良好: $good"
    echo "一般: $fair"
    echo "较差: $poor"
    echo "失败: $fail"
    echo "成功率: $success_rate%"
    echo "实际执行率: $execution_rate%"
    echo "平均执行时间: ${avg_duration}s"
    echo "真实工具调用: $total_real_tools (日志) / $total_json_tools (JSON)"
    echo "实际执行证据: $total_actual_execution"
    
    # 深度分析
    echo ""
    echo "🔍 深度分析:"
    if [ $execution_rate -ge 80 ]; then
        echo "🎉 执行质量: 优秀"
        echo "   - 绝大多数任务都有实际执行"
        echo "   - 工具调用真实有效"
        echo "   - 规划逻辑正确执行"
    elif [ $execution_rate -ge 60 ]; then
        echo "✅ 执行质量: 良好"
        echo "   - 大部分任务有实际执行"
        echo "   - 工具调用基本有效"
        echo "   - 规划逻辑基本正确"
    elif [ $execution_rate -ge 40 ]; then
        echo "⚠️ 执行质量: 一般"
        echo "   - 部分任务有实际执行"
        echo "   - 工具调用有时无效"
        echo "   - 规划逻辑有待改进"
    else
        echo "❌ 执行质量: 需要改进"
        echo "   - 大部分任务缺乏实际执行"
        echo "   - 工具调用可能只是输出JSON"
        echo "   - 规划逻辑可能只是提示词"
    fi
    
    # 生成关键建议
    echo ""
    echo "💡 关键发现和建议:"
    
    if [ $total_json_tools -gt $total_real_tools ]; then
        echo "🔍 发现: JSON工具调用数量($total_json_tools) > 日志工具调用数量($total_real_tools)"
        echo "   - 可能存在工具调用只是JSON输出而非实际执行"
        echo "   - 建议检查工具实现的真实性"
    fi
    
    if [ $execution_rate -lt 50 ]; then
        echo "🔍 发现: 实际执行率过低 ($execution_rate%)"
        echo "   - 可能过度依赖提示词优化"
        echo "   - 建议增强实际工具执行能力"
    fi
    
    if [ $avg_duration -gt 100 ]; then
        echo "🔍 发现: 平均执行时间过长 (${avg_duration}s)"
        echo "   - 可能存在效率问题或无效执行"
        echo "   - 建议优化工具执行流程"
    fi
    
    # 输出详细的问题案例
    echo ""
    echo "❌ 需要改进的案例:"
    for test_id in "${!execution_results[@]}"; do
        local result="${execution_results[$test_id]}"
        local quality="${result%%:*}"
        local reason="${result##*:}"
        
        if [ "$quality" = "POOR" ] || [ "$quality" = "FAIL" ]; then
            echo "   $test_id: $reason"
        fi
    done
}

# 主函数
main() {
    echo "🧪 开始规划步骤和工具执行实际能力测试"
    echo "测试目的: 验证是否真正执行规划步骤和工具，而非仅通过提示词优化"
    echo "测试目录: $TEST_DIR"
    echo "开始时间: $(date)"
    echo ""
    
    # 初始化日志
    echo "规划步骤和工具执行实际能力测试" > "$LOG_FILE"
    echo "开始时间: $(date)" >> "$LOG_FILE"
    echo "======================================" >> "$LOG_FILE"
    
    # 执行各类测试
    test_simple_tool_execution
    test_complex_multi_step_execution
    test_planning_logic_reality
    test_tool_chain_reality
    
    # 分析结果
    analyze_execution_quality
    
    # 记录到日志
    echo "" >> "$LOG_FILE"
    echo "完成时间: $(date)" >> "$LOG_FILE"
    echo "总测试数: $total_tests" >> "$LOG_FILE"
    echo "实际执行率: $execution_rate%" >> "$LOG_FILE"
    echo "关键发现: JSON工具调用($total_json_tools) vs 日志工具调用($total_real_tools)" >> "$LOG_FILE"
    
    echo ""
    echo "详细日志: $LOG_FILE"
    echo "测试完成时间: $(date)"
}

# 执行主函数
main "$@"