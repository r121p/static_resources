#!/bin/bash
# ============================================================
#  Install script — uv sync + shell alias for the launcher
#  + lerobot venv setup
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ALIAS_NAME="robot"
LEROOT_VENV="${SCRIPT_DIR}/lerobot_venv"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ------------------------------------------------------------------
# Check for uv
# ------------------------------------------------------------------
if ! command -v uv &>/dev/null; then
  echo "ERROR: 'uv' is not installed or not in PATH."
  echo "Install it first: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi

# ------------------------------------------------------------------
# Run uv sync in phosphobot/
# ------------------------------------------------------------------
echo "▶ Running uv sync in ${SCRIPT_DIR}/phosphobot ..."
cd "${SCRIPT_DIR}/phosphobot"
uv sync

# ------------------------------------------------------------------
# Setup lerobot environment
# ------------------------------------------------------------------
setup_lerobot_env() {
    echo ""
    echo "▶ Setting up lerobot environment in ${SCRIPT_DIR} ..."

    # Check for Python 3.12
    if ! command -v python3.12 &> /dev/null; then
        echo -e "${RED}ERROR: Python 3.12 is not installed or not in PATH${NC}"
        echo "Please install Python 3.12"
        echo "  Ubuntu/Debian: sudo apt install python3.12 python3.12-venv python3.12-pip"
        echo "  macOS: brew install python@3.12"
        exit 1
    fi

    # Check Python version (need 3.12)
    PYVER=$(python3.12 --version 2>&1 | cut -d' ' -f2)
    PYMAJOR=$(echo "$PYVER" | cut -d'.' -f1)
    PYMINOR=$(echo "$PYVER" | cut -d'.' -f2)

    if [ "$PYMAJOR" -lt 3 ] || ([ "$PYMAJOR" -eq 3 ] && [ "$PYMINOR" -lt 12 ]); then
        echo -e "${RED}ERROR: Python 3.12 is required. Found Python $PYVER${NC}"
        exit 1
    fi
    echo -e "${GREEN}Found Python $PYVER - OK${NC}"

    # Check for Git (required for lerobot installation)
    if ! command -v git &> /dev/null; then
        echo -e "${RED}ERROR: Git is not installed${NC}"
        echo "Git is required to install lerobot from GitHub"
        echo "  Ubuntu/Debian: sudo apt install git"
        echo "  macOS: brew install git"
        exit 1
    fi
    echo -e "${GREEN}Found Git - OK${NC}"

    # Create venv if needed
    if [ ! -d "${LEROOT_VENV}" ]; then
        echo
        echo "Creating virtual environment at ${LEROOT_VENV} ..."
        python3.12 -m venv "${LEROOT_VENV}"
        if [ $? -ne 0 ]; then
            echo -e "${RED}ERROR: Failed to create virtual environment${NC}"
            exit 1
        fi
        echo "Virtual environment created successfully."
    else
        echo "Virtual environment already exists at ${LEROOT_VENV}."
    fi

    # Activate venv
    echo
    echo "Activating virtual environment..."
    source "${LEROOT_VENV}/bin/activate"
    if [ $? -ne 0 ]; then
        echo -e "${RED}ERROR: Failed to activate virtual environment${NC}"
        exit 1
    fi
    echo "Virtual environment activated."

    # Create symlinks for python/python3 to point to python3.12
    if [ -f "${LEROOT_VENV}/bin/python3.12" ]; then
        ln -sf "${LEROOT_VENV}/bin/python3.12" "${LEROOT_VENV}/bin/python"
        ln -sf "${LEROOT_VENV}/bin/python3.12" "${LEROOT_VENV}/bin/python3"
        echo "Created symlinks: python -> python3.12, python3 -> python3.12"
    fi

    # Install/upgrade dependencies from local requirements file
    echo
    echo "Installing dependencies..."
    echo "This may take a few minutes (lerobot is installed from GitHub)..."
    pip install -r "${SCRIPT_DIR}/lerobot_requirements.txt" -q
    if [ $? -ne 0 ]; then
        echo
        echo -e "${RED}ERROR: Failed to install dependencies${NC}"
        echo
        echo "Common issues:"
        echo "  - Network issues: Check your internet connection"
        echo "  - Permission issues: Check write permissions"
        echo "  - Missing build tools: sudo apt install build-essential (Ubuntu/Debian)"
        echo
        exit 1
    fi
    echo -e "${GREEN}Dependencies installed successfully.${NC}"
}

setup_lerobot_env

# Return to script directory so the alias points to the right place
cd "${SCRIPT_DIR}"

# ------------------------------------------------------------------
# Detect shell config file
# ------------------------------------------------------------------
if [ -n "${ZSH_VERSION:-}" ] || [ "$(basename "${SHELL:-bash}")" = "zsh" ]; then
  SHELL_RC="${HOME}/.zshrc"
else
  SHELL_RC="${HOME}/.bashrc"
fi

# ------------------------------------------------------------------
# Add alias
# ------------------------------------------------------------------
ALIAS_CMD="alias ${ALIAS_NAME}='cd \"${SCRIPT_DIR}\" && ./run.sh'"

if [ -f "${SHELL_RC}" ] && grep -qF "alias ${ALIAS_NAME}='cd \"${SCRIPT_DIR}\"" "${SHELL_RC}" 2>/dev/null; then
  echo "Alias '${ALIAS_NAME}' already points to this directory in ${SHELL_RC}"
else
  echo "" >> "${SHELL_RC}"
  echo "# IN097-phase2 robot launcher alias" >> "${SHELL_RC}"
  echo "${ALIAS_CMD}" >> "${SHELL_RC}"
  echo "Added alias '${ALIAS_NAME}' to ${SHELL_RC}"
fi

# ------------------------------------------------------------------
# Done
# ------------------------------------------------------------------
echo ""
echo "✅ Installation complete!"
echo ""
echo "Next steps:"
echo "  1. Run: source ${SHELL_RC}"
echo "  2. From anywhere, type: ${ALIAS_NAME}"
echo ""
echo "This will cd to ${SCRIPT_DIR} and start the menu (run.sh)."
