#!/usr/bin/env bash
set -euo pipefail

TARGET_HOST="nuc01"
echo "=== Checking SSH connection to ${TARGET_HOST} ==="
if ! ssh -q -o BatchMode=yes "${TARGET_HOST}" exit; then
    echo "Error: Cannot connect to ${TARGET_HOST} without a password."
    echo "Please ensure SSH key authentication is configured."
    exit 1
fi
echo "SSH connection OK."

echo ""
echo "=== 1. Syncing ~/.config from WSL to ${TARGET_HOST} ==="
tar --exclude='.venv' \
    --exclude='google-chrome*' \
    --exclude='microsoft-edge*' \
    --exclude='chromium*' \
    --exclude='Code*' \
    --exclude='dconf' \
    --exclude='pulse' \
    --exclude='*cache*' \
    -czf - -C "$HOME" .config | ssh "${TARGET_HOST}" "tar -xzf - -C ~"
echo "~/.config synced successfully."

echo ""
echo "=== 2. Syncing .gitconfig ==="
scp -q "$HOME/.gitconfig" "${TARGET_HOST}:~/.gitconfig"

echo ""
echo "=== 3. Staging Remote Setup Script on ${TARGET_HOST} ==="
ssh "${TARGET_HOST}" 'cat << '\''REMOTE_PAYLOAD'\'' > /tmp/setup-remote.sh
#!/usr/bin/env bash
set -euo pipefail

# Append mise & custom bash loaders to ~/.bashrc if not already present
if ! grep -q "mise activate bash" ~/.bashrc; then
    cat << '\''BASHRC_SNIPPET'\'' >> ~/.bashrc

# --- Load ~/.config/bash scripts ---
BASH_CONFIG_DIR="$HOME/.config/bash"
if [ -d "$BASH_CONFIG_DIR" ]; then
  for file in "$BASH_CONFIG_DIR"/*.sh "$BASH_CONFIG_DIR"/*.bash; do
    if [ -r "$file" ]; then
      source "$file"
    fi
  done
  unset file
fi
unset BASH_CONFIG_DIR

# --- Activate Mise & Direnv ---
if [ -x "$HOME/.local/bin/mise" ]; then
    eval "$($HOME/.local/bin/mise activate bash)"
    eval "$($HOME/.local/bin/mise exec direnv -- direnv hook bash 2>/dev/null || true)"
fi
BASHRC_SNIPPET
    echo "Added Mise & custom bash loading to ~/.bashrc"
fi

echo ""
echo "=== Installing Core Packages ==="
echo "Enter your sudo password when prompted:"
sudo apt update
sudo apt install -y git curl wget build-essential rsync unzip jq ca-certificates gnupg fzf

# Configure passwordless sudo for user
if [ ! -f "/etc/sudoers.d/$USER" ]; then
    echo "$USER ALL=(ALL) NOPASSWD:ALL" | sudo tee "/etc/sudoers.d/$USER" >/dev/null
    sudo chmod 0440 "/etc/sudoers.d/$USER"
    echo "Configured passwordless sudo for $USER"
fi

echo ""
echo "=== Installing Mise ==="
if [ ! -x "$HOME/.local/bin/mise" ]; then
    curl -fsSL https://mise.jdx.dev/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
eval "$(mise activate bash)"

echo ""
echo "=== Installing Tools from ~/.config/mise/config.toml ==="
mise install -y

echo ""
echo "=== Pre-fetching Neovim Plugins ==="
if mise which nvim >/dev/null 2>&1; then
    echo "Running headless Neovim Lazy sync..."
    mise exec -- nvim --headless "+Lazy! sync" +qa || true
fi

echo ""
echo "=================================================="
echo "  SETUP COMPLETE on $(hostname)!"
echo "=================================================="
REMOTE_PAYLOAD
chmod +x /tmp/setup-remote.sh
'

echo "=== 4. Running Provisioning Script (Interactive TTY) ==="
# Execute the remote script with an interactive TTY so sudo can prompt for password
ssh -t "${TARGET_HOST}" "/tmp/setup-remote.sh"

echo ""
echo "All done! Your NUC01 is fully provisioned."
