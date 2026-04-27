#!/usr/bin/env python3
"""
USB Device Manager

Runs as root every 5 seconds to:
1. Find all USB devices and their iSerial
2. Match iSerial to records in arm_mappings.csv
3. For matched devices: change group ownership and create symlinks
4. Clean up stale symlinks in /home/so101p2*/dev/

Currently in dry-run mode: prints actions instead of executing them.
"""

import os
import sys
import glob
import time
import grp
import csv


ARM_MAPPINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arm_mappings.csv")
MERMAID_OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "usb_tree.mmd")
POLL_INTERVAL = 5  # seconds


# Hardcoded emoji for each user (up to 10 users)
USER_EMOJIS = {
    "so101p2dev": "🟠",
    "user1": "🔴",
    "user2": "🟢",
    "user3": "🔵",
    "user4": "🟣",
    "user5": "🟡",
    "user6": "🟤",
    "user7": "⚫",
    "user8": "⚪",
    "user9": "🩷",
}


def get_user_emoji(user_name):
    """Return a hardcoded emoji for a user name."""
    return USER_EMOJIS.get(user_name, "👤")


def get_video_devices_for_usb(usb_syspath):
    """
    Given a USB device syspath, find all /dev/video* devices associated with it.
    Returns a list of video device names like ['video0'].
    """
    video_devices = []
    dev_name = os.path.basename(usb_syspath)
    parent_dir = os.path.dirname(usb_syspath)

    for iface_path in sorted(glob.glob(os.path.join(parent_dir, f"{dev_name}:*"))):
        video_dir = os.path.join(iface_path, "video4linux")
        if os.path.isdir(video_dir):
            for vid_name in sorted(os.listdir(video_dir)):
                if vid_name.startswith("video"):
                    video_devices.append(vid_name)

    return video_devices


def get_video_device_index(video_name):
    """
    Read the V4L2 index for a video device from sysfs.
    index=0 is typically the video feed, index=1 is metadata.
    Returns int or None.
    """
    idx_file = f"/sys/class/video4linux/{video_name}/index"
    if os.path.isfile(idx_file):
        try:
            with open(idx_file, "r") as f:
                return int(f.read().strip())
        except (ValueError, PermissionError, IOError):
            return None
    return None


def process_camera_devices(devices, hub_assignments):
    """
    For cameras downstream of hubs assigned to users:
    - chgrp /dev/video* files to the user
    - create symlinks cam<port> -> video feed, cam<port>-metadata -> metadata
    Returns a dict of {user: set of valid camera symlink names} for cleanup.
    """
    valid_cam_links = {}

    for dev in devices:
        if not dev.get("video_devices"):
            continue

        parent_hub = dev.get("parent")
        if not parent_hub:
            continue

        hub_user = hub_assignments.get(parent_hub)
        if not hub_user:
            continue

        port = dev.get("port")
        if not port:
            continue

        # Classify video devices by index
        video_feed = None
        meta_device = None
        for vid_name in dev["video_devices"]:
            idx = get_video_device_index(vid_name)
            dev_path = f"/dev/{vid_name}"
            if not os.path.exists(dev_path):
                continue
            if idx == 0:
                video_feed = dev_path
            elif idx == 1:
                meta_device = dev_path

        if not video_feed:
            continue

        # Change group ownership for video devices
        for dev_path in [video_feed, meta_device]:
            if not dev_path:
                continue
            current_group = get_group_of_file(dev_path)
            if current_group != hub_user:
                try:
                    gid = grp.getgrnam(hub_user).gr_gid
                    os.chown(dev_path, -1, gid)
                    print(f"  Changed group of {dev_path} to {hub_user}")
                except (KeyError, PermissionError) as e:
                    print(f"  ERROR: Failed to change group of {dev_path}: {e}", file=sys.stderr)

        # Create symlinks
        home_dir = f"/home/{hub_user}"
        symlink_dir = os.path.join(home_dir, "dev")
        cam_link = os.path.join(symlink_dir, f"cam{port}")
        meta_link = os.path.join(symlink_dir, f"cam{port}-metadata")

        for link_path, target in [(cam_link, video_feed), (meta_link, meta_device)]:
            if not target:
                continue
            if os.path.islink(link_path):
                current_target = os.readlink(link_path)
                if current_target == target:
                    pass  # Already correct
                else:
                    os.unlink(link_path)
                    os.makedirs(symlink_dir, exist_ok=True)
                    os.symlink(target, link_path)
                    print(f"  Replaced symlink {link_path} -> {target}")
            elif os.path.exists(link_path):
                os.remove(link_path)
                os.makedirs(symlink_dir, exist_ok=True)
                os.symlink(target, link_path)
                print(f"  Created symlink {link_path} -> {target}")
            else:
                os.makedirs(symlink_dir, exist_ok=True)
                os.symlink(target, link_path)
                print(f"  Created symlink {link_path} -> {target}")

        # Track valid symlink names for cleanup
        valid_names = {f"cam{port}"}
        if meta_device:
            valid_names.add(f"cam{port}-metadata")
        valid_cam_links.setdefault(hub_user, set()).update(valid_names)

    return valid_cam_links


def get_device_class(usb_syspath):
    """Read bDeviceClass from sysfs. Returns string like '09' or None."""
    class_file = os.path.join(usb_syspath, "bDeviceClass")
    if os.path.isfile(class_file):
        try:
            with open(class_file, "r") as f:
                return f.read().strip()
        except (PermissionError, IOError):
            return None
    return None


def extract_port_number(name):
    """
    Extract the port number from a USB device name.
    1-2 -> port 2; 1-2.3 -> port 3; usb1 -> None
    """
    if name.startswith("usb"):
        return None
    if "." in name:
        return name.rsplit(".", 1)[1]
    parts = name.split("-", 1)
    if len(parts) == 2:
        return parts[1]
    return None


# In-memory hub user assignments: {iSerial -> user_name}
_hub_assignments = {}


def update_hub_assignments(devices, mappings):
    """
    Update hub-to-user assignments based on downstream ARM devices.
    Rules:
    - If a hub is not assigned and has direct downstream ARMs mapped to the SAME user,
      assign the hub to that user.
    - If direct downstream ARMs are mapped to DIFFERENT users, do not assign.
    - Once assigned, a hub keeps its user until physically disconnected.
    - Hubs that are no longer present are removed from assignments.
    """
    global _hub_assignments

    # Build lookups
    iserial_to_mapping = mappings
    present_hub_names = set()
    hubs = [d for d in devices if d.get("device_class") == "09" and not d["name"].startswith("usb")]

    for hub in hubs:
        hub_name = hub["name"]
        present_hub_names.add(hub_name)

        # Skip if already assigned
        if hub_name in _hub_assignments:
            continue

        # Find direct children (devices whose parent is this hub)
        child_users = set()
        for dev in devices:
            if dev.get("parent") == hub_name:
                child_iserial = dev.get("iSerial")
                child_mapping = iserial_to_mapping.get(child_iserial) if child_iserial else None
                if child_mapping:
                    child_users.add(child_mapping["user"])

        # Assign only if exactly one unique user among direct children
        if len(child_users) == 1:
            assigned_user = child_users.pop()
            _hub_assignments[hub_name] = assigned_user
            print(f"  Assigned hub {hub_name} to user {assigned_user}")

    # Remove assignments for disconnected hubs
    disconnected = [name for name in _hub_assignments if name not in present_hub_names]
    for name in disconnected:
        del _hub_assignments[name]
        print(f"  Removed hub assignment for disconnected hub {name}")


def get_usb_device_tree():
    """
    Scan /sys/bus/usb/devices/ and build the USB device tree with hierarchy info.
    Returns a list of dicts with device info including tty/video devices, class, etc.
    """
    usb_sys_path = "/sys/bus/usb/devices/"
    devices = []

    for dev_path in sorted(glob.glob(os.path.join(usb_sys_path, "*"))):
        if not os.path.isdir(dev_path):
            continue

        name = os.path.basename(dev_path)

        # Skip interface directories (e.g. 1-2:1.0, 1-2.3:1.1)
        if ":" in name:
            continue

        info = {"name": name, "syspath": dev_path}

        # Read iSerial
        serial_file = os.path.join(dev_path, "serial")
        if os.path.isfile(serial_file):
            try:
                with open(serial_file, "r") as f:
                    info["iSerial"] = f.read().strip()
            except (PermissionError, IOError):
                info["iSerial"] = None
        else:
            info["iSerial"] = None

        # Read idVendor / idProduct
        for field in ["idVendor", "idProduct"]:
            field_file = os.path.join(dev_path, field)
            if os.path.isfile(field_file):
                try:
                    with open(field_file, "r") as f:
                        info[field] = f.read().strip()
                except (PermissionError, IOError):
                    info[field] = None
            else:
                info[field] = None

        # Read bDeviceClass (09 = hub)
        info["device_class"] = get_device_class(dev_path)

        # Find tty and video devices
        info["tty_devices"] = get_tty_devices_for_usb(dev_path)
        info["video_devices"] = get_video_devices_for_usb(dev_path)

        # Determine parent and port
        if name.startswith("usb"):
            info["parent"] = None
            info["depth"] = 0
            info["port"] = None
        elif "." in name:
            info["parent"] = name.rsplit(".", 1)[0]
            info["depth"] = name.count(".") + 1
            info["port"] = name.rsplit(".", 1)[1]
        else:
            bus_num = name.split("-", 1)[0]
            info["parent"] = f"usb{bus_num}"
            info["depth"] = 1
            info["port"] = name.split("-", 1)[1] if "-" in name else None

        devices.append(info)

    return devices


def mermaid_node_id(name):
    """Sanitize a USB device name for use as a Mermaid node ID."""
    return "node_" + name.replace("-", "_").replace(".", "_")


def generate_mermaid_diagram(devices, mappings, hub_assignments=None):
    """
    Generate a Mermaid flowchart string from the USB device tree.
    Devices are colored by type: root hub, hub, camera, arm, other.
    User assignments are shown as emoji badges.
    Hub assignments are shown for hubs allocated to users.
    Edges are labeled with port numbers.
    """
    if hub_assignments is None:
        hub_assignments = {}
    lines = ["graph TD"]

    # Type class definitions
    lines.append("    classDef root_hub fill:#e1f5fe,stroke:#01579b,stroke-width:3px")
    lines.append("    classDef usb_hub fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px")
    lines.append("    classDef camera fill:#ffebee,stroke:#c62828,stroke-width:2px")
    lines.append("    classDef arm fill:#f1f8e9,stroke:#33691e,stroke-width:2px")
    lines.append("    classDef other fill:#fafafa,stroke:#616161,stroke-width:1px")

    iserial_to_mapping = mappings


    # Determine node types
    def get_node_type(dev):
        if dev["name"].startswith("usb"):
            return "root_hub"
        if dev.get("device_class") == "09":
            return "usb_hub"
        if dev.get("video_devices"):
            return "camera"
        if dev.get("tty_devices"):
            return "arm"
        return "other"

    # Build node entries
    for dev in devices:
        name = dev["name"]
        node_id = mermaid_node_id(name)
        vendor = dev.get("idVendor", "")
        product = dev.get("idProduct", "")
        iserial = dev.get("iSerial", "")
        ttys = dev.get("tty_devices", [])
        videos = dev.get("video_devices", [])
        dev_class = dev.get("device_class", "")
        node_type = get_node_type(dev)

        mapping = iserial_to_mapping.get(iserial) if iserial else None

        # Build node label
        label_parts = [f"<b>{name}</b>"]

        if node_type == "usb_hub":
            label_parts.append("🔄 USB Hub")
            # Show hub user assignment if present
            hub_user = hub_assignments.get(name)
            if hub_user:
                emoji = get_user_emoji(hub_user)
                label_parts.append(f"{emoji} {hub_user}")
        elif node_type == "root_hub":
            label_parts.append("🔄 Root Hub")

        if vendor and product:
            label_parts.append(f"{vendor}:{product}")

        if iserial and not name.startswith("usb"):
            label_parts.append(f"SN: {iserial}")

        if ttys:
            label_parts.append(f"tty: {', '.join(ttys)}")
        if videos:
            label_parts.append(f"video: {', '.join(videos)}")

        # Camera mapping info (if parent hub is assigned)
        if node_type == "camera":
            parent_hub = dev.get("parent")
            hub_user = hub_assignments.get(parent_hub) if parent_hub else None
            if hub_user:
                port = dev.get("port", "?")
                emoji = get_user_emoji(hub_user)
                label_parts.append(f"{emoji} {hub_user}")
                label_parts.append(f"cam{port}, cam{port}-metadata")

        # User assignment badge inside node label (for CSV-mapped ARMs)
        if mapping:
            user = mapping["user"]
            devname = mapping["devname"]
            emoji = get_user_emoji(user)
            label_parts.append(f"{emoji} {user} / {devname}")

        label = "<br/>".join(label_parts)
        lines.append(f'    {node_id}["{label}"]')

        # Apply type class
        lines.append(f"    class {node_id} {node_type}")

    # Add edges with port labels
    for dev in devices:
        parent = dev.get("parent")
        if parent:
            child_id = mermaid_node_id(dev["name"])
            parent_id = mermaid_node_id(parent)
            port = dev.get("port")
            if port:
                lines.append(f'    {parent_id} -->|"port {port}"| {child_id}')
            else:
                lines.append(f"    {parent_id} --> {child_id}")

    return "\n".join(lines)


_last_mermaid_diagram = None


def write_mermaid_diagram(diagram):
    """Write the mermaid diagram to the output file only if it changed."""
    global _last_mermaid_diagram
    if diagram == _last_mermaid_diagram:
        return  # No change, skip writing

    _last_mermaid_diagram = diagram
    try:
        with open(MERMAID_OUTPUT_FILE, "w") as f:
            f.write(diagram)
        print("  Mermaid diagram updated (USB tree changed)")
    except OSError as e:
        print(f"ERROR: Failed to write mermaid diagram: {e}", file=sys.stderr)




def load_arm_mappings(filepath):
    """
    Load arm_mappings.csv and return a dict mapping iSerial -> {user, devname}.
    CSV format: iSerial,User,DevName
    """
    mappings = {}
    try:
        with open(filepath, "r") as f:
            reader = csv.reader(f)
            header = next(reader, None)  # skip header
            for row in reader:
                if len(row) >= 3:
                    iserial, user, devname = row[0].strip(), row[1].strip(), row[2].strip()
                    mappings[iserial] = {"user": user, "devname": devname}
    except FileNotFoundError:
        print(f"ERROR: Mapping file not found: {filepath}", file=sys.stderr)
    return mappings


def get_usb_devices():
    """
    Scan /sys/bus/usb/devices/ and collect USB device info including iSerial.
    Returns a list of dicts with keys: 'syspath', 'iSerial', 'idVendor', 'idProduct'.
    """
    devices = []
    usb_sys_path = "/sys/bus/usb/devices/"

    for dev_path in sorted(glob.glob(os.path.join(usb_sys_path, "*"))):
        if not os.path.isdir(dev_path):
            continue

        info = {"syspath": dev_path}

        # Read iSerial (serial number)
        serial_file = os.path.join(dev_path, "serial")
        if os.path.isfile(serial_file):
            try:
                with open(serial_file, "r") as f:
                    info["iSerial"] = f.read().strip()
            except (PermissionError, IOError):
                info["iSerial"] = None
        else:
            info["iSerial"] = None

        # Read idVendor
        vendor_file = os.path.join(dev_path, "idVendor")
        if os.path.isfile(vendor_file):
            try:
                with open(vendor_file, "r") as f:
                    info["idVendor"] = f.read().strip()
            except (PermissionError, IOError):
                info["idVendor"] = None
        else:
            info["idVendor"] = None

        # Read idProduct
        product_file = os.path.join(dev_path, "idProduct")
        if os.path.isfile(product_file):
            try:
                with open(product_file, "r") as f:
                    info["idProduct"] = f.read().strip()
            except (PermissionError, IOError):
                info["idProduct"] = None
        else:
            info["idProduct"] = None

        devices.append(info)

    return devices


def get_tty_devices_for_usb(usb_syspath):
    """
    Given a USB device syspath, find all /dev/tty* devices associated with it.
    Looks for tty subdirectories under interface directories (e.g. 1-2.3:1.0/tty/).
    Returns a list of tty device names like ['ttyACM0'].
    """
    tty_devices = []
    dev_name = os.path.basename(usb_syspath)

    # Look for interface directories: <usbpath>:<interface>
    # These are siblings in the same parent directory
    parent_dir = os.path.dirname(usb_syspath)

    for iface_path in sorted(glob.glob(os.path.join(parent_dir, f"{dev_name}:*"))):
        tty_dir = os.path.join(iface_path, "tty")
        if os.path.isdir(tty_dir):
            for tty_name in sorted(os.listdir(tty_dir)):
                if tty_name.startswith("tty"):
                    tty_devices.append(tty_name)

    return tty_devices


def get_group_of_file(filepath):
    """Get the group name that owns the given file."""
    try:
        stat_info = os.stat(filepath)
        return grp.getgrgid(stat_info.st_gid).gr_name
    except (FileNotFoundError, KeyError):
        return None


def process_devices(mappings, symlink_dry_run=True):
    """
    Main processing logic:
    1. Find all USB devices and their iSerial
    2. Match iSerial to arm_mappings records
    3. For matched devices with /dev/tty mapping:
       - Change group ownership if needed (ALWAYS executed)
       - Create/fix symlinks (dry-run if symlink_dry_run=True)
    """
    devices = get_usb_devices()

    # Build a lookup: iSerial -> list of USB device syspaths
    iserial_to_devices = {}
    for d in devices:
        iserial = d.get("iSerial")
        if iserial:
            iserial_to_devices.setdefault(iserial, []).append(d)

    # Process each mapping
    for iserial, mapping in mappings.items():
        user = mapping["user"]
        devname = mapping["devname"]

        if iserial not in iserial_to_devices:
            continue

        for usb_dev in iserial_to_devices[iserial]:
            usb_syspath = usb_dev["syspath"]
            usb_name = os.path.basename(usb_syspath)

            # Find /dev/tty* devices for this USB device
            tty_devs = get_tty_devices_for_usb(usb_syspath)

            if not tty_devs:
                # No tty mapping, skip this device
                continue

            for tty_name in tty_devs:
                dev_path = f"/dev/{tty_name}"

                if not os.path.exists(dev_path):
                    continue

                # Step 3a: Change group ownership if needed (ALWAYS executed)
                current_group = get_group_of_file(dev_path)
                if current_group != user:
                    try:
                        gid = grp.getgrnam(user).gr_gid
                        os.chown(dev_path, -1, gid)
                        print(f"  Changed group of {dev_path} to {user} (was: {current_group})")
                    except (KeyError, PermissionError) as e:
                        print(f"  ERROR: Failed to change group of {dev_path}: {e}", file=sys.stderr)

                # Step 3b: Create/fix symlink at /home/<user>/dev/<devname>
                home_dir = f"/home/{user}"
                symlink_dir = os.path.join(home_dir, "dev")
                symlink_path = os.path.join(symlink_dir, devname)

                if symlink_dry_run:
                    # Check if symlink exists and is correct
                    if os.path.islink(symlink_path):
                        current_target = os.readlink(symlink_path)
                        if current_target == dev_path:
                            pass  # Already correct, no action needed
                        else:
                            print(f"  [DRY-RUN] Replace symlink {symlink_path} -> {dev_path}  (current target: {current_target})")
                    elif os.path.exists(symlink_path):
                        print(f"  [DRY-RUN] Remove existing file {symlink_path} and create symlink -> {dev_path}")
                    else:
                        # Symlink doesn't exist
                        print(f"  [DRY-RUN] mkdir -p {symlink_dir} && ln -s {dev_path} {symlink_path}")
                else:
                    if os.path.islink(symlink_path):
                        current_target = os.readlink(symlink_path)
                        if current_target == dev_path:
                            pass  # Already correct
                        else:
                            # Replace with correct target
                            os.unlink(symlink_path)
                            os.symlink(dev_path, symlink_path)
                            print(f"  Replaced symlink {symlink_path} -> {dev_path}")
                    elif os.path.exists(symlink_path):
                        # A regular file exists, remove and replace
                        os.remove(symlink_path)
                        os.makedirs(symlink_dir, exist_ok=True)
                        os.symlink(dev_path, symlink_path)
                        print(f"  Created symlink {symlink_path} -> {dev_path}")
                    else:
                        # Doesn't exist, create it
                        os.makedirs(symlink_dir, exist_ok=True)
                        os.symlink(dev_path, symlink_path)
                        print(f"  Created symlink {symlink_path} -> {dev_path}")


def cleanup_stale_symlinks(mappings, valid_cam_links=None, cleanup_dry_run=True):
    """
    For all symlinks in /home/so101p2*/dev/, remove if:
    - The symlink points to a device file in /dev that no longer exists, OR
    - The symlink name does not match any valid name (CSV devname or camera link)
    """
    if valid_cam_links is None:
        valid_cam_links = {}

    # Build a set of valid devnames per user from the mappings
    valid_names_per_user = {}
    for iserial, m in mappings.items():
        user = m["user"]
        devname = m["devname"]
        valid_names_per_user.setdefault(user, set()).add(devname)

    # Add camera symlink names to valid names
    for user, cam_names in valid_cam_links.items():
        valid_names_per_user.setdefault(user, set()).update(cam_names)

    for dev_dir in sorted(glob.glob("/home/so101p2*/dev/")):
        if not os.path.isdir(dev_dir):
            continue

        # Extract username from path: /home/<user>/dev/
        parts = dev_dir.rstrip("/").split("/")
        if len(parts) >= 3:
            user = parts[-2]
        else:
            continue

        valid_names = valid_names_per_user.get(user, set())

        for entry in sorted(os.listdir(dev_dir)):
            entry_path = os.path.join(dev_dir, entry)
            if not os.path.islink(entry_path):
                continue
            target = os.readlink(entry_path)
            # Only consider symlinks that point into /dev
            if not target.startswith("/dev/"):
                continue

            # Check if the symlink name is valid
            if entry not in valid_names:
                if cleanup_dry_run:
                    print(f"  [DRY-RUN] rm {entry_path}  (not in valid names, valid: {valid_names or 'none'})")
                else:
                    try:
                        os.unlink(entry_path)
                        print(f"  Removed orphaned symlink {entry_path} -> {target}  (not in valid names)")
                    except OSError as e:
                        print(f"  ERROR: Failed to remove {entry_path}: {e}", file=sys.stderr)
                continue

            # Check if the target device file still exists
            if not os.path.exists(target):
                if cleanup_dry_run:
                    print(f"  [DRY-RUN] rm {entry_path}  (stale target: {target})")
                else:
                    try:
                        os.unlink(entry_path)
                        print(f"  Removed stale symlink {entry_path} -> {target}")
                    except OSError as e:
                        print(f"  ERROR: Failed to remove {entry_path}: {e}", file=sys.stderr)


def main():
    if os.geteuid() != 0:
        print("WARNING: This program should be run as root for full functionality.", file=sys.stderr)

    print("=" * 60)
    print("USB Device Manager (LIVE MODE)")
    print(f"Mapping file: {ARM_MAPPINGS_FILE}")
    print(f"Poll interval: {POLL_INTERVAL}s")
    print("=" * 60)

    mappings = load_arm_mappings(ARM_MAPPINGS_FILE)
    if not mappings:
        print("No mappings loaded, exiting.")
        return

    print(f"Loaded {len(mappings)} mapping(s):")
    for iserial, m in mappings.items():
        print(f"  iSerial={iserial} -> user={m['user']}, devname={m['devname']}")
    print()

    while True:
        print(f"--- Poll cycle at {time.strftime('%Y-%m-%d %H:%M:%S')} ---")

        # Build device tree once per cycle
        tree_devices = get_usb_device_tree()

        # Update hub assignments first (needed for camera processing)
        update_hub_assignments(tree_devices, mappings)

        # Process ARM devices (tty)
        process_devices(mappings, symlink_dry_run=False)

        # Process camera devices (video) for hubs assigned to users
        valid_cam_links = process_camera_devices(tree_devices, _hub_assignments)

        # Clean up stale symlinks (arms + cameras)
        cleanup_stale_symlinks(mappings, valid_cam_links, cleanup_dry_run=False)

        # Generate mermaid diagram
        diagram = generate_mermaid_diagram(tree_devices, mappings, _hub_assignments)
        write_mermaid_diagram(diagram)

        print()
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()