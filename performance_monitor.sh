#!/bin/bash

# 📊 Performance Monitoring Script for clude program
# Monitors resource usage, response times, and error rates

MONITOR_INTERVAL=60  # seconds
LOG_FILE="D:/Work/crtc/PoixsDesk/performance_monitor.log"
ALERT_THRESHOLD_CPU=80  # percentage
ALERT_THRESHOLD_MEMORY=85  # percentage
ALERT_THRESHOLD_RESPONSE_TIME=30  # seconds

# Create log directory if not exists
mkdir -p "$(dirname "$LOG_FILE")"

# Function to log with timestamp
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Function to check CPU usage
check_cpu_usage() {
    local cpu_usage=$(ps aux | grep "clude" | grep -v grep | awk '{sum+=$3} END {print sum}')
    if (( $(echo "$cpu_usage > $ALERT_THRESHOLD_CPU" | bc -l) )); then
        log_message "🚨 ALERT: High CPU usage detected: ${cpu_usage}%"
        return 1
    fi
    return 0
}

# Function to check memory usage
check_memory_usage() {
    local memory_usage=$(ps aux | grep "clude" | grep -v grep | awk '{sum+=$4} END {print sum}')
    if (( $(echo "$memory_usage > $ALERT_THRESHOLD_MEMORY" | bc -l) )); then
        log_message "🚨 ALERT: High memory usage detected: ${memory_usage}%"
        return 1
    fi
    return 0
}

# Function to check clude process health
check_clude_health() {
    if ! pgrep -f "clude" > /dev/null; then
        log_message "🚨 ALERT: clude process is not running"
        return 1
    fi
    return 0
}

# Function to test response time
test_response_time() {
    local start_time=$(date +%s)
    
    # Test simple query
    echo "Hello" | timeout 30 conda run -n claude_code clude chat --select-model > /dev/null 2>&1
    
    local end_time=$(date +%s)
    local response_time=$((end_time - start_time))
    
    if [ "$response_time" -gt "$ALERT_THRESHOLD_RESPONSE_TIME" ]; then
        log_message "🚨 ALERT: Slow response time detected: ${response_time}s"
        return 1
    fi
    
    log_message "✅ Response time: ${response_time}s"
    return 0
}

# Function to check error logs
check_error_logs() {
    local error_count=$(grep -c "ERROR\|CRITICAL\|FATAL" "$LOG_FILE" 2>/dev/null || echo "0")
    if [ "$error_count" -gt 5 ]; then  # More than 5 errors in monitoring period
        log_message "🚨 ALERT: High error count detected: $error_count errors"
        return 1
    fi
    return 0
}

# Main monitoring loop
log_message "🚀 Starting performance monitoring for clude program"
log_message "📊 Monitoring interval: ${MONITOR_INTERVAL}s"
log_message "⚠️  CPU threshold: ${ALERT_THRESHOLD_CPU}%"
log_message "⚠️  Memory threshold: ${ALERT_THRESHOLD_MEMORY}%"
log_message "⚠️  Response time threshold: ${ALERT_THRESHOLD_RESPONSE_TIME}s"

while true; do
    log_message "🔍 Performing health checks..."
    
    local alerts=0
    
    # Run all checks
    check_cpu_usage || ((alerts++))
    check_memory_usage || ((alerts++))
    check_clude_health || ((alerts++))
    test_response_time || ((alerts++))
    check_error_logs || ((alerts++))
    
    if [ "$alerts" -eq 0 ]; then
        log_message "✅ All systems normal"
    else
        log_message "⚠️  $alerts alerts triggered in this cycle"
    fi
    
    log_message "💤 Sleeping for ${MONITOR_INTERVAL}s..."
    sleep "$MONITOR_INTERVAL"
done