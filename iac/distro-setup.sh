#!/usr/bin/env bash

# WSL Distro Setup Dashboard - Generic Installer Engine
LIST_FILE="$HOME/tools.list"
STATE_FILE="$HOME/.mstouffer_setup_state.json"

# --- INTERNAL DEFAULT TOOLS (Used if tools.list is missing) ---
INTERNAL_LIST="sudo-nopasswd|Enable passwordless sudo|echo \"\$USER ALL=(ALL) NOPASSWD:ALL\" | sudo tee /etc/sudoers.d/\$USER
bridge-dirs|Create migration bridge folders|mkdir -p /mnt/wsl/migrate_source ~/repos
git|Install Git|sudo apt update && sudo apt install -y git
rsync|Install Rsync|sudo apt install -y rsync
curl|Install Curl|sudo apt install -y curl
wget|Install Wget|sudo apt install -y wget
ca-certs|Install CA Certificates|sudo apt install -y ca-certificates
gnupg|Install GnuPG|sudo apt install -y gnupg
lsb-release|Install LSB Release|sudo apt install -y lsb-release
unzip|Install Unzip|sudo apt install -y unzip
htop|Install Htop|sudo apt install -y htop
tree|Install Tree|sudo apt install -y tree
jq|Install JQ|sudo apt install -y jq
build-essent|Install Build Essential (GCC/Make)|sudo apt install -y build-essential
mise|Install Mise (Runtime Manager)|curl https://mise.jdx.dev/install.sh | sh
uv|Install UV (Python Manager)|curl -LsSf https://astral.sh/uv/install.sh | sh
node@24|Install Node.js v24 (via Mise)|mise use --global node@24
neovim|Install Neovim (via Mise)|mise use --global neovim@latest
starship|Install Starship Prompt (via Mise)|mise use --global starship@latest
zoxide|Install Zoxide (via Mise)|mise use --global zoxide@latest
fzf|Install FZF (via Mise)|mise use --global fzf@latest
fd|Install FD Finder (via Mise)|mise use --global fd@latest
bat|Install Bat (via Mise)|mise use --global bat@latest
lsd|Install LSD (via Mise)|mise use --global lsd@latest
gh|Install GitHub CLI (via Mise)|mise use --global gh@latest
aws-cli|Install AWS CLI v2|curl \"https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip\" -o \"/tmp/aws.zip\" && unzip -o /tmp/aws.zip -d /tmp/ && sudo /tmp/aws/install --update
1password|Install 1Password CLI|curl -sS https://downloads.1password.com/linux/keys/1password.asc | sudo gpg --dearmor --yes --output /usr/share/keyrings/1password.gpg && echo \"deb [arch=amd64 signed-by=/usr/share/keyrings/1password.gpg] https://downloads.1password.com/linux/debian/amd64 stable main\" | sudo tee /etc/apt/sources.list.d/1password.list && sudo apt update && sudo apt install -y 1password-cli"

# Colors
BLUE='\033[0;34m'; GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'; BOLD='\033[1m'

# --- LOAD TOOLS ---
TOOL_NAMES=()
declare -A TOOL_DESC
declare -A TOOL_CMD
DATA_SOURCE=""

load_tool_line() {
    local name=$1; local desc=$2; local cmd=$3
    [[ -z "$name" || "$name" == "#"* ]] && return
    TOOL_NAMES+=("$name")
    TOOL_DESC["$name"]="$desc"
    TOOL_CMD["$name"]="$cmd"
}

if [[ -f "$LIST_FILE" ]]; then
    DATA_SOURCE="External File ($LIST_FILE)"
    while IFS="|" read -r name desc cmd; do
        load_tool_line "$name" "$desc" "$cmd"
    done < "$LIST_FILE"
else
    DATA_SOURCE="Internal Default List"
    while IFS="|" read -r name desc cmd; do
        load_tool_line "$name" "$desc" "$cmd"
    done <<< "$INTERNAL_LIST"
fi

# --- STATE & UI ENGINE ---
declare -A SELECTED
[[ -f "$STATE_FILE" ]] && while read -r line; do SELECTED["$line"]=1; done < "$STATE_FILE"
save_state() { > "$STATE_FILE"; for n in "${!SELECTED[@]}"; do [[ ${SELECTED[$n]} -eq 1 ]] && echo "$n" >> "$STATE_FILE"; done; }

current_idx=0
move_cursor() { printf "\033[%d;%dH" "$1" "$2"; }
hide_cursor() { printf "\033[?25l"; }
show_cursor() { printf "\033[?25h"; }

draw_ui() {
    printf "\033[H\033[J"
    echo -e "${BLUE}${BOLD}=== WSL Distro Setup Dashboard ===${NC}"
    echo -e "Data Source: ${YELLOW}$DATA_SOURCE${NC}"
    echo "-----------------------------------------------------------------------"
    for i in "${!TOOL_NAMES[@]}"; do
        local name="${TOOL_NAMES[$i]}"
        local prefix="  "; [[ $i -eq $current_idx ]] && prefix="${YELLOW}> ${NC}"
        local mark="[ ]"; local color=$NC; [[ ${SELECTED[$name]} -eq 1 ]] && { mark="[x]"; color=$GREEN; }
        printf "%b%b %-15s %b  ${NC}%s\n" "$prefix" "$color" "$name" "$mark" "${TOOL_DESC[$name]}"
    done
}

apply_changes() {
    echo -e "\n\n${YELLOW}${BOLD}--- Installing Selected Items ---${NC}"
    export PATH="$HOME/.local/bin:$PATH"
    if command -v mise &>/dev/null; then eval "$(mise activate bash)"; fi
    for name in "${TOOL_NAMES[@]}"; do
        if [[ ${SELECTED[$name]} -eq 1 ]]; then
            echo -e "${BLUE}Running: $name...${NC}"
            eval "${TOOL_CMD[$name]}"
        fi
    done
    echo -e "\n${GREEN}${BOLD}Done! Press any key.${NC}"
    read -n 1 -s
}

hide_cursor; trap show_cursor EXIT
while true; do
    draw_ui
    read -rsn1 key
    [[ "$key" == "" ]] && key=" " 
    case "$key" in
        k) ((current_idx--)); [[ $current_idx -lt 0 ]] && current_idx=$((${#TOOL_NAMES[@]} - 1)) ;;
        j) ((current_idx++)); [[ $current_idx -ge ${#TOOL_NAMES[@]} ]] && current_idx=0 ;;
        " ") name="${TOOL_NAMES[$current_idx]}"; [[ ${SELECTED[$name]} -eq 1 ]] && SELECTED[$name]=0 || SELECTED[$name]=1; save_state ;;
        i) apply_changes ;;
        q) break ;;
    esac
done
show_cursor