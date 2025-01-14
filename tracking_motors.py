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

DETECTION_WINDOW = 1.0  # 1 second window for conflict detection
CONFLICT_THRESHOLD = 3  # Number of conflicts needed to trigger resolution

# Add these after other global variables
detection_conflicts = {}  # {gallery_id: [(timestamp, detection_id, x, y), ...]}
current_override = None  # Store current override detection_id if any

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
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    monitor_script = os.path.join(current_dir, 'monitor_detections.py')
    subprocess.Popen(['python3', monitor_script])
    print(f"Started monitor_detection.py from: {monitor_script}")

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

def check_detection_conflicts(gallery_id, detection_id, center_x, center_y):
    """
    Check if there are conflicts in detection IDs for the same gallery ID
    Returns the detection_id to track
    """
    global detection_conflicts, current_override
    current_time = time.time()
    
    # Initialize or clean old entries
    if gallery_id not in detection_conflicts:
        detection_conflicts[gallery_id] = []
    
    # Remove old entries (older than DETECTION_WINDOW)
    detection_conflicts[gallery_id] = [
        entry for entry in detection_conflicts[gallery_id]
        if current_time - entry[0] < DETECTION_WINDOW
    ]
    
    # Add new detection
    detection_conflicts[gallery_id].append((current_time, detection_id, center_x, center_y))
    
    # Check for conflicts in the current window
    recent_detections = detection_conflicts[gallery_id]
    unique_detection_ids = set(entry[1] for entry in recent_detections)
    
    # If we have conflicts and enough samples
    if len(unique_detection_ids) > 1 and len(recent_detections) >= CONFLICT_THRESHOLD:
        # Group detections by detection_id
        detection_groups = {}
        for entry in recent_detections:
            _, det_id, x, y = entry
            if det_id not in detection_groups:
                detection_groups[det_id] = []
            detection_groups[det_id].append((x, y))
        
        # Find the detection_id closest to center
        closest_id = None
        min_distance = float('inf')
        
        for det_id, positions in detection_groups.items():
            # Calculate average position for this detection_id
            avg_x = sum(x for x, _ in positions) / len(positions)
            avg_y = sum(y for y, _ in positions) / len(positions)
            
            # Calculate distance to center
            distance = ((avg_x - CENTRE_X) ** 2 + (avg_y - CENTRE_Y) ** 2) ** 0.5
            
            if distance < min_distance:
                min_distance = distance
                closest_id = det_id
        
        current_override = closest_id
        print(f"Conflict detected for Gallery ID {gallery_id}. Using closest Detection ID: {closest_id}")
        return closest_id
    
    # If no conflicts in window, clear override
    if len(unique_detection_ids) == 1 and current_override:
        print(f"Conflict resolved for Gallery ID {gallery_id}. Returning to normal tracking.")
        current_override = None
    
    return detection_id

def track_face():
    """
    Modified track_face function with conflict detection
    """
    global TARGET_GALLERY_ID
    last_offset = -1
    x_last = None
    y_last = None

    while True:
        try:
            TARGET_GALLERY_ID = get_target_face_id()
            
            latest_row = get_latest_csv_row(CSV_PATH)
            if latest_row is not None:
                timestamp_str = latest_row[0]
                offset_str = latest_row[1]
                detection_id = latest_row[2]
                gallery_id = latest_row[3]
                label = latest_row[4]
                center_x_str = latest_row[5]
                center_y_str = latest_row[6]

                if (gallery_id == TARGET_GALLERY_ID and 
                    detection_id not in [None, '', 'null'] and
                    center_x_str not in [None, '', 'null'] and
                    center_y_str not in [None, '', 'null']):
                    
                    try:
                        offset_int = int(offset_str)
                        center_x = float(center_x_str)
                        center_y = float(center_y_str)
                        
                        # Check for detection conflicts
                        tracked_detection_id = check_detection_conflicts(
                            gallery_id, detection_id, center_x, center_y)
                        
                        # Only process if this is the detection ID we want to track
                        if tracked_detection_id == detection_id:
                            if offset_int > last_offset:
                                last_offset = offset_int
                                x_last = center_x
                                y_last = center_y
                                adjust_servo_angles_using_old_logic(x_last, y_last)
                    except:
                        offset_int = -1
                        center_x, center_y = None, None
            
            time.sleep(0.01)

        except KeyboardInterrupt:
            print("\nTracking stopped by user.")
            break
        except Exception as e:
            print(f"Error reading CSV: {e}")
            time.sleep(0.1)

def cleanup_servos():
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

def get_target_face_id():
    try:
        with open('tmp/target_face.txt', 'r') as f:
            return f.read().strip()
    except:
        return '1'  # Default face ID

# Update the target face ID
TARGET_GALLERY_ID = get_target_face_id()

if __name__ == "__main__":
    main()
