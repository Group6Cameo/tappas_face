#!/usr/bin/env python3
import json
import time
import os
import threading
import subprocess
import csv
import zmq
from datetime import datetime, timedelta
from collections import deque

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# Define image dimensions and settings
IMAGE_WIDTH = 640
IMAGE_HEIGHT = 360
ENABLE_CONSOLE_PRINT = False  # Switch for console printing

RESOURCES_DIR = os.path.join(CURRENT_DIR, 'tmp')
LOG_FILE = os.path.join(RESOURCES_DIR, 'face_info_log.csv')

MAX_HISTORY_SECONDS = 5.0
MAX_ROWS = 200

# We can store the CSV header somewhere
CSV_HEADER = ['Timestamp', 'Rec_BufferSet', 'Detection_ID',
              'Gallery_ID', 'Label', 'Center_X', 'Center_Y']

class RecordManager:
    def __init__(self, max_records=200, max_age_seconds=5.0):
        self.records = deque(maxlen=max_records)  # each item is (datetime_obj, row_data_list)
        self.max_age = timedelta(seconds=max_age_seconds)
        
    def add_record(self, record):
        """Add a new record to the in-memory deque and write only that record to CSV."""
        now = datetime.now()
        self.records.append((now, record))
        
        # Append only the new record to CSV (for streaming)
        with open(LOG_FILE, 'a', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(record)
    
    def clean_old_records(self):
        """Remove records older than max_age and rewrite the CSV if something changed."""
        now = datetime.now()
        old_len = len(self.records)
        
        # Pop from the left while the oldest record is too old
        while self.records and (now - self.records[0][0]) > self.max_age:
            self.records.popleft()
        
        new_len = len(self.records)
        pruned_count = old_len - new_len
        
        # If we pruned anything, we must rewrite the CSV so disk matches memory
        if pruned_count > 0:
            print(f"Pruned {pruned_count} records")

            # Re-write CSV with only current records
            with open(LOG_FILE, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                # Optionally write header each time if you want a valid CSV
                writer.writerow(CSV_HEADER)
                # Now write the in-memory items
                for _, row_data in self.records:
                    writer.writerow(row_data)

        # Filter out 'nd' values when displaying unique IDs
        unique_ids = set(r[3] for _, r in self.records if r[3] != 'nd')
        if unique_ids:  # Only print if there are valid IDs
            print(f"Current unique Gallery IDs in memory: {unique_ids}")

def clear_file(filename):
    """Create file if it doesn't exist, clear it if it does."""
    try:
        directory = os.path.dirname(filename)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created directory: {directory}")
        
        open(filename, 'w').close()
        print(f"Cleared/Created {filename}")
    except Exception as e:
        print(f"Error handling file {filename}: {str(e)}")
        raise

def run_bash_script():
    """Run the face recognition bash script."""
    try:
        subprocess.run(['bash', 'face_recognition.sh'], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running bash script: {e}")
    except Exception as e:
        print(f"Unexpected error running bash script: {e}")

def calculate_center(bbox):
    center_x = (bbox["xmin"] + bbox["width"]/2) * IMAGE_WIDTH
    center_y = (bbox["ymin"] + bbox["height"]/2) * IMAGE_HEIGHT
    return int(center_x), int(center_y)

def get_face_info(data):
    face_info = {
        'mode0_id': None,
        'mode1_id': None,
        'label': None,
        'center_x': None,
        'center_y': None
    }
    
    try:
        if "HailoROI" in data:
            if "HailoBBox" in data["HailoROI"]:
                bbox = data["HailoROI"]["HailoBBox"]
                face_info['center_x'], face_info['center_y'] = calculate_center(bbox)
            
            for obj in data["HailoROI"].get("SubObjects", []):
                if "HailoUniqueID" in obj:
                    unique_id = obj["HailoUniqueID"]
                    if unique_id["mode"] == 0:
                        face_info['mode0_id'] = unique_id["unique_id"]
                    elif unique_id["mode"] == 1:
                        face_info['mode1_id'] = unique_id["unique_id"]
                
                if "HailoClassification" in obj:
                    classification = obj["HailoClassification"]
                    if classification["classification_type"] == "recognition_result":
                        face_info['label'] = classification["label"]
    except Exception as e:
        print(f"Error extracting face info: {str(e)}")
    
    return face_info

def monitor_zmq():
    """Monitor ZMQ socket for face recognition data."""
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect("tcp://localhost:5555")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")  # Subscribe to all topics/messages
    
    record_manager = RecordManager(max_records=MAX_ROWS, max_age_seconds=MAX_HISTORY_SECONDS)
    last_cleanup = datetime.now()
    processed_data_ids = set()
    
    # Write CSV header initially
    with open(LOG_FILE, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(CSV_HEADER)
    
    print("Starting ZMQ-based face tracking...")
    
    while True:
        try:
            # Non-blocking receive with 100ms poll
            if socket.poll(100):
                data = socket.recv_json()
                data_id = f"{data.get('timestamp (ms)', '')}_${data.get('stream_id', '')}"
                
                if data_id not in processed_data_ids:
                    face_info = get_face_info(data)
                    
                    if face_info['mode0_id'] is not None:
                        gallery_id = face_info['mode1_id'] or 'nd'
                        label = face_info['label'] or 'nd'
                        
                        row = [
                            datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'),
                            data['buffer_offset'],
                            face_info['mode0_id'],
                            gallery_id,
                            label,
                            face_info['center_x'],
                            face_info['center_y']
                        ]
                        
                        record_manager.add_record(row)
                        processed_data_ids.add(data_id)
                        
                        if ENABLE_CONSOLE_PRINT:
                            print(f"New Data - Rec BufferSet {data['buffer_offset']}: "
                                  f"DetID:{face_info['mode0_id']}, "
                                  f"GalleryID:{gallery_id}, "
                                  f"Label:{label}, "
                                  f"X:{face_info['center_x']}, "
                                  f"Y:{face_info['center_y']}")
            
            # Clean old records every 5 seconds
            now = datetime.now()
            if (now - last_cleanup).total_seconds() >= 5.0:
                record_manager.clean_old_records()
                # Optionally prune 'processed_data_ids' if too large
                if len(processed_data_ids) > MAX_ROWS * 2:
                    processed_data_ids.clear()
                last_cleanup = now
                
        except zmq.ZMQError as e:
            print(f"ZMQ error: {str(e)}")
            time.sleep(0.1)
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            time.sleep(0.1)

def main():
    clear_file(LOG_FILE)
    
    # Start face recognition script, if needed
    bash_thread = threading.Thread(target=run_bash_script, daemon=True)
    bash_thread.start()
    
    print("Monitoring ZMQ feed...")
    try:
        time.sleep(1)  # give script time to start
        monitor_zmq()
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")

if __name__ == "__main__":
    main()
