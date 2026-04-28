#!/bin/bash
# ============================================================
#  Dummy User Launcher — run this script and pick a service
# ============================================================

set -euo pipefail

# Colours
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Colour

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${SCRIPT_DIR}/phosphobot/.venv/bin/activate"
LEROBOT_VENV="${SCRIPT_DIR}/lerobot_venv/bin/activate"

clear
echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║          SO-100 Robot Arm & Camera Launcher              ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# ------------------------------------------------------------------
# Menu
# ------------------------------------------------------------------
echo -e "${GREEN}1)${NC}  ${YELLOW}arm_control_server.py${NC}"
echo -e "     Start a Flask web UI to control the SO-100 robot arm."
echo -e "     Opens a browser page with sliders for arm pose & gripper."
echo -e "     ${CYAN}Requires:${NC} phosphobot/.venv"
echo ""

echo -e "${GREEN}2)${NC}  ${YELLOW}camera_stream_server.py${NC}"
echo -e "     Start a Flask server that streams live video from all"
echo -e "     cameras found under ~/dev."
echo -e "     ${CYAN}Requires:${NC} phosphobot/.venv"
echo ""

echo -e "${GREEN}3)${NC}  ${YELLOW}ik_example_control_arm.py${NC}"
echo -e "     Run automated pick-and-place demos using inverse kinematics."
echo -e "     Choose from several built-in movement examples."
echo -e "     ${CYAN}Requires:${NC} phosphobot/.venv"
echo ""

echo -e "${GREEN}4)${NC}  ${YELLOW}check_dev_usage.sh${NC}"
echo -e "     Check which processes are currently holding device files"
echo -e "     in ~/dev (e.g. /dev/ttyACM*, cameras, etc.)."
echo -e "     Useful when the Python scripts fail with 'device busy' errors."
echo ""

echo -e "${GREEN}5)${NC}  ${YELLOW}arm_setup.sh --calibrate${NC}"
echo -e "     Run calibration on a selected arm (leader or follower)."
echo -e "     ${CYAN}Requires:${NC} lerobot_venv"
echo -e "     ${RED}WARNING:${NC} You must be PHYSICALLY NEXT TO THE ROBOT."
echo -e "     You will need to move the robot joints by hand during the process."
echo ""

echo -e "${RED}q)${NC}  Quit"
echo ""

read -rp "Pick an option (1-5, or q): " choice

case "${choice}" in
  1)
    echo ""
    echo -e "${CYAN}▶ Launching arm_control_server.py …${NC}"
    if [ -f "${VENV}" ]; then
      # shellcheck source=/dev/null
      source "${VENV}"
      python "${SCRIPT_DIR}/arm_control_server.py"
    else
      echo -e "${RED}ERROR:${NC} Virtual environment not found at ${VENV}"
      exit 1
    fi
    ;;

  2)
    echo ""
    echo -e "${CYAN}▶ Launching camera_stream_server.py …${NC}"
    if [ -f "${VENV}" ]; then
      # shellcheck source=/dev/null
      source "${VENV}"
      python "${SCRIPT_DIR}/camera_stream_server.py"
    else
      echo -e "${RED}ERROR:${NC} Virtual environment not found at ${VENV}"
      exit 1
    fi
    ;;

  3)
    echo ""
    echo -e "${CYAN}▶ Launching ik_example_control_arm.py …${NC}"
    if [ -f "${VENV}" ]; then
      # shellcheck source=/dev/null
      source "${VENV}"
      python "${SCRIPT_DIR}/ik_example_control_arm.py"
    else
      echo -e "${RED}ERROR:${NC} Virtual environment not found at ${VENV}"
      exit 1
    fi
    ;;

  4)
    echo ""
    echo -e "${YELLOW}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║  REMINDER                                                ║${NC}"
    echo -e "${YELLOW}║  If you see a process using the device you need,         ║${NC}"
    echo -e "${YELLOW}║  ${RED}CHECK WITH YOUR GROUPMATES${YELLOW} before killing it!          ║${NC}"
    echo -e "${YELLOW}║  They might be in the middle of an experiment.           ║${NC}"
    echo -e "${YELLOW}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    read -rp "Run check_dev_usage.sh now? [y/N]: " confirm
    if [[ "${confirm}" =~ ^[Yy]$ ]]; then
      echo ""
      echo -e "${CYAN}▶ Running check_dev_usage.sh …${NC}"
      bash "${SCRIPT_DIR}/check_dev_usage.sh"
    else
      echo "Cancelled."
    fi
    ;;

  5)
    echo ""
    echo -e "${RED}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  ⚠️  PHYSICAL PRESENCE REQUIRED                          ║${NC}"
    echo -e "${RED}║                                                          ║${NC}"
    echo -e "${RED}║  You MUST be physically next to the robot to calibrate.  ║${NC}"
    echo -e "${RED}║  You will need to move the robot joints BY HAND.         ║${NC}"
    echo -e "${RED}║  Do NOT run this remotely.                               ║${NC}"
    echo -e "${RED}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    read -rp "Are you physically next to the robot and ready? [y/N]: " confirm
    if [[ "${confirm}" =~ ^[Yy]$ ]]; then
      echo ""
      echo -e "${CYAN}▶ Launching arm_setup.sh --calibrate …${NC}"
      if [ -f "${LEROBOT_VENV}" ]; then
        bash "${SCRIPT_DIR}/arm_setup.sh" --calibrate
      else
        echo -e "${RED}ERROR:${NC} Virtual environment not found at ${LEROBOT_VENV}"
        exit 1
      fi
    else
      echo "Cancelled."
    fi
    ;;

  q|Q)
    echo "Bye!"
    exit 0
    ;;

  *)
    echo -e "${RED}Invalid option:${NC} ${choice}"
    exit 1
    ;;
esac
