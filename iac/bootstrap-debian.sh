#!/usr/bin/env bash

# bootstrap-debian.sh - Prepare a new Debian/Ubuntu system for work.

echo "=== 1. System Update & Core Tools ==="
sudo apt update
sudo apt install -y git rsync curl build-essential wget ca-certificates gnupg lsb-release

echo "=== 2. Configure Passwordless Sudo (Optional) ==="
# Allows you to run sudo without a password
echo "$USER ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/$USER

echo "=== 3. Install Mise (Tool Manager) ==="
if ! command -v mise &> /dev/null; then
    curl https://mise.jdx.dev/install.sh | sh
    echo 'eval "$($HOME/.local/bin/mise activate bash)"' >> ~/.bashrc
fi

echo "=== 4. Prepare for Migration ==="
mkdir -p ~/.config/bash/bin
mkdir -p ~/repos

echo "=== BOOTSTRAP COMPLETE ==="
echo "Please run: source ~/.bashrc"
echo "Then you can run the migrate-wsl.sh script."