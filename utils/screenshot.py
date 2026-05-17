import cv2
import os
import time
from config import Config

def save_screenshot(frame, student_id, violation_type):
    timestamp = int(time.time())
    # Replace spaces with underscores to avoid url issues
    safe_violation = violation_type.replace(' ', '_')
    filename = f"student_{student_id}_{safe_violation}_{timestamp}.jpg"
    
    os.makedirs(Config.SCREENSHOTS_DIR, exist_ok=True)
    
    filepath = os.path.join(Config.SCREENSHOTS_DIR, filename)
    cv2.imwrite(filepath, frame)
    return filepath
