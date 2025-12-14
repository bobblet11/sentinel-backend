#!/usr/bin/env python3
"""
GPU Jupyter launcher that KEEPS the session alive
Uses pexpect to maintain interactive GPU session
"""
import re
import sys
import time

import pexpect


def launch_gpu_jupyter(portal_id="farhan", gateway="gpu2gate1.cs.hku.hk"):
    print("HKU GPU Farm - Session Keeper")
    print("=" * 40)
    print(f"Portal ID: {portal_id}")
    print(f"Gateway: {gateway}")
    print()

    # Step 1: Start single interactive session to gateway
    print("1. Connecting to gateway...")
    print("   (You'll need to enter your password)")

    try:
        # Start SSH to gateway
        child = pexpect.spawn(f"ssh -t {portal_id}@{gateway}")
        # Don't echo everything to stdout - causes duplicate output
        # child.logfile_read = sys.stdout.buffer

        # Wait for password prompt or shell
        index = child.expect(
            ["password:", "\\$ ", "~\\$ ", ":\\~\\$", pexpect.TIMEOUT], timeout=30
        )

        if index == 0:  # Password prompt
            import getpass

            password = getpass.getpass("Enter password: ")
            child.sendline(password)
            # shell_index = child.expect(["\\$ ", "~\\$ ", ":\\~\\$"], timeout=30)
        elif index in [1, 2, 3]:  # Already at shell
            print("Already at shell prompt")

        print("✅ Connected to gateway")
        print()

        # Give a moment for the shell to stabilize
        time.sleep(2)

        # Step 2: Setup Jupyter config
        print("2. Setting up Jupyter config...")
        child.sendline("mkdir -p ~/.jupyter")
        index = child.expect(["\\$ ", "~\\$ ", ":\\~\\$"], timeout=10)
        print("   Directory created")

        config_cmd = """cat > ~/.jupyter/jupyter_server_config.py << 'EOF'
c = get_config()
c.ServerApp.token = 'my-fixed-token-12345'
c.ServerApp.password = ''
c.ServerApp.open_browser = False
EOF"""

        child.sendline(config_cmd)
        index = child.expect(["\\$ ", "~\\$ ", ":\\~\\$"], timeout=10)
        print("✅ Config created")
        print()

        # Step 3: Start gpu-interactive
        print("3. Starting GPU session...")
        print("   This will allocate a GPU and keep the session alive")
        print()
        print("   Running: gpu-interactive")

        child.sendline("gpu-interactive")

        # Wait for GPU allocation and shell prompt
        print("   Waiting for GPU allocation...")
        index = child.expect(
            ["\\$ ", "~\\$ ", "srun:", "error:", "denied", pexpect.TIMEOUT], timeout=60
        )

        if index in [0, 1]:  # Got shell on GPU node
            print("✅ GPU allocated!")
            print()

            # Step 4: Get GPU IP
            print("4. Getting GPU IP...")
            child.sendline("hostname -I | awk '{print $1}'")
            child.expect(["\\$ ", "~\\$ "], timeout=10)

            # Extract GPU IP from the output
            output = child.before.decode()
            # Look for IP in the format xxx.xxx.xxx.xxx
            ip_match = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", output)

            if ip_match:
                gpu_ip = ip_match.group(1)
                print(f"✅ GPU IP: {gpu_ip}")

                # Save IP to file
                with open("current_gpu_ip.txt", "w") as f:
                    f.write(gpu_ip)

                # Step 5: Start Jupyter
                print()
                print("5. Starting Jupyter...")
                child.sendline("nohup jupyter-lab --no-browser > ~/jupyter.log 2>&1 &")
                child.expect(["\\$ ", "~\\$ "], timeout=10)

                print("✅ Jupyter started in background")
                print()

                print("=" * 50)
                print("🚀 SUCCESS! GPU session is ACTIVE")
                print("=" * 50)
                print()
                print(f"GPU IP: {gpu_ip}")
                print()
                print("In a NEW terminal, run this command:")
                print()
                print(f"ssh -L 8888:localhost:8888 {portal_id}@{gpu_ip}")
                print()
                print("Then open this URL in browser or VS Code:")
                print()
                print("http://localhost:8888/lab?token=my-fixed-token-12345")
                print()
                print("=" * 50)
                print("⚠️  IMPORTANT: Keep THIS terminal open!")
                print("   Closing it will end your GPU session")
                print("   Type 'exit' when done to release GPU")
                print("=" * 50)
                print()

                # Keep session alive - give user control
                print("You now have control of the GPU session:")
                child.interact()

            else:
                print("❌ Could not get GPU IP")
                return False
        elif index == 2:  # srun message
            print("⏳ GPU allocation in progress...")
            # Wait longer for actual allocation
            child.expect(["\\$ ", "~\\$ "], timeout=120)
            print("✅ GPU allocated!")
        elif index in [3, 4]:  # error or denied
            print("❌ GPU allocation failed - check quota or try again")
            return False
        else:
            print("❌ Failed to allocate GPU - timeout")
            return False

    except pexpect.exceptions.TIMEOUT:
        print("❌ Timeout - connection failed")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    portal_id = sys.argv[1] if len(sys.argv) > 1 else "farhan"
    gateway = sys.argv[2] if len(sys.argv) > 2 else "gpu2gate1.cs.hku.hk"

    # Check if pexpect is available
    try:
        # import pexpect
        pass
    except ImportError:
        print("❌ pexpect not installed")
        print("Install it with: pip install pexpect")
        sys.exit(1)

    launch_gpu_jupyter(portal_id, gateway)
