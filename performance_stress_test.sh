#!/bin/bash

# 🚀 性能压力测试脚本
# 用于极限测试 clude 程序的性能表现

TEST_DIR="D:/Work/crtc/PoixsDesk"
LOG_FILE="performance_stress_test.log"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# 性能测试结果
PASSED_TESTS=0
FAILED_TESTS=0
TOTAL_TESTS=0

# 记录测试结果
log_test() {
    local test_name="$1"
    local result="$2"
    local duration="$3"
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    echo "[$(date)] $test_name: $result (${duration}s)" >> "$LOG_FILE"
    
    if [ "$result" = "PASS" ]; then
        PASSED_TESTS=$((PASSED_TESTS + 1))
    else
        FAILED_TESTS=$((FAILED_TESTS + 1))
    fi
}

# 启动时间测试
test_startup_time() {
    echo "🚀 测试启动时间..."
    local start_time=$(date +%s)
    
    cd "$TEST_DIR" && timeout 30 cmd //c "echo 1 | conda run -n claude_code clude chat --select-model" > /dev/null 2>&1
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    if [ $duration -le 30 ]; then
        log_test "启动时间测试" "PASS" "$duration"
        echo "✅ 启动时间: ${duration}s (< 30s)"
    else
        log_test "启动时间测试" "FAIL" "$duration"
        echo "❌ 启动时间过长: ${duration}s (> 30s)"
    fi
}

# 快速响应测试
test_quick_response() {
    echo "⚡ 测试快速响应..."
    local start_time=$(date +%s)
    
    cd "$TEST_DIR" && timeout 25 cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print 快速测试" > /dev/null 2>&1
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    if [ $duration -le 25 ]; then
        log_test "快速响应测试" "PASS" "$duration"
        echo "✅ 快速响应: ${duration}s (< 25s)"
    else
        log_test "快速响应测试" "FAIL" "$duration"
        echo "❌ 快速响应过慢: ${duration}s (> 25s)"
    fi
}

# 内存压力测试
test_memory_stress() {
    echo "🧠 测试内存压力..."
    local start_time=$(date +%s)
    
    cd "$TEST_DIR" && timeout 40 cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print 内存压力测试" > /dev/null 2>&1
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    if [ $duration -le 40 ]; then
        log_test "内存压力测试" "PASS" "$duration"
        echo "✅ 内存压力测试: ${duration}s (< 40s)"
    else
        log_test "内存压力测试" "FAIL" "$duration"
        echo "❌ 内存压力测试超时: ${duration}s (> 40s)"
    fi
}

# 极限负载测试
test_extreme_load() {
    echo "🔥 测试极限负载..."
    local start_time=$(date +%s)
    
    cd "$TEST_DIR" && timeout 20 cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print 极限测试" > /dev/null 2>&1
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    if [ $duration -le 20 ]; then
        log_test "极限负载测试" "PASS" "$duration"
        echo "✅ 极限负载测试: ${duration}s (< 20s)"
    else
        log_test "极限负载测试" "FAIL" "$duration"
        echo "❌ 极限负载测试失败: ${duration}s (> 20s)"
    fi
}

# 并发测试
test_concurrency() {
    echo "🔄 测试并发能力..."
    local start_time=$(date +%s)
    
    # 并发启动多个测试
    (
        cd "$TEST_DIR" && timeout 15 cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print 并发1" > /dev/null 2>&1 &
        cd "$TEST_DIR" && timeout 15 cmd //c "echo 1 | conda run -n claude_code clude chat --select-model --print 并发2" > /dev/null 2>&1 &
        wait
    )
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    if [ $duration -le 20 ]; then
        log_test "并发测试" "PASS" "$duration"
        echo "✅ 并发测试: ${duration}s (< 20s)"
    else
        log_test "并发测试" "FAIL" "$duration"
        echo "❌ 并发测试超时: ${duration}s (> 20s)"
    fi
}

# 主测试函数
main() {
    echo "🚀 开始 clude 性能压力测试"
    echo "测试目录: $TEST_DIR"
    echo "日志文件: $LOG_FILE"
    echo "开始时间: $(date)"
    echo ""
    
    # 初始化日志
    echo "clude 性能压力测试 - $(date)" > "$LOG_FILE"
    echo "======================================" >> "$LOG_FILE"
    
    # 执行所有测试
    test_startup_time
    test_quick_response
    test_memory_stress
    test_extreme_load
    test_concurrency
    
    # 输出结果
    echo ""
    echo "📊 测试结果汇总:"
    echo "总测试数: $TOTAL_TESTS"
    echo "通过: $PASSED_TESTS"
    echo "失败: $FAILED_TESTS"
    
    local success_rate=$(( (PASSED_TESTS * 100) / TOTAL_TESTS ))
    echo "成功率: $success_rate%"
    
    if [ $success_rate -ge 80 ]; then
        echo "🎉 性能测试: 优秀"
    elif [ $success_rate -ge 60 ]; then
        echo "⚠️ 性能测试: 良好"
    else
        echo "❌ 性能测试: 需要优化"
    fi
    
    echo ""
    echo "详细日志: $LOG_FILE"
    echo "完成时间: $(date)"
}

# 执行主函数
main "$@"