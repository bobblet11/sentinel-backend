#!/bin/bash

# =============================================================================
# HKU CS GPU Farm Auto-Cleanup Script
# Author: GitHub Copilot
# Date: 2025-10-06
# =============================================================================

# Configuration - should match your setup script
CONDA_ENV_NAME="finalyear"
JUPYTER_PORT=8888
PHASE=2
GATEWAY_HOST="gpu${PHASE}gate1.cs.hku.hk"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging function
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Function to check if expect is available and install if needed
ensure_expect() {
    if ! command -v expect >/dev/null 2>&1; then
        log "Installing expect for automation..."
        if [[ "$OSTYPE" == "linux-gnu"* ]]; then
            if command -v apt-get >/dev/null 2>&1; then
                sudo apt-get update && sudo apt-get install -y expect
            elif command -v yum >/dev/null 2>&1; then
                sudo yum install -y expect
            elif command -v apk >/dev/null 2>&1; then
                sudo apk add expect
            else
                error "Cannot install expect automatically. Please install it manually."
                return 1
            fi
        elif [[ "$OSTYPE" == "darwin"* ]]; then
            if command -v brew >/dev/null 2>&1; then
                brew install expect
            else
                error "Please install expect: brew install expect"
                return 1
            fi
        else
            error "Unsupported OS for automatic expect installation"
            return 1
        fi
    fi
    return 0
}

# Function to create cleanup expect script
create_cleanup_expect_script() {
    local expect_script=$(mktemp)
    cat > "$expect_script" << 'EXPECT_EOF'
#!/usr/bin/expect -f

set timeout 60
set password [lindex $argv 0]
set portal_id [lindex $argv 1]
set gateway [lindex $argv 2]

log_user 1

# Connect to gateway
spawn ssh -o StrictHostKeyChecking=no ${portal_id}@${gateway}
expect {
    "password:" {
        send "${password}\r"
        exp_continue
    }
    "$ " {
        # Check for existing GPU sessions
        send "squeue -u ${portal_id}\r"
        expect "$ "
        
        # Get job IDs and cancel them
        send "squeue -u ${portal_id} --noheader --format='%i' | while read jobid; do echo \"Cancelling job: \$jobid\"; scancel \$jobid; done\r"
        expect "$ "
        
        # Wait a moment for jobs to be cancelled
        send "sleep 3\r"
        expect "$ "
        
        # Verify no jobs are running
        send "squeue -u ${portal_id} | grep -q ${portal_id} && echo 'JOBS_STILL_RUNNING' || echo 'ALL_JOBS_CANCELLED'\r"
        expect {
            "ALL_JOBS_CANCELLED" {
                puts "CLEANUP_SUCCESS"
                expect "$ "
            }
            "JOBS_STILL_RUNNING" {
                puts "CLEANUP_PARTIAL"
                expect "$ "
                send "squeue -u ${portal_id}\r"
                expect "$ "
            }
        }
        
        # Clean up any remaining processes
        send "pkill -u ${portal_id} -f jupyter\r"
        expect "$ "
        send "pkill -u ${portal_id} -f tmux\r"
        expect "$ "
        
        puts "CLEANUP_COMPLETE"
        send "exit\r"
    }
    timeout {
        puts "Connection timeout"
        exit 1
    }
}

expect eof
EXPECT_EOF

    echo "$expect_script"
}

# Function to clean up local processes
cleanup_local() {
    log "Cleaning up local processes..."
    
    # Kill any SSH tunnels for this setup
    local tunnel_pids=$(pgrep -f "ssh.*-L.*$JUPYTER_PORT:localhost:$JUPYTER_PORT" 2>/dev/null || true)
    if [[ -n "$tunnel_pids" ]]; then
        log "Killing SSH tunnels: $tunnel_pids"
        echo "$tunnel_pids" | xargs kill 2>/dev/null || true
        success "Local SSH tunnels terminated"
    else
        log "No local SSH tunnels found"
    fi
    
    # Clean up any remaining port forwards
    pkill -f "ssh.*-J.*$GATEWAY_HOST" 2>/dev/null || true
    
    # Clean up temp files
    rm -f /tmp/gpu_node_ip /tmp/jupyter_ready /tmp/setup_complete /tmp/new_gpu_ip 2>/dev/null || true
    
    success "Local cleanup completed"
}

# Function to clean up remote sessions
cleanup_remote() {
    log "Cleaning up remote GPU sessions..."
    
    # Ensure expect is available
    if ! ensure_expect; then
        error "Cannot proceed without expect"
        exit 1
    fi
    
    # Get credentials
    if [[ -z "$PORTAL_ID" ]]; then
        read -p "Enter your HKU Portal ID: " PORTAL_ID
    fi
    
    echo -n "Enter password for $PORTAL_ID@$GATEWAY_HOST: "
    read -s password
    echo
    
    # Create and run cleanup script
    local expect_script=$(create_cleanup_expect_script)
    chmod +x "$expect_script"
    
    log "Executing remote cleanup..."
    
    # Run cleanup and capture output
    local cleanup_success=false
    "$expect_script" "$password" "$PORTAL_ID" "$GATEWAY_HOST" 2>&1 | while IFS= read -r line; do
        echo "$line"
        if [[ "$line" =~ CLEANUP_SUCCESS|CLEANUP_COMPLETE ]]; then
            echo "SUCCESS" > /tmp/cleanup_status
        fi
    done
    
    # Check results
    if [[ -f /tmp/cleanup_status ]]; then
        success "Remote cleanup completed successfully"
        cleanup_success=true
        rm -f /tmp/cleanup_status
    else
        warn "Remote cleanup may have encountered issues"
    fi
    
    # Clean up the expect script
    rm -f "$expect_script"
    
    return 0
}

# Function to show current status
show_status() {
    log "Checking current GPU session status..."
    
    if [[ -z "$PORTAL_ID" ]]; then
        read -p "Enter your HKU Portal ID: " PORTAL_ID
    fi
    
    echo -n "Enter password for $PORTAL_ID@$GATEWAY_HOST: "
    read -s password
    echo
    
    log "Connecting to check status..."
    
    # Simple status check
    if command -v sshpass >/dev/null 2>&1; then
        sshpass -p "$password" ssh -o StrictHostKeyChecking=no "$PORTAL_ID@$GATEWAY_HOST" "echo 'Current GPU sessions:'; squeue -u $PORTAL_ID; echo; echo 'Current processes:'; ps aux | grep -E '(jupyter|tmux)' | grep -v grep || echo 'No jupyter/tmux processes found'"
    else
        ssh "$PORTAL_ID@$GATEWAY_HOST" "echo 'Current GPU sessions:'; squeue -u $PORTAL_ID; echo; echo 'Current processes:'; ps aux | grep -E '(jupyter|tmux)' | grep -v grep || echo 'No jupyter/tmux processes found'"
    fi
}

# Function to force cleanup everything
force_cleanup() {
    log "=== FORCE CLEANUP MODE ==="
    warn "This will terminate ALL your GPU sessions and processes"
    read -p "Are you sure? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cleanup_local
        cleanup_remote
        
        log "Waiting 5 seconds for cleanup to complete..."
        sleep 5
        
        log "Verifying cleanup..."
        show_status
        
        success "=== FORCE CLEANUP COMPLETED ==="
    else
        log "Cleanup cancelled"
    fi
}

# Function to clean up specific job ID
cleanup_job() {
    local job_id="$1"
    
    if [[ -z "$job_id" ]]; then
        read -p "Enter Job ID to cancel: " job_id
    fi
    
    if [[ -z "$PORTAL_ID" ]]; then
        read -p "Enter your HKU Portal ID: " PORTAL_ID
    fi
    
    echo -n "Enter password for $PORTAL_ID@$GATEWAY_HOST: "
    read -s password
    echo
    
    log "Cancelling job $job_id..."
    
    if command -v sshpass >/dev/null 2>&1; then
        if sshpass -p "$password" ssh "$PORTAL_ID@$GATEWAY_HOST" "scancel $job_id && echo 'Job $job_id cancelled'"; then
            success "Job $job_id has been cancelled"
        else
            error "Failed to cancel job $job_id"
        fi
    else
        ssh "$PORTAL_ID@$GATEWAY_HOST" "scancel $job_id && echo 'Job $job_id cancelled'"
    fi
}

# Main script
log "=== HKU CS GPU Farm Cleanup Script ==="

# Parse command line arguments
case "${1:-interactive}" in
    "status"|"-s"|"--status")
        show_status
        ;;
    "force"|"-f"|"--force")
        force_cleanup
        ;;
    "job"|"-j"|"--job")
        cleanup_job "$2"
        ;;
    "local"|"-l"|"--local")
        cleanup_local
        ;;
    "remote"|"-r"|"--remote")
        cleanup_remote
        ;;
    "help"|"-h"|"--help")
        echo "Usage: $0 [OPTION]"
        echo ""
        echo "Options:"
        echo "  status, -s, --status    Show current GPU sessions and processes"
        echo "  force, -f, --force      Force cleanup of all sessions and processes"
        echo "  job, -j, --job [ID]     Cancel specific job ID"
        echo "  local, -l, --local      Cleanup only local processes (SSH tunnels)"
        echo "  remote, -r, --remote    Cleanup only remote sessions"
        echo "  help, -h, --help        Show this help message"
        echo ""
        echo "Interactive mode (default): Provides menu options"
        ;;
    *)
        # Interactive mode
        echo "What would you like to do?"
        echo "1) Check current status"
        echo "2) Force cleanup everything"
        echo "3) Cancel specific job ID"
        echo "4) Cleanup local processes only"
        echo "5) Cleanup remote sessions only"
        echo "6) Exit"
        echo
        read -p "Enter choice (1-6): " choice
        
        case $choice in
            1) show_status ;;
            2) force_cleanup ;;
            3) cleanup_job ;;
            4) cleanup_local ;;
            5) cleanup_remote ;;
            6) log "Exiting..."; exit 0 ;;
            *) error "Invalid choice"; exit 1 ;;
        esac
        ;;
esac

success "Cleanup script completed"