import time
import csv
import subprocess
import threading
import os
from adafruit_servokit import ServoKit

# Initialize servo kit
kit = ServoKit(channels=16)

# Set servo pulse width ranges
kit.servo[0].set_pulse_width_range(400, 2600)
kit.servo[1].set_pulse_width_range(400, 2600)

# Initialize servo positions to center
kit.servo[0].angle = 120  # Vertical (up/down)
kit.servo[1].angle = 95  # Horizontal (left/right)

# Constants
IMAGE_WIDTH = 640
IMAGE_HEIGHT = 360
CENTER_X = IMAGE_WIDTH // 2
CENTER_Y = IMAGE_HEIGHT // 2

# Rectangular deadzone
DEADZONE_WIDTH = 120
DEADZONE_HEIGHT = 30
CSV_PATH = 'tmp/face_info_log.csv'

# Current angles
current_vertical_angle = 120
current_horizontal_angle = 95

def start_monitor_detection():
    """Start the monitor_detection.py script"""
    subprocess.Popen(['python3', 'monitor_detections.py'])

def adjust_servo_angles(target_x, target_y):
    global current_vertical_angle, current_horizontal_angle
    
    # Calculate offsets from center
    x_offset = target_x - CENTER_X
    y_offset = target_y - CENTER_Y
    
    # Define deadzone boundaries
    deadzone_left = CENTER_X - DEADZONE_WIDTH//2
    deadzone_right = CENTER_X + DEADZONE_WIDTH//2
    deadzone_top = CENTER_Y - DEADZONE_HEIGHT//2
    deadzone_bottom = CENTER_Y + DEADZONE_HEIGHT//2
    
    # Adjust horizontal angle if target is outside horizontal deadzone
    if target_x < deadzone_left or target_x > deadzone_right:
        # Move right: increase angle, Move left: decrease angle
        adjustment = 0.3 if x_offset > 0 else -0.3
        new_horizontal = current_horizontal_angle + adjustment
        if 0 <= new_horizontal <= 180:
            current_horizontal_angle = new_horizontal
            kit.servo[1].angle = current_horizontal_angle

    # Adjust vertical angle if target is outside vertical deadzone
    if target_y < deadzone_top or target_y > deadzone_bottom:
        # Move up: decrease angle, Move down: increase angle
        adjustment = 0.3 if y_offset > 0 else -0.3
        new_vertical = current_vertical_angle + adjustment
        if 0 <= new_vertical <= 180:
            current_vertical_angle = new_vertical
            kit.servo[0].angle = current_vertical_angle

def track_face():
    """Main tracking loop"""
    last_processed_line = 0
    
    while True:
        try:
            with open(CSV_PATH, 'r') as file:
                csv_reader = csv.DictReader(file)
                rows = list(csv_reader)
                
                # Process only new rows
                if len(rows) > last_processed_line:
                    for row in rows[last_processed_line:]:
                        # Only track if we have valid coordinates and Gallery_ID is 1
                        if (row['Gallery_ID'] == '1' and 
                            row['Center_X'] != 'null' and 
                            row['Center_Y'] != 'null'):
                            
                            target_x = int(float(row['Center_X']))
                            target_y = int(float(row['Center_Y']))
                            adjust_servo_angles(target_x, target_y)
                    
                    last_processed_line = len(rows)
                
                time.sleep(0.05)  # Small delay to prevent CPU overload
                
        except FileNotFoundError:
            print("Waiting for CSV file...")
            time.sleep(1)
        except Exception as e:
            print(f"Error reading CSV: {e}")
            time.sleep(1)

def main():
    # Start monitor_detection.py
    start_monitor_detection()
    print("Started monitor_detection.py")
    
    # Wait for CSV file to be created
    time.sleep(2)
    
    print("Starting face tracking...")
    try:
        track_face()
    except KeyboardInterrupt:
        print("\nTracking stopped.")
        # Center servos before exit
        kit.servo[0].angle = 120
        kit.servo[1].angle = 95

if __name__ == "__main__":
    main()