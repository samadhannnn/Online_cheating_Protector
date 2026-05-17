from database import get_db_connection
import csv
import os
from config import Config

import time

# Global cooldown to prevent multiple alerts from different sources (video, browser) at the same time
global_violation_cooldowns = {}

def log_violation(student_id, exam_id, violation_type, screenshot_path=None):
    current_time = time.time()
    last_time = global_violation_cooldowns.get(student_id, 0)
    
    # Strictly enforce 5 seconds cooldown at the database level
    if current_time - last_time < 5:
        return False
        
    global_violation_cooldowns[student_id] = current_time

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        'INSERT INTO violations (student_id, exam_id, violation_type, screenshot_path) VALUES (?, ?, ?, ?)',
        (student_id, exam_id, violation_type, screenshot_path)
    )
    
    # Increment session warning count
    c.execute('UPDATE sessions SET warnings_count = warnings_count + 1 WHERE student_id = ? AND exam_id = ? AND is_active = TRUE', (student_id, exam_id))
    
    # Update results warning count
    c.execute('UPDATE results SET warnings_count = warnings_count + 1 WHERE student_id = ? AND exam_id = ?', (student_id, exam_id))
    
    conn.commit()
    conn.close()
    
    # Save to CSV
    csv_path = os.path.join(Config.LOGS_DIR, 'violations.csv')
    file_exists = os.path.isfile(csv_path)
    with open(csv_path, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            writer.writerow(['student_id', 'exam_id', 'violation_type', 'screenshot_path', 'timestamp'])
        import datetime
        writer.writerow([student_id, exam_id, violation_type, screenshot_path, datetime.datetime.now().isoformat()])
