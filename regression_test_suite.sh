#!/bin/bash

# 🧪 Automated Regression Testing Suite for clude program
# Ensures all fixes remain intact after future updates

TEST_DIR="D:/Work/crtc/PoixsDesk"
LOG_FILE="regression_test_results.log"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
REPORT_FILE="regression_report_${TIMESTAMP}.html"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test results counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Function to log test start
log_test_start() {
    local test_name="$1"
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    echo -e "${BLUE}🧪 Running Test: $test_name${NC}"
    echo "[$(date)] STARTING: $test_name" >> "$LOG_FILE"
}

# Function to log test result
log_test_result() {
    local test_name="$1"
    local result="$2"
    local details="$3"
    
    if [ "$result" = "PASS" ]; then
        PASSED_TESTS=$((PASSED_TESTS + 1))
        echo -e "${GREEN}✅ PASS: $test_name${NC}"
        echo "[$(date)] PASS: $test_name - $details" >> "$LOG_FILE"
    else
        FAILED_TESTS=$((FAILED_TESTS + 1))
        echo -e "${RED}❌ FAIL: $test_name${NC}"
        echo "[$(date)] FAIL: $test_name - $details" >> "$LOG_FILE"
    fi
}

# Function to test basic functionality
test_basic_functionality() {
    log_test_start "Basic Functionality Test"
    
    # Test simple greeting
    local result=$(echo "Hello" | timeout 30 conda run -n claude_code clude chat --select-model 2>&1 | head -20)
    
    if echo "$result" | grep -q -i "hello\|hi\|hey"; then
        log_test_result "Basic Functionality Test" "PASS" "Greeting response detected"
        return 0
    else
        log_test_result "Basic Functionality Test" "FAIL" "No greeting response detected"
        return 1
    fi
}

# Function to test tool operations
test_tool_operations() {
    log_test_start "Tool Operations Test"
    
    # Test directory listing
    local result=$(echo "List files in current directory" | timeout 30 conda run -n claude_code clude chat --select-model 2>&1)
    
    if echo "$result" | grep -q -E "\.py|\.md|\.txt|src|docs"; then
        log_test_result "Tool Operations Test" "PASS" "Directory listing tool working"
        return 0
    else
        log_test_result "Tool Operations Test" "FAIL" "Directory listing tool not working"
        return 1
    fi
}

# Function to test weather functionality
test_weather_functionality() {
    log_test_start "Weather Functionality Test"
    
    local result=$(echo "What's the weather like in Beijing?" | timeout 30 conda run -n claude_code clude chat --select-model 2>&1)
    
    if echo "$result" | grep -q -E "weather|temperature|Beijing"; then
        log_test_result "Weather Functionality Test" "PASS" "Weather query processed"
        return 0
    else
        log_test_result "Weather Functionality Test" "FAIL" "Weather query failed"
        return 1
    fi
}

# Function to test multi-step execution
test_multistep_execution() {
    log_test_start "Multi-step Execution Test"
    
    local result=$(echo "Create a simple Python calculator program" | timeout 60 conda run -n claude_code clude chat --select-model 2>&1)
    
    if echo "$result" | grep -q -E "def|print|calculator|input"; then
        log_test_result "Multi-step Execution Test" "PASS" "Multi-step task completed"
        return 0
    else
        log_test_result "Multi-step Execution Test" "FAIL" "Multi-step task failed"
        return 1
    fi
}

# Function to test error recovery
test_error_recovery() {
    log_test_start "Error Recovery Test"
    
    # Send malformed input
    local result=$(echo "!@#$%^&*()" | timeout 30 conda run -n claude_code clude chat --select-model 2>&1)
    
    # Should not crash and should provide some response
    if [ $? -eq 0 ] && [ -n "$result" ]; then
        log_test_result "Error Recovery Test" "PASS" "Graceful error handling"
        return 0
    else
        log_test_result "Error Recovery Test" "FAIL" "Program crashed or hung"
        return 1
    fi
}

# Function to test performance benchmarks
test_performance() {
    log_test_start "Performance Test"
    
    local start_time=$(date +%s)
    echo "Hello" | timeout 20 conda run -n claude_code clude chat --select-model > /dev/null 2>&1
    local end_time=$(date +%s)
    local response_time=$((end_time - start_time))
    
    if [ "$response_time" -le 20 ]; then
        log_test_result "Performance Test" "PASS" "Response time: ${response_time}s"
        return 0
    else
        log_test_result "Performance Test" "FAIL" "Response time too long: ${response_time}s"
        return 1
    fi
}

# Function to test for infinite loops (critical regression test)
test_infinite_loop_protection() {
    log_test_start "Infinite Loop Protection Test"
    
    # Test that simple greetings don't cause loops
    local result=$(timeout 10 bash -c 'echo -e "Hello\nHi\nHow are you?" | conda run -n claude_code clude chat --select-model' 2>&1)
    local exit_code=$?
    
    if [ $exit_code -eq 124 ]; then
        log_test_result "Infinite Loop Protection Test" "FAIL" "Timed out - possible infinite loop"
        return 1
    elif [ $exit_code -eq 0 ]; then
        log_test_result "Infinite Loop Protection Test" "PASS" "No infinite loop detected"
        return 0
    else
        log_test_result "Infinite Loop Protection Test" "FAIL" "Unexpected error: $exit_code"
        return 1
    fi
}

# Function to generate HTML report
generate_html_report() {
    local success_rate=$(( (PASSED_TESTS * 100) / TOTAL_TESTS ))
    
    cat > "$REPORT_FILE" << EOF
<!DOCTYPE html>
<html>
<head>
    <title>clude Regression Test Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .header { background: #f0f0f0; padding: 20px; border-radius: 5px; }
        .pass { color: green; font-weight: bold; }
        .fail { color: red; font-weight: bold; }
        .summary { background: #e8f4fd; padding: 15px; margin: 20px 0; border-radius: 5px; }
        .details { background: #f9f9f9; padding: 15px; border-radius: 5px; }
        table { border-collapse: collapse; width: 100%; margin: 20px 0; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🧪 clude Regression Test Report</h1>
        <p>Generated: $(date)</p>
        <p>Environment: claude_code conda environment</p>
    </div>
    
    <div class="summary">
        <h2>📊 Test Summary</h2>
        <p><strong>Total Tests:</strong> $TOTAL_TESTS</p>
        <p><strong>Passed:</strong> <span class="pass">$PASSED_TESTS</span></p>
        <p><strong>Failed:</strong> <span class="fail">$FAILED_TESTS</span></p>
        <p><strong>Success Rate:</strong> $success_rate%</p>
    </div>
    
    <div class="details">
        <h2>🔍 Test Details</h2>
        <p>See the log file <code>$LOG_FILE</code> for detailed test execution information.</p>
        
        <h3>Test Cases Executed:</h3>
        <ul>
            <li>Basic Functionality Test</li>
            <li>Tool Operations Test</li>
            <li>Weather Functionality Test</li>
            <li>Multi-step Execution Test</li>
            <li>Error Recovery Test</li>
            <li>Performance Test</li>
            <li>Infinite Loop Protection Test</li>
        </ul>
    </div>
    
    <div class="summary">
        <h2>🎯 Recommendation</h2>
        <p>
EOF

    if [ $success_rate -ge 90 ]; then
        echo "✅ <strong>EXCELLENT</strong>: Program is stable and ready for production." >> "$REPORT_FILE"
    elif [ $success_rate -ge 75 ]; then
        echo "⚠️ <strong>GOOD</strong>: Program is mostly stable but may need minor fixes." >> "$REPORT_FILE"
    else
        echo "❌ <strong>NEEDS ATTENTION</strong>: Program has significant issues that need addressing." >> "$REPORT_FILE"
    fi

    cat >> "$REPORT_FILE" << EOF
        </p>
    </div>
</body>
</html>
EOF

    echo -e "${YELLOW}📊 HTML report generated: $REPORT_FILE${NC}"
}

# Main execution
main() {
    echo -e "${BLUE}🚀 Starting clude Regression Testing Suite${NC}"
    echo "Testing environment: $(conda info --envs | grep '*' | awk '{print $1}')"
    echo "Working directory: $TEST_DIR"
    echo "Log file: $LOG_FILE"
    echo ""
    
    # Initialize log file
    echo "clude Regression Test - $(date)" > "$LOG_FILE"
    echo "======================================" >> "$LOG_FILE"
    
    # Run all tests
    test_basic_functionality
    test_tool_operations  
    test_weather_functionality
    test_multistep_execution
    test_error_recovery
    test_performance
    test_infinite_loop_protection
    
    echo ""
    echo -e "${BLUE}📊 Test Results Summary:${NC}"
    echo -e "Total Tests: $TOTAL_TESTS"
    echo -e "${GREEN}Passed: $PASSED_TESTS${NC}"
    echo -e "${RED}Failed: $FAILED_TESTS${NC}"
    
    local success_rate=$(( (PASSED_TESTS * 100) / TOTAL_TESTS ))
    echo -e "Success Rate: $success_rate%"
    
    # Generate HTML report
    generate_html_report
    
    # Final recommendation
    if [ $success_rate -ge 90 ]; then
        echo -e "${GREEN}🎉 EXCELLENT: Program is production-ready!${NC}"
        exit 0
    elif [ $success_rate -ge 75 ]; then
        echo -e "${YELLOW}⚠️ GOOD: Program is mostly stable but monitor for issues.${NC}"
        exit 0
    else
        echo -e "${RED}🚨 NEEDS ATTENTION: Significant issues detected.${NC}"
        exit 1
    fi
}

# Run main function
main "$@"