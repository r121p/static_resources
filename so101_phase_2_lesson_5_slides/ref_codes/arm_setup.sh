#!/bin/bash
# ============================================================
#  Arm Calibration / Motor-ID Setup
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lerobot_venv/bin/activate"
trap deactivate EXIT

MODE="${1:-}"
if [ "$MODE" != "--calibrate" ] && [ "$MODE" != "--setup-motors" ]; then
    echo "Usage: $0 --calibrate | --setup-motors"
    exit 1
fi

echo "Available arms:"
ARMS=()
i=1
for link in $(find "${HOME}/dev" -maxdepth 1 -type l | sort); do
    name=$(basename "$link")
    case "$name" in
        black_*|white_*)
            port=$(readlink -f "$link")
            ARMS+=("$name:$port")
            echo "  $i. $name -> $port"
            i=$((i+1))
            ;;
    esac
done

read -r -p "Select: " choice
selected="${ARMS[$((choice-1))]}"
name="${selected%%:*}"
port="${selected##*:}"

echo ""
echo "Selected: $name ($port)"

if [ "$MODE" == "--calibrate" ]; then
    if [[ "$name" == black_* ]]; then
        lerobot-calibrate --teleop.type=so101_leader --teleop.port="$port"
    else
        lerobot-calibrate --robot.type=so101_follower --robot.port="$port"
    fi
else
    if [[ "$name" == black_* ]]; then
        lerobot-setup-motors --teleop.type=so101_leader --teleop.port="$port"
    else
        lerobot-setup-motors --robot.type=so101_follower --robot.port="$port"
    fi
fi
