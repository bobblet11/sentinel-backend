#!/bin/bash

# Creates a session keeper script on the gateway
PORTAL_ID="${1:-farhan}"
GATEWAY="${2:-gpu2gate1.cs.hku.hk}"

echo "HKU GPU Farm - Session Keeper Setup"
echo "===================================="
echo "Portal ID: $PORTAL_ID"
echo "Gateway: $GATEWAY"
echo ""

echo "1. Creating Jupyter config and session script..."

# Create both config and session script on gateway
ssh $PORTAL_ID@$GATEWAY << 'EOF'

# Create Jupyter config
mkdir -p ~/.jupyter
cat > ~/.jupyter/jupyter_server_config.py << 'CONFIG'
c = get_config()
c.ServerApp.token = 'my-fixed-token-12345'
c.ServerApp.password = ''
c.ServerApp.open_browser = False
CONFIG

# Create simpler session keeper script
cat > ~/gpu_start.sh << 'SCRIPT'
#!/bin/bash

echo "Starting GPU session with Jupyter..."
echo ""

# Start gpu-interactive with commands
echo "Allocating GPU (this may take a moment)..."
gpu-interactive bash -c '
echo ""
echo "================================"
echo "🚀 GPU ALLOCATED SUCCESSFULLY!"
echo "================================"

GPU_IP=\$(hostname -I | awk "{print \$1}")
GPU_HOST=\$(hostname)

echo "GPU IP: \$GPU_IP"
echo "GPU Host: \$GPU_HOST"
echo ""

# Save IP
echo "\$GPU_IP" > ~/.gpu_ip

# Start Jupyter
echo "Starting Jupyter Lab..."
nohup jupyter-lab --no-browser --ip=0.0.0.0 > ~/.jupyter.log 2>&1 &
sleep 3

echo "✅ Jupyter started in background"
echo ""
echo "================================"
echo "CONNECTION INFO:"
echo "================================"
echo ""
echo "In a NEW terminal, run:"
echo "  ssh -L 8888:localhost:8888 farhan@\$GPU_IP"
echo ""
echo "Then open in browser:"
echo "  http://localhost:8888/lab?token=my-fixed-token-12345"
echo ""
echo "================================"
echo "IMPORTANT: Keep this session open!"
echo "Type \"exit\" when done to release GPU"
echo "================================"
echo ""

# Keep session alive
bash
'
SCRIPT

chmod +x ~/gpu_start.sh

echo "✅ Scripts created on gateway"
echo ""
echo "Session keeper script: ~/gpu_start.sh"

EOF

if [ $? -eq 0 ]; then
    echo ""
    echo "===================================="
    echo "✅ Setup complete!"
    echo "===================================="
    echo ""
    echo "Now run these commands:"
    echo ""
    echo "1. SSH to gateway:"
    echo "   ssh $PORTAL_ID@$GATEWAY"
    echo ""
    echo "2. Start GPU session:"
    echo "   ~/gpu_start.sh"
    echo ""
    echo "   This will:"
    echo "   ✅ Allocate GPU and keep session alive"
    echo "   ✅ Start Jupyter with fixed token"
    echo "   ✅ Show connection command"
    echo ""
    echo "3. Use the connection command it shows you"
    echo ""
    echo "===================================="
    echo "The session will stay alive until you type 'exit'"
    echo "===================================="
else
    echo "❌ Failed to create scripts on gateway"
fi