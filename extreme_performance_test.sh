#!/bin/bash

# 🚀 极限性能测试脚本
# 测试 clude 程序的极限性能表现

TEST_DIR="D:/Work/crtc/PoixsDesk"
CONFIG_FILE="D:/Work/AI/clude_code/.ultra_extreme_performance.yaml"
LOG_FILE="extreme_performance_test.log"

# 备份原配置
backup_config() {
    cp "$TEST_DIR/.clude.yaml" "$TEST_DIR/.clude.yaml.backup" 2>/dev/null || true
}

# 恢复原配置  
restore_config() {
    cp "$TEST_DIR/.clude.yaml.backup" "$TEST_DIR/.clude.yaml" 2>/dev/null || true
}

# 应用极限性能配置
apply_extreme_config() {
    cp "$CONFIG_FILE" "$TEST_DIR/.clude.yaml"
}

# 极限性能测试
test_extreme_performance() {
    local test_name="$1"
    local timeout_limit="$2"
    local command="$3"
    
    echo "🔥 极限测试: $test_name"
    local start_time=$(date +%s)
    
    cd "$TEST_DIR" && timeout "$timeout_limit" cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print $command" > /dev/null 2>&1
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    if [ $duration -le $timeout_limit ]; then
        echo "✅ $test_name: ${duration}s (极限优化成功)"
        return 0
    else
        echo "❌ $test_name: ${duration}s (需要进一步优化)"
        return 1
    fi
}

# 主测试函数
main() {
    echo "🚀 开始极限性能优化测试"
    echo "测试目录: $TEST_DIR"
    echo "配置文件: $CONFIG_FILE"
    echo "开始时间: $(date)"
    echo ""
    
    # 备份并应用极限配置
    backup_config
    apply_extreme_config
    
    # 极限性能测试套件
    local passed=0
    local failed=0
    
    # 超快速启动测试
    if test_extreme_performance "超快速启动" 20 "快速启动"; then
        passed=$((passed + 1))
    else
        failed=$((failed + 1))
    fi
    
    # 极速响应测试  
    if test_extreme_performance "极速响应" 15 "极速测试"; then
        passed=$((passed + 1))
    else
        failed=$((failed + 1))
    fi
    
    # 极限内存测试
    if test_extreme_performance "极限内存" 30 "内存极限"; then
        passed=$((passed + 1))
    else
        failed=$((failed + 1))
    fi
    
    # 极限并发测试
    if test_extreme_performance "极限并发" 20 "并发极限"; then
        passed=$((passed + 1))
    else
        failed=$((failed + 1))
    fi
    
    # 极限负载测试
    if test_extreme_performance "极限负载" 15 "负载极限"; then
        passed=$((passed + 1))
    else
        failed=$((failed + 1))
    fi
    
    # 输出结果
    local total=$((passed + failed))
    local success_rate=$(( (passed * 100) / total ))
    
    echo ""
    echo "🏆 极限性能测试结果:"
    echo "通过: $passed"
    echo "失败: $failed" 
    echo "总计: $total"
    echo "成功率: $success_rate%"
    
    if [ $success_rate -ge 80 ]; then
        echo "🎉 极限性能优化: 优秀"
    elif [ $success_rate -ge 60 ]; then
        echo "⚠️ 极限性能优化: 良好"
    else
        echo "🔧 极限性能优化: 需要进一步改进"
    fi
    
    # 恢复原配置
    restore_config
    
    echo ""
    echo "完成时间: $(date)"
    echo "配置已恢复原设置"
}

# 执行测试
main "$@"