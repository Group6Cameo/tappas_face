#!/usr/bin/env python3
import json
import time
import os
import threading
import subprocess
import csv
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# Define image dimensions and settings
IMAGE_WIDTH = 640
IMAGE_HEIGHT = 360
ENABLE_CONSOLE_PRINT = False  # Switch for console printing
RESOURCES_DIR = os.path.join(CURRENT_DIR, 'tmp')
LOG_FILE = os.path.join(RESOURCES_DIR, 'face_info_log.csv')

def clear_file(filename):
    """Create file if it doesn't exist, clear it if it does"""
    try:
        # Create directory if it doesn't exist
        directory = os.path.dirname(filename)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created directory: {directory}")
        
        # Create or clear file
        open(filename, 'w').close()
        print(f"Cleared/Created {filename}")
    except Exception as e:
        print(f"Error handling file {filename}: {str(e)}")
        raise

def run_bash_script():
    """Run the face recognition bash script"""
    try:
        subprocess.run(['bash', 'face_recognition.sh'], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running bash script: {e}")
    except Exception as e:
        print(f"Unexpected error running bash script: {e}")

def calculate_center(bbox):
    """Calculate center point from bbox in pixel coordinates"""
    # Convert normalized coordinates to pixel coordinates
    center_x = (bbox["xmin"] + bbox["width"]/2) * IMAGE_WIDTH
    center_y = (bbox["ymin"] + bbox["height"]/2) * IMAGE_HEIGHT
    return int(center_x), int(center_y)

def get_face_info(data):
    """Extract face detection and recognition info from data"""
    face_info = {
        'mode0_id': None,  # Detection ID
        'mode1_id': None,  # Gallery ID
        'label': None,     # Recognition label
        'center_x': None,
        'center_y': None
    }
    
    try:
        if "HailoROI" in data:
            # Get detection bbox and center
            if "HailoBBox" in data["HailoROI"]:
                bbox = data["HailoROI"]["HailoBBox"]
                face_info['center_x'], face_info['center_y'] = calculate_center(bbox)
            
            # Get unique IDs and recognition result from SubObjects
            for obj in data["HailoROI"].get("SubObjects", []):
                # Get mode 0/1 IDs
                if "HailoUniqueID" in obj:
                    unique_id = obj["HailoUniqueID"]
                    if unique_id["mode"] == 0:
                        face_info['mode0_id'] = unique_id["unique_id"]
                    elif unique_id["mode"] == 1:
                        face_info['mode1_id'] = unique_id["unique_id"]
                
                # Get recognition label
                if "HailoClassification" in obj:
                    classification = obj["HailoClassification"]
                    if classification["classification_type"] == "recognition_result":
                        face_info['label'] = classification["label"]
    
    except Exception as e:
        print(f"Error extracting face info: {str(e)}")
    
    return face_info

def write_frame_info(frame_num, rec_buffer=None, face_info=None):
    """Helper function to write frame info to CSV"""
    if face_info is None:
        # No recognition data available, write None values
        row = [
            datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'),
            frame_num,
            'null',
            'null',
            'null',
            'null',
            'null',
            'null'
        ]
    else:
        # Write with available recognition data
        # If using copied data, mark the rec_buffer as 'cpX' where X is the original recognition buffer
        rec_buffer_str = f"cp{face_info['original_buffer']}" if rec_buffer != face_info.get('original_buffer') else (rec_buffer or 'null')
        
        # Use 'nd' for unrecognized faces (detected but not in gallery)
        gallery_id = face_info['mode1_id'] or 'nd'
        label = face_info['label'] or 'nd'
        
        row = [
            datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'),
            frame_num,
            rec_buffer_str,
            face_info['mode0_id'],
            gallery_id,
            label,
            face_info['center_x'],
            face_info['center_y']
        ]
    
    with open(LOG_FILE, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(row)
    
    if ENABLE_CONSOLE_PRINT:
        print(f"Current Frame {frame_num}, Rec BufferSet {row[2]}: "
              f"Detection_ID:{face_info['mode0_id'] if face_info else 'null'}, "
              f"Gallery_ID:{gallery_id if face_info else 'null'}, "
              f"Label:{label if face_info else 'null'}, "
              f"x:{face_info['center_x'] if face_info else 'null'}, "
              f"y:{face_info['center_y'] if face_info else 'null'}")

def monitor_files(rec_filename, det_filename):
    """Monitor both recognition and detection files"""
    processed_rec_data = set()
    current_frame = -1
    last_face_info = None  # Store last valid recognition info
    processed_frames = set()  # Track processed detection frames
    
    # Initialize CSV file with headers
    with open(LOG_FILE, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Timestamp', 'Current_Frame', 'Rec_BufferSet', 'Detection_ID', 
                        'Gallery_ID', 'Label', 'Center_X', 'Center_Y'])
    
    while True:
        try:
            # First check detection file for actual frame count
            if os.path.exists(det_filename):
                with open(det_filename, 'r') as file:
                    det_content = file.read().strip()
                    if det_content:
                        try:
                            if det_content.endswith(','):
                                det_content = '[' + det_content[:-1] + ']'
                            elif not (det_content.startswith('[') and det_content.endswith(']')):
                                det_content = '[' + det_content + ']'
                            
                            det_data_list = json.loads(det_content)
                            if det_data_list:
                                # Process each detection frame
                                for det_data in det_data_list:
                                    frame_num = det_data["buffer_offset"]
                                    if frame_num > current_frame:
                                        current_frame = frame_num
                                        if frame_num not in processed_frames:
                                            # Will process this frame with latest recognition data
                                            processed_frames.add(frame_num)
                                            write_frame_info(frame_num, frame_num, last_face_info)
                        except Exception as e:
                            print(f"Error processing detection data: {str(e)}")
            
            # Then process recognition data
            if os.path.exists(rec_filename):
                with open(rec_filename, 'r') as file:
                    rec_content = file.read().strip()
                    if rec_content:
                        try:
                            if rec_content.endswith(','):
                                rec_content = '[' + rec_content[:-1] + ']'
                            elif not (rec_content.startswith('[') and rec_content.endswith(']')):
                                rec_content = '[' + rec_content + ']'
                            
                            rec_data_list = json.loads(rec_content)
                            
                            # Get latest recognition data that hasn't been processed
                            for data in rec_data_list:
                                # Create unique identifier for this recognition data
                                data_id = f"{data['timestamp (ms)']}_{data['stream_id']}"
                                
                                if data_id not in processed_rec_data:
                                    face_info = get_face_info(data)
                                    
                                    if face_info['mode0_id'] is not None:
                                        # Store original buffer offset
                                        face_info['original_buffer'] = data['buffer_offset']
                                        # Update last valid face info
                                        last_face_info = face_info
                                        # Write frame info with new recognition data
                                        write_frame_info(current_frame, data['buffer_offset'], face_info)
                                    
                                    processed_rec_data.add(data_id)
                                        
                        except json.JSONDecodeError:
                            pass
                        except Exception as e:
                            print(f"Error processing recognition data: {str(e)}")
            
            time.sleep(0.1)
                    
        except Exception as e:
            print(f"File reading error: {str(e)}")
            time.sleep(0.1)

def main():
    rec_file = os.path.join(RESOURCES_DIR, 'face_recognition_output.json')
    det_file = os.path.join(RESOURCES_DIR, 'face_detection_output.json')
    
    # Clear all files
    clear_file(rec_file)
    clear_file(det_file)
    clear_file(LOG_FILE)
    
    # Create and start bash script thread
    bash_thread = threading.Thread(target=run_bash_script)
    bash_thread.daemon = True
    bash_thread.start()
    
    print("Starting monitoring...")
    try:
        time.sleep(1)
        monitor_files(rec_file, det_file)
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")

if __name__ == "__main__":
    main()