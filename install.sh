#!/usr/bin/env bash
# Multi-Agent Council — install wizard
# Supports: Linux, WSL, Termux (Android)
set -euo pipefail

BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
prompt()  { echo -e "${YELLOW}[INPUT]${NC} $*"; }

detect_platform() {
    if [ -n "${TERMUX_VERSION:-}" ] || [ -d "/data/data/com.termux" ]; then echo "termux"
    elif grep -qi microsoft /proc/version 2>/dev/null; then echo "wsl"
    else echo "linux"; fi
}

install_deps_system() {
    local plat="$1"
    case "$plat" in
        termux) pkg update -y; pkg install -y python git ;;
        wsl|linux)
            if command -v apt-get &>/dev/null; then
                sudo apt-get update -qq
                sudo apt-get install -y python3 python3-venv python3-pip git
            elif command -v dnf &>/dev/null; then
                sudo dnf install -y python3 python3-virtualenv git
            elif command -v pacman &>/dev/null; then
                sudo pacman -Sy --noconfirm python git
            elif command -v apk &>/dev/null; then
                sudo apk add --no-cache python3 py3-pip git
            fi ;;
    esac
}

PLATFORM=$(detect_platform)
INSTALL_DIR="${HOME}/.local/share/multi-agent-council"
VENV_DIR="${INSTALL_DIR}/.venv"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     Multi-Agent Council  v1.0.0          ║"
echo "║  7-phase AI think-tank deliberation      ║"
echo "╚══════════════════════════════════════════╝"
echo ""
info "Platform: $PLATFORM"
info "Phases: BRIEF → RECON → INTEL → WARGAME → REFINE → COUNCIL → DEBRIEF"

install_deps_system "$PLATFORM"
mkdir -p "$INSTALL_DIR"
if [ "$PLATFORM" = "termux" ]; then python -m venv "$VENV_DIR"
else python3 -m venv "$VENV_DIR"; fi
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install . -q

ENV_FILE="${INSTALL_DIR}/.env"
touch "$ENV_FILE"; chmod 600 "$ENV_FILE"

echo ""
echo "────────────────────────────────────────────"
echo " CLI Backend Configuration"
echo " The council needs at least one AI CLI."
echo " Provide the commands used to call each CLI."
echo "────────────────────────────────────────────"

prompt "Claude CLI command (e.g. 'claude' or full path, blank to skip):"
read -r claude_cmd
if [ -n "$claude_cmd" ]; then echo "COUNCIL_CLAUDE_CMD=${claude_cmd}" >> "$ENV_FILE"; fi

prompt "Gemini CLI command (e.g. 'gemini', blank to skip):"
read -r gemini_cmd
if [ -n "$gemini_cmd" ]; then echo "COUNCIL_GEMINI_CMD=${gemini_cmd}" >> "$ENV_FILE"; fi

prompt "Custom AI CLI command (any CLI that accepts text input, blank to skip):"
read -r custom_cmd
if [ -n "$custom_cmd" ]; then echo "COUNCIL_CUSTOM_CMD=${custom_cmd}" >> "$ENV_FILE"; fi

prompt "Council home directory (default: $INSTALL_DIR):"
read -r home_path
if [ -n "$home_path" ]; then echo "COUNCIL_HOME=${home_path}" >> "$ENV_FILE"; fi

echo "" >> "$ENV_FILE"
echo "# Comma-separated list of enabled backends (auto-detected from above)" >> "$ENV_FILE"
backends=""
[ -n "$claude_cmd" ] && backends="${backends}claude,"
[ -n "$gemini_cmd" ] && backends="${backends}gemini,"
[ -n "$custom_cmd" ] && backends="${backends}custom,"
backends="${backends%,}"
[ -n "$backends" ] && echo "COUNCIL_BACKENDS=${backends}" >> "$ENV_FILE"

success "Config saved to $ENV_FILE"

WRAPPER="${HOME}/.local/bin/council"
mkdir -p "$(dirname "$WRAPPER")"
cat > "$WRAPPER" << WRAPEOF
#!/usr/bin/env bash
set -a; [ -f "${ENV_FILE}" ] && . "${ENV_FILE}"; set +a
exec "${VENV_DIR}/bin/council" "\$@"
WRAPEOF
chmod +x "$WRAPPER"

echo ""
success "Installation complete!"
echo ""
echo "  Run a council:   council --topic 'Should we use Go or Rust for the daemon?'"
echo "  List phases:     council --phases"
echo "  Dry run:         council --dry-run --topic '...'"
echo "  Docs:            https://github.com/M00C1FER/multi-agent-council"
