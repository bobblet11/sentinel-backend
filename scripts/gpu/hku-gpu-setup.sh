#!/bin/bash

# =============================================================================
# HKU CS GPU Farm Simple Setup Script
# Author: GitHub Copilot
# Date: 2025-10-06
# =============================================================================

# Configuration - Modify these as needed
CONDA_ENV_NAME="finalyear"
JUPYTER_TOKEN="myfixedtoken123"
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

# Function to find available local port
find_available_port() {
    local port=$1
    while netstat -an 2>/dev/null | grep -q ":$port " || ss -tuln 2>/dev/null | grep -q ":$port "; do
        ((port++))
        if [[ $port -gt 9000 ]]; then
            error "Could not find available port between $1 and 9000"
            exit 1
        fi
    done
    echo $port
}

# Main script
log "=== HKU CS GPU Farm Simple Setup Script ==="
log "This script provides step-by-step instructions for manual setup"
log "Configuration:"
log "  Gateway: $GATEWAY_HOST"
log "  Conda Environment: $CONDA_ENV_NAME"
log "  Jupyter Token: $JUPYTER_TOKEN"
log "  Jupyter Port: $JUPYTER_PORT"

# Get credentials
if [[ -z "$PORTAL_ID" ]]; then
    read -p "Enter your HKU Portal ID: " PORTAL_ID
fi

LOCAL_PORT=$(find_available_port $JUPYTER_PORT)
if [[ "$LOCAL_PORT" != "$JUPYTER_PORT" ]]; then
    warn "Port $JUPYTER_PORT is busy locally, will use port $LOCAL_PORT for tunnel"
fi

log "Portal ID: $PORTAL_ID"

echo
log "=== STEP 1: Connect to Gateway and Allocate GPU ==="
echo "Run these commands in a separate terminal:"
echo
echo "1. Connect to the gateway:"
echo "   ssh $PORTAL_ID@$GATEWAY_HOST"
echo
echo "2. Request a GPU allocation:"
echo "   gpu-interactive"
echo
echo "3. Wait for allocation and note the GPU node (e.g., gpu-4080-117)"
echo "4. Get the node IP address:"
echo "   hostname -I | awk '{print \$1}'"
echo

read -p "Press Enter when you have completed Step 1 and have the GPU node IP..."

# Get GPU node IP from user
read -p "Enter the GPU node IP address (e.g., 10.21.5.147): " GPU_NODE_IP

if [[ ! "$GPU_NODE_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    error "Invalid IP address format"
    exit 1
fi

success "GPU Node IP: $GPU_NODE_IP"

echo
log "=== STEP 2: Setup Conda Environment on GPU Node ==="
echo "In your GPU node terminal, run these commands:"
echo
echo "# Setup conda"
echo "export PATH=\"/userhome/cs/$PORTAL_ID/anaconda3/bin:\$PATH\""
echo "eval \"\$(/userhome/cs/$PORTAL_ID/anaconda3/bin/conda shell.bash hook)\""
echo
echo "# Activate or create environment"
echo "conda activate $CONDA_ENV_NAME || conda create -n $CONDA_ENV_NAME python=3.11 -y"
echo "conda activate $CONDA_ENV_NAME"
echo
echo "# Install packages if needed"
echo "conda list jupyterlab >/dev/null 2>&1 || conda install -y jupyterlab ipykernel"
echo "python -c 'import torch' >/dev/null 2>&1 || pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124"
echo
echo "# Register kernel"
echo "python -m ipykernel install --user --name=$CONDA_ENV_NAME --display-name 'Python ($CONDA_ENV_NAME)'"
echo
echo "# Test GPU"
echo "python -c \"import torch; print(f'GPU Available: {torch.cuda.is_available()}'); print(f'GPU Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"None\"}')\""
echo

read -p "Press Enter when you have completed Step 2..."

echo
log "=== STEP 3: Start Jupyter Lab ==="
echo "In your GPU node terminal, run:"
echo
echo "# Kill any existing sessions"
echo "pkill -f 'jupyter.*port=$JUPYTER_PORT' 2>/dev/null || true"
echo
echo "# Start Jupyter Lab"
echo "cd ~"
echo "jupyter-lab --no-browser --port=$JUPYTER_PORT --ip=0.0.0.0 --allow-root --NotebookApp.token='$JUPYTER_TOKEN'"
echo
warn "IMPORTANT: Keep this terminal open! Jupyter will run in the foreground."
warn "You should see output like 'Jupyter Server is running at http://0.0.0.0:$JUPYTER_PORT/'"

read -p "Press Enter when Jupyter Lab is running..."

echo
log "=== STEP 4: Create SSH Tunnel ==="
log "Creating SSH tunnel from your local machine to the GPU node..."

# Kill any existing tunnels
pkill -f "ssh.*-L.*$LOCAL_PORT:localhost:$JUPYTER_PORT" 2>/dev/null || true

log "Setting up tunnel: localhost:$LOCAL_PORT -> $GPU_NODE_IP:$JUPYTER_PORT"

# Create SSH tunnel
log "You may need to enter your password for the SSH tunnel..."
ssh -L "$LOCAL_PORT:localhost:$JUPYTER_PORT" -J "$PORTAL_ID@$GATEWAY_HOST" "$PORTAL_ID@$GPU_NODE_IP" -N &
SSH_TUNNEL_PID=$!

log "SSH tunnel started (PID: $SSH_TUNNEL_PID)"
sleep 3

# Test the tunnel
log "Testing tunnel connection..."
for i in {1..10}; do
    if curl -s -m 5 "http://localhost:$LOCAL_PORT" >/dev/null 2>&1; then
        success "Tunnel is working!"
        break
    elif [[ $i -eq 10 ]]; then
        warn "Tunnel test timed out, but it might still work"
    else
        log "Test attempt $i/10..."
        sleep 2
    fi
done

echo
success "=== Setup Complete! ==="
echo
success "Jupyter Lab should be accessible at:"
echo "    🌐 http://localhost:$LOCAL_PORT/?token=$JUPYTER_TOKEN"
echo
log "For VS Code integration:"
log "1. Install Python and Jupyter extensions in VS Code"
log "2. Create or open a .ipynb file"
log "3. Click 'Select Kernel' (top right)"
log "4. Choose 'Existing Jupyter Server'"
log "5. Enter: http://localhost:$LOCAL_PORT/?token=$JUPYTER_TOKEN"
log "6. Select the 'Python ($CONDA_ENV_NAME)' kernel"
echo
log "=== Connection Details ==="
log "Gateway: $GATEWAY_HOST"
log "GPU Node: $GPU_NODE_IP"
log "Local URL: http://localhost:$LOCAL_PORT/?token=$JUPYTER_TOKEN"
log "SSH Tunnel PID: $SSH_TUNNEL_PID"
echo

warn "Keep this terminal open to maintain the SSH tunnel"
warn "To stop: Press Ctrl+C or kill process $SSH_TUNNEL_PID"

echo
log "=== Manual Cleanup Instructions ==="
log "When you're done:"
log "1. Stop Jupyter Lab in the GPU node terminal (Ctrl+C)"
log "2. Exit the GPU node: exit"
log "3. Stop this tunnel: Ctrl+C or kill $SSH_TUNNEL_PID"
log "4. Optional: Cancel the GPU job: scancel <job_id>"

# Wait for user to stop
log "Monitoring tunnel... Press Ctrl+C to stop"
trap "log 'Stopping tunnel...'; kill $SSH_TUNNEL_PID 2>/dev/null; log 'Tunnel stopped. Goodbye!'; exit 0" SIGINT

while true; do
    sleep 30
    if ! kill -0 $SSH_TUNNEL_PID 2>/dev/null; then
        error "SSH tunnel died unexpectedly"
        break
    fi
done