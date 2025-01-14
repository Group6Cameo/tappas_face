import time
import csv
import subprocess
import threading
import os
from adafruit_servokit import ServoKit
from datetime import datetime

# =============================
# ========== SETTINGS ==========
# =============================
CSV_PATH = 'tmp/face_info_log.csv'
IMAGE_WIDTH = 640
IMAGE_HEIGHT = 360
TARGET_GALLERY_ID = '1'
# import pandas as pd
# unique_gallery_ids = pd.read_csv(LOG_FILE)['Gallery_ID'].unique()

INITIAL_SERVO0_ANGLE = 120
INITIAL_SERVO1_ANGLE = 95
INITIAL_ARM_ANGLE = 90

DEADZONE_X = 60
DEADZONE_Y = 40

K_P = 0.5
SERVO_STEP = 1.5

CENTRE_X = IMAGE_WIDTH // 2
CENTRE_Y = IMAGE_HEIGHT // 2

# =============================
# ========== SETUP =============
# =============================
kit = ServoKit(channels=16)

kit.servo[0].set_pulse_width_range(400, 2600)
kit.servo[1].set_pulse_width_range(400, 2600)
kit.servo[2].set_pulse_width_range(400, 2600)
kit.servo[3].set_pulse_width_range(400, 2600)

# =============================
# ========== FUNCTIONS =========
# =============================
def set_arm_position(kit_instance, angle):
    """Linked control for servo2 & servo3, so that when servo3 moves forward,
    servo2 moves backward. The 'angle' must be between 0 and 180."""
    if angle < 0 or angle > 180:
        raise ValueError("Angle must be between 0 and 180 degrees.")
    kit_instance.servo[3].angle = angle
    kit_instance.servo[2].angle = 180 - angle

deadzones = {
    'servo0': (999, -1),
    'servo1': (999, -1),
    'arm':   (999, -1)
}

def in_deadzone(angle, deadzone):
    dz_min, dz_max = deadzone
    if dz_min <= dz_max:
        return dz_min <= angle <= dz_max
    return False

def set_servo_angle_with_deadzone(servo_index, angle, deadzone_key):
    angle = max(0, min(180, angle))
    if not in_deadzone(angle, deadzones[deadzone_key]):
        kit.servo[servo_index].angle = angle

def set_arm_angle_with_deadzone(angle):
    angle = max(0, min(180, angle))
    if not in_deadzone(angle, deadzones['arm']):
        set_arm_position(kit, angle)

# ===========================
# ====== CONTROL LOGIC =======
# ===========================
servo0_angle = INITIAL_SERVO0_ANGLE
servo1_angle = INITIAL_SERVO1_ANGLE
arm_angle = INITIAL_ARM_ANGLE

kit.servo[0].angle = servo0_angle
kit.servo[1].angle = servo1_angle
set_arm_position(kit, arm_angle)

def adjust_servo_angles_using_old_logic(target_x, target_y):
    """
    Original motor control logic:
      - Move servo1 (horizontal) by K_P*error_x if outside deadzone
      - Move servo0 (partial vertical) by K_P*error_y if outside deadzone
      - If servo0 hits top/bottom limit, move the arm angle (servo2 & 3).
    """
    global servo0_angle, servo1_angle, arm_angle

    error_x = CENTRE_X - target_x
    error_y = CENTRE_Y - target_y

    # Horizontal servo1
    if abs(error_x) > DEADZONE_X:
        delta_servo1 = K_P * error_x
        delta_servo1 = max(-SERVO_STEP, min(SERVO_STEP, delta_servo1))
    else:
        delta_servo1 = 0

    # Vertical servo0
    if abs(error_y) > DEADZONE_Y:
        delta_servo0 = K_P * error_y
        delta_servo0 = max(-SERVO_STEP, min(SERVO_STEP, delta_servo0))
    else:
        delta_servo0 = 0

    new_servo1_angle = servo1_angle + delta_servo1
    new_servo0_angle = servo0_angle - delta_servo0

    # Clamp angles
    new_servo1_angle = max(0, min(180, new_servo1_angle))
    new_servo0_angle = max(0, min(180, new_servo0_angle))

    # Check if servo0 can move
    servo0_moved = True
    if (delta_servo0 < 0 and new_servo0_angle <= 0):
        servo0_moved = False
    elif (delta_servo0 > 0 and new_servo0_angle >= 180):
        servo0_moved = False

    new_arm_angle = arm_angle
    if not servo0_moved:
        # servo0 is at a limit, move the arm
        if delta_servo0 < 0 and new_servo0_angle <= 0:
            arm_delta = -SERVO_STEP
            new_arm_angle = max(0, arm_angle + arm_delta)
        elif delta_servo0 > 0 and new_servo0_angle >= 180:
            arm_delta = SERVO_STEP
            new_arm_angle = min(180, arm_angle + arm_delta)
    else:
        servo0_angle = new_servo0_angle

    # Set servo1
    set_servo_angle_with_deadzone(1, new_servo1_angle, 'servo1')
    servo1_angle = new_servo1_angle

    # If servo0 moved, update it. Otherwise move arm.
    if servo0_moved:
        set_servo_angle_with_deadzone(0, servo0_angle, 'servo0')
    else:
        set_arm_angle_with_deadzone(new_arm_angle)
        arm_angle = new_arm_angle

# =============================
# === CSV-BASED DETECTION ====
# =============================

def start_monitor_detection():
    """
    Launches the face-detection script in the background. 
    Adjust as needed for your environment.
    """
    subprocess.Popen(['python3', 'monitor_detections.py'])
    print("Started monitor_detection.py")

def get_latest_csv_row(csv_path):
    """
    Reads the CSV, returns the row with the largest Rec_BufferSet
    (the second column). If no data, returns None.
    """
    try:
        with open(csv_path, 'r') as f:
            rows = list(csv.reader(f))
        if len(rows) <= 1:
            return None  # only header or empty file

        header = rows[0]
        data_lines = rows[1:]
        
        # The second column is 'Rec_BufferSet' => index=1
        # We'll parse it as an integer and find the maximum
        valid_lines = []
        for row in data_lines:
            # row format: 
            # [Timestamp, Rec_BufferSet, Detection_ID, Gallery_ID, Label, Center_X, Center_Y]
            try:
                offset_int = int(row[1])  # convert Rec_BufferSet to int
                valid_lines.append((offset_int, row))
            except:
                # skip invalid rows
                pass

        if not valid_lines:
            return None
        
        # Sort by offset ascending, last item has the largest offset
        valid_lines.sort(key=lambda x: x[0])
        max_offset, max_row = valid_lines[-1]
        return max_row
    except FileNotFoundError:
        return None
    except:
        return None

def track_face():
    """
    Continuously reads the CSV, finds the row with the largest Rec_BufferSet,
    and moves the servos if that offset is new since last time.
    """
    last_offset = -1
    x_last = None
    y_last = None

    while True:
        try:
            latest_row = get_latest_csv_row(CSV_PATH)
            if latest_row is not None:
                # latest_row:
                # [Timestamp, Rec_BufferSet, Detection_ID, Gallery_ID, Label, Center_X, Center_Y]
                timestamp_str = latest_row[0]
                offset_str = latest_row[1]
                detection_id = latest_row[2]
                gallery_id   = latest_row[3]
                label        = latest_row[4]
                center_x_str = latest_row[5]
                center_y_str = latest_row[6]

                # Check validity
                if (gallery_id == TARGET_GALLERY_ID and 
                    detection_id not in [None, '', 'null'] and
                    center_x_str not in [None, '', 'null'] and
                    center_y_str not in [None, '', 'null']):
                    
                    try:
                        offset_int = int(offset_str)
                        center_x = float(center_x_str)
                        center_y = float(center_y_str)
                    except:
                        offset_int = -1
                        center_x, center_y = None, None
                    
                    # If we have a valid offset AND it's larger than last_offset => new data
                    if offset_int > last_offset and center_x is not None and center_y is not None:
                        last_offset = offset_int
                        x_last = center_x
                        y_last = center_y
                        
                        # Move servos
                        adjust_servo_angles_using_old_logic(x_last, y_last)
                    else:
                        # offset is the same => no new lines
                        # optionally keep moving servo to x_last,y_last
                        pass
                else:
                    # The largest row doesn't match our filter conditions
                    pass

            else:
                # CSV is empty or missing => no data to track
                pass

            # If desired, you can keep moving the servo to the last known coords:
            # if x_last is not None and y_last is not None:
            #     adjust_servo_angles_using_old_logic(x_last, y_last)
            
            time.sleep(0.01)

        except KeyboardInterrupt:
            print("\nTracking stopped by user.")
            break
        except Exception as e:
            print(f"Error reading CSV: {e}")
            time.sleep(0.1)

def cleanup_servos():
    """
    Smoothly move the servos back to neutral (90, 90, 90).
    Increase 'delay' or 'steps' if you want a slower move.
    """
    global servo0_angle, servo1_angle, arm_angle
    target0, target1, targetA = 90, 90, 90
    steps = 10
    delay = 0.01

    for i in range(steps):
        servo0_angle += (target0 - servo0_angle) / (steps - i)
        servo1_angle += (target1 - servo1_angle) / (steps - i)
        arm_angle += (targetA - arm_angle) / (steps - i)
        
        set_servo_angle_with_deadzone(0, servo0_angle, 'servo0')
        set_servo_angle_with_deadzone(1, servo1_angle, 'servo1')
        set_arm_angle_with_deadzone(arm_angle)
        time.sleep(delay)

def main():
    try:
        start_monitor_detection()
        # Give it time to spin up
        time.sleep(2)
        print("Starting CSV-based face tracking with Rec_BufferSet logic...")
        track_face()
    except KeyboardInterrupt:
        print("Interrupted by user.")
    finally:
        print("Cleaning up servo positions...")
        cleanup_servos()

if __name__ == "__main__":
    main()
