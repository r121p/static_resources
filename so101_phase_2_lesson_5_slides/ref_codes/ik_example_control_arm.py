#!/usr/bin/env python3
"""
Pick and place demos with selectable examples.

Usage:
    source phosphobot/.venv/bin/activate
    python ik_example_control_arm.py
"""

import asyncio
import os
from ik import ArmController


def resolve_arm_alias(alias: str) -> tuple[str, str]:
    """
    Resolve an arm alias to its device path and serial identifier.

    Supported aliases:
        white_1 -> ~/dev/white_1
        white_2 -> ~/dev/white_2

    Returns:
        (serial_id, device_path) where device_path is the resolved symlink.
    """
    dev_path = os.path.expanduser(f"~/dev/{alias}")
    if not os.path.exists(dev_path):
        raise FileNotFoundError(
            f"Alias '{alias}' not found at {dev_path}. "
            f"Make sure the symlink exists (e.g. white_1 -> /dev/ttyACM0)."
        )
    resolved = os.path.realpath(dev_path)
    return alias, resolved


def print_move_result(result: dict):
    """Print the move result with position error."""
    if result:
        err = result.get('error', {}).get('position_cm', [0, 0, 0])
        err_mag = sum(e**2 for e in err)**0.5
        print(f"   Position error: {err_mag:.2f}cm")


async def example_1_pick_and_place_with_show(arm: ArmController):
    """
    Example 1: Pick up, show at intermediate position, rotate wrist, then place down.
    """
    print("\n" + "="*60)
    print("EXAMPLE 1: PICK AND PLACE WITH INTERMEDIATE POSITION")
    print("="*60)

    # Orientation for pick/place: ry=-90 points gripper down
    pick_ry = -90.0
    pick_rx = 0.0
    pick_rz = 0.0

    pick_x, pick_y, pick_z = -15, 10, -12
    place_x, place_y, place_z = -8, 0, -12

    # Move above pick
    print("\nMoving above pick position...")
    result = await arm.move_to_pose(
        x=pick_x, y=pick_y, z=pick_z + 8,
        rx=pick_rx, ry=pick_ry, rz=pick_rz,
        duration=3.0
    )
    print_move_result(result)

    # Open gripper
    print("Opening gripper...")
    arm.set_gripper(opening=50.0)

    # Move down to pick
    print("Moving down to pick...")
    result = await arm.move_to_pose(
        x=pick_x, y=pick_y, z=pick_z,
        rx=pick_rx, ry=pick_ry, rz=pick_rz,
        duration=2.0
    )
    print_move_result(result)

    # Close gripper
    print("Closing gripper...")
    arm.set_gripper(opening=0.0)
    await asyncio.sleep(1.0)

    # Lift
    print("Lifting object...")
    result = await arm.move_to_pose(
        x=pick_x, y=pick_y, z=pick_z + 5,
        rx=pick_rx, ry=pick_ry, rz=pick_rz,
        duration=3.0
    )
    print_move_result(result)

    # Move to intermediate position
    print("\nMoving to intermediate position (x=0, y=15, z=0)...")
    print("Note: Using position-only IK with locked wrist roll (90 deg)")
    print("because the arm has only 5 DOF and cannot control all 6 pose parameters.")
    result = await arm.move_to_pose(
        x=0, y=15, z=0,
        position_only=True,
        locked_joints={4: 90.0},  # Lock wrist roll to 90 degrees
        duration=4.0
    )
    print_move_result(result)

    # Hold at intermediate position
    print("Holding at intermediate position for 2 seconds...")
    await arm.hold_position(duration=2.0)

    # Rotate gripper by only moving wrist roll axis
    print("\nRotating gripper by moving wrist roll to 0 degrees...")
    await arm.move_joint(joint_index=4, angle=0.0, unit="degrees", duration=2.0)

    # Hold after rotation
    print("Holding for 2 seconds...")
    await arm.hold_position(duration=2.0)

    # Now move to place position
    print("\nMoving to place position...")
    result = await arm.move_to_pose(
        x=place_x, y=place_y, z=place_z + 5,
        rx=0, ry=-90, rz=0,
        duration=4.0
    )
    print_move_result(result)

    # Move down to place
    print("Moving down to place...")
    result = await arm.move_to_pose(
        x=place_x, y=place_y, z=place_z,
        rx=0, ry=-90, rz=0,
        duration=2.0
    )
    print_move_result(result)

    # Open gripper
    print("Opening gripper to release...")
    arm.set_gripper(opening=50.0)

    # Move up
    print("Moving up...")
    result = await arm.move_to_pose(
        x=place_x, y=place_y, z=place_z + 5,
        rx=0, ry=-90, rz=0,
        duration=2.0
    )
    print_move_result(result)


async def example_2_pick_up_and_place_down(arm: ArmController):
    """
    Example 2: Pick up, lift, then place down.
    No intermediate show position, no wrist rotation.
    """
    print("\n" + "="*60)
    print("EXAMPLE 2: PICK UP, LIFT, THEN PLACE DOWN")
    print("="*60)

    pick_ry = -90.0
    pick_rx = 0.0
    pick_rz = 0.0

    pick_x, pick_y, pick_z = -15, 10, -12
    place_x, place_y, place_z = -8, 0, -12

    # Move above pick
    print("\nMoving above pick position...")
    result = await arm.move_to_pose(
        x=pick_x, y=pick_y, z=pick_z + 8,
        rx=pick_rx, ry=pick_ry, rz=pick_rz,
        duration=3.0
    )
    print_move_result(result)

    # Open gripper
    print("Opening gripper...")
    arm.set_gripper(opening=50.0)

    # Move down to pick
    print("Moving down to pick...")
    result = await arm.move_to_pose(
        x=pick_x, y=pick_y, z=pick_z,
        rx=pick_rx, ry=pick_ry, rz=pick_rz,
        duration=2.0
    )
    print_move_result(result)

    # Close gripper
    print("Closing gripper...")
    arm.set_gripper(opening=0.0)
    await asyncio.sleep(1.0)

    # Lift object
    print("Lifting object...")
    result = await arm.move_to_pose(
        x=pick_x, y=pick_y, z=pick_z + 5,
        rx=pick_rx, ry=pick_ry, rz=pick_rz,
        duration=3.0
    )
    print_move_result(result)

    # Hold briefly while lifted
    print("Holding lifted position for 1 second...")
    await asyncio.sleep(1.0)

    # Move to place position
    print("\nMoving to place position...")
    result = await arm.move_to_pose(
        x=place_x, y=place_y, z=place_z + 5,
        rx=0, ry=-90, rz=0,
        duration=4.0
    )
    print_move_result(result)

    # Move down to place
    print("Moving down to place...")
    result = await arm.move_to_pose(
        x=place_x, y=place_y, z=place_z,
        rx=0, ry=-90, rz=0,
        duration=2.0
    )
    print_move_result(result)

    # Open gripper
    print("Opening gripper to release...")
    arm.set_gripper(opening=50.0)

    # Move up
    print("Moving up...")
    result = await arm.move_to_pose(
        x=place_x, y=place_y, z=place_z + 5,
        rx=0, ry=-90, rz=0,
        duration=2.0
    )
    print_move_result(result)


async def example_3_horizontal_pick(arm: ArmController):
    """
    Example 3: Horizontal pick.
    Move to start, dash forward, close gripper, and come back.
    All moves lock wrist to 90 deg and use position-only IK.
    """
    print("\n" + "="*60)
    print("EXAMPLE 3: HORIZONTAL PICK (POSITION-ONLY, WRIST LOCKED 90 DEG)")
    print("="*60)

    start_x, start_y, start_z = -10, -5, 0
    dash_x = 0

    # Move to start position
    print("\nMoving to start position (x=-10, y=-5, z=0)...")
    result = await arm.move_to_pose(
        x=start_x, y=start_y, z=start_z,
        position_only=True,
        locked_joints={4: 90.0},
        duration=3.0
    )
    print_move_result(result)

    # Open gripper before dash
    print("Opening gripper...")
    arm.set_gripper(opening=50.0)
    await asyncio.sleep(0.5)

    # Dash to x=0
    print("Dashing to x=0...")
    result = await arm.move_to_pose(
        x=dash_x, y=start_y, z=start_z,
        position_only=True,
        locked_joints={4: 90.0},
        duration=1.5
    )
    print_move_result(result)

    # Close gripper
    print("Closing gripper...")
    arm.set_gripper(opening=0.0)
    await asyncio.sleep(1.0)

    # Come back to start
    print("Coming back to start position...")
    result = await arm.move_to_pose(
        x=start_x, y=start_y, z=start_z,
        position_only=True,
        locked_joints={4: 90.0},
        duration=3.0
    )
    print_move_result(result)

    # Open gripper to release
    print("Opening gripper to release...")
    arm.set_gripper(opening=50.0)
    await asyncio.sleep(0.5)


async def main():
    """Main entry point with menu selection."""

    # Arm selection prompt
    print("\n" + "="*60)
    print("SELECT ARM")
    print("="*60)
    print("Available aliases: white_1, white_2")
    print("="*60)

    while True:
        arm_alias = input("\nEnter arm alias (white_1/white_2): ").strip()
        if arm_alias in ("white_1", "white_2"):
            break
        print("Invalid alias. Please enter white_1 or white_2.")

    try:
        serial_id, device_path = resolve_arm_alias(arm_alias)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return

    print(f"\nResolved alias '{arm_alias}' -> {device_path}")
    arm = ArmController(serial_id=serial_id, device_name=device_path)

    print("\nConnecting to arm...")
    if not await arm.connect():
        print("Failed to connect!")
        return
    print("Connected!")

    try:
        print("\nEnabling torque...")
        arm.torque_on()

        print("Initializing pose...")
        await arm.initialize_pose()

        # Example selection prompt
        print("\n" + "="*60)
        print("SELECT AN EXAMPLE TO PLAY")
        print("="*60)
        print("1) Pick and place with intermediate show + wrist rotation")
        print("2) Pick up, lift, then place down")
        print("3) Horizontal pick (position-only, wrist locked 90 deg)")
        print("="*60)

        while True:
            choice = input("\nEnter your choice (1/2/3): ").strip()
            if choice in ("1", "2", "3"):
                break
            print("Invalid choice. Please enter 1, 2, or 3.")

        if choice == "1":
            await example_1_pick_and_place_with_show(arm)
        elif choice == "2":
            await example_2_pick_up_and_place_down(arm)
        elif choice == "3":
            await example_3_horizontal_pick(arm)

        # Return home
        print("\nReturning to home position...")
        result = await arm.move_to_pose(
            x=-20, y=0, z=0,
            rx=0, ry=0, rz=0,
            duration=5.0
        )
        print_move_result(result)

        # Close gripper and hold before power off
        print("Closing gripper...")
        arm.set_gripper(opening=0.0)
        await arm.hold_position(duration=3.0)

        

    finally:
        print("\nDisabling torque...")
        arm.torque_off()

        print("Disconnecting...")
        await arm.disconnect()
        print("Done!")


if __name__ == "__main__":
    print("="*60)
    print("SO-100 Pick and Place Demo")
    print("="*60)
    asyncio.run(main())
