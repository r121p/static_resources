#!/bin/bash

DEV_DIR="${HOME}/dev"

echo "=================================================="
echo "  Device Usage Checker for ~/dev"
echo "=================================================="
echo ""
echo "Scanning directory: $DEV_DIR"
echo ""

if [ ! -d "$DEV_DIR" ]; then
    echo "ERROR: Directory $DEV_DIR does not exist."
    exit 1
fi

# Arrays to store device info
declare -a names
declare -a paths
declare -a pid_lists
declare -a is_busy
busy_indices=()

index=0
busy_count=0

# Iterate over symlinks in ~/dev
for entry in "$DEV_DIR"/*; do
    if [ ! -e "$entry" ]; then
        # Directory is empty or no matches
        continue
    fi

    if [ ! -L "$entry" ]; then
        continue
    fi

    real_path=$(readlink -f "$entry")
    name=$(basename "$entry")

    # Only check actual device files (character or block)
    if [ ! -c "$real_path" ] && [ ! -b "$real_path" ]; then
        continue
    fi

    # Check for processes using this device
    pid_list=$(fuser "$real_path" 2>/dev/null)

    names[$index]="$name"
    paths[$index]="$real_path"
    pid_lists[$index]="$pid_list"

    if [ -n "$pid_list" ]; then
        is_busy[$index]=1
        busy_indices+=($index)
        busy_count=$((busy_count + 1))
        echo "[$index] $name -> $real_path"
        echo "    STATUS: IN USE by PID(s): $pid_list"
    else
        is_busy[$index]=0
        echo "[$index] $name -> $real_path"
        echo "    STATUS: No process is using this device"
    fi

    echo ""
    index=$((index + 1))
done

if [ "$index" -eq 0 ]; then
    echo "No device symlinks found in $DEV_DIR."
    exit 0
fi

echo "=================================================="
echo "  Scan complete. Found $index device(s), $busy_count busy."
echo "=================================================="
echo ""

if [ "$busy_count" -eq 0 ]; then
    echo "All devices are free. Nothing to do."
    exit 0
fi

echo "Enter the index number(s) of the device(s) you want to free up."
echo "Separate multiple indices with spaces or commas (e.g., '0,2' or '0 2')."
echo "Type 'all' to kill all processes on all busy devices."
echo "Press Enter or type 'q' to quit without killing anything."
echo ""
read -r -p "Selection: " selection

# Trim whitespace
selection=$(echo "$selection" | xargs)

if [ -z "$selection" ] || [ "$selection" = "q" ] || [ "$selection" = "Q" ]; then
    echo "No devices selected. Exiting without killing any processes."
    exit 0
fi

# Parse selection
declare -a selected_indices=()

if [ "$selection" = "all" ] || [ "$selection" = "ALL" ]; then
    selected_indices=("${busy_indices[@]}")
else
    # Replace commas with spaces, then iterate
    selection_clean=$(echo "$selection" | tr ',' ' ')
    for num in $selection_clean; do
        # Validate it's a number
        if ! [[ "$num" =~ ^[0-9]+$ ]]; then
            echo "WARNING: '$num' is not a valid index. Skipping."
            continue
        fi

        if [ "$num" -lt 0 ] || [ "$num" -ge "$index" ]; then
            echo "WARNING: Index $num is out of range. Skipping."
            continue
        fi

        if [ "${is_busy[$num]}" -ne 1 ]; then
            echo "WARNING: Device [$num] is not in use. Skipping."
            continue
        fi

        # Avoid duplicates
        already_added=0
        for existing in "${selected_indices[@]}"; do
            if [ "$existing" -eq "$num" ]; then
                already_added=1
                break
            fi
        done

        if [ "$already_added" -eq 0 ]; then
            selected_indices+=($num)
        fi
    done
fi

if [ "${#selected_indices[@]}" -eq 0 ]; then
    echo "No valid busy devices selected. Exiting without killing any processes."
    exit 0
fi

echo ""
echo "The following devices will be freed up:"
for idx in "${selected_indices[@]}"; do
    echo "  [$idx] ${names[$idx]} -> ${paths[$idx]} (PID(s): ${pid_lists[$idx]})"
done

echo ""
read -r -p "Are you sure you want to kill these processes? [y/N]: " confirm
if [[ "$confirm" =~ ^[Yy]$ ]]; then
    for idx in "${selected_indices[@]}"; do
        device_path="${paths[$idx]}"
        echo "Killing processes using ${names[$idx]} ($device_path)..."
        fuser -k "$device_path" >/dev/null 2>&1
        if [ $? -eq 0 ]; then
            echo "  Done."
        else
            echo "  Failed or no processes to kill (they may have already exited)."
        fi
    done
    echo ""
    echo "Cleanup complete."
else
    echo "Aborted. No processes were killed."
fi
