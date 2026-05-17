import cv2
from utils.yolo_detector import YOLODetector
from utils.face_detection import FaceDetector
from utils.screenshot import save_screenshot
from utils.logger import log_violation
import time

class VideoProcessor:
    def __init__(self):
        self.yolo = YOLODetector()
        self.face_detector = FaceDetector()
        self.last_violation_time = {}
        self.start_times = {}
        # Per-student consecutive "looking away" counter for head/eye violations
        self.look_away_counter = {}
        # Caches for throttling AI inference
        self.last_check_time = {}
        self.last_detections = {}
        self.last_faces = {}
        self.last_person_count = {}
        self.last_phone_detected = {}
        self.face_missing_start = {}

    def process_frame(self, frame, student_id, exam_id):
        # Resize frame for faster processing (keep original for output)
        small = cv2.resize(frame, (320, 240))
        scale_x = frame.shape[1] / 320
        scale_y = frame.shape[0] / 240

        current_time = time.time()
        last_check = self.last_check_time.get(student_id, 0)
        
        if current_time - last_check > 0.5:
            # 1. YOLO Detection on small frame
            detections, person_count, phone_detected = self.yolo.detect(small)

            # 2. Face Detection on small frame
            faces = self.face_detector.detect(small)
            
            self.last_check_time[student_id] = current_time
            self.last_detections[student_id] = detections
            self.last_faces[student_id] = faces
            self.last_person_count[student_id] = person_count
            self.last_phone_detected[student_id] = phone_detected
        else:
            detections = self.last_detections.get(student_id, [])
            faces = self.last_faces.get(student_id, [])
            person_count = self.last_person_count.get(student_id, 1)
            phone_detected = self.last_phone_detected.get(student_id, False)

        violation = None

        if phone_detected:
            violation = "Mobile Phone Detected"
        elif person_count > 1:
            violation = "Multiple Persons Detected"
        elif len(faces) == 0:
            # Face not visible, but only warn if it's missing for > 2.5 seconds (prevents rubbing eyes false positive)
            if student_id not in self.face_missing_start:
                self.face_missing_start[student_id] = current_time
            elif current_time - self.face_missing_start[student_id] > 2.5:
                violation = "Face Not Visible"
        else:
            if student_id in self.face_missing_start:
                del self.face_missing_start[student_id]
            # Face is present — clear look-away counter
            self.look_away_counter[student_id] = 0

        # Draw YOLO detections (scaled back to original frame)
        for det in detections:
            bx1, by1, bx2, by2 = det['box']
            bx1 = int(bx1 * scale_x); bx2 = int(bx2 * scale_x)
            by1 = int(by1 * scale_y); by2 = int(by2 * scale_y)
            label = f"{det['label']} {det['confidence']:.0%}"
            color = (0, 50, 255) if det['label'] == 'cell phone' else (255, 100, 0)
            cv2.rectangle(frame, (bx1, by1), (bx2, by2), color, 2)
            cv2.putText(frame, label, (bx1, max(by1 - 8, 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # Draw face box (scaled)
        if faces:
            x, y, w, h = faces[0]
            x = int(x * scale_x); y = int(y * scale_y)
            w = int(w * scale_x); h = int(h * scale_y)
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 220, 80), 2)
            cv2.putText(frame, "Face OK", (x, max(y - 8, 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 80), 2)

        # Ensure current_time is defined if we removed it from below

        # Grace period tracking
        if student_id not in self.start_times:
            self.start_times[student_id] = current_time

        # 12-second grace period for "Face Not Visible" (camera warm-up)
        if violation == "Face Not Visible" and (current_time - self.start_times[student_id] < 12):
            violation = None

        # Cooldown: only log a violation once every 7 seconds per student
        last_time = self.last_violation_time.get(student_id, 0)
        if violation and (current_time - last_time > 7):
            self.last_violation_time[student_id] = current_time
            filepath = save_screenshot(frame, student_id, violation)
            is_logged = log_violation(student_id, exam_id, violation, filepath)
            if is_logged is False:
                return frame, None
            # Draw warning overlay on frame
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 0), (frame.shape[1], 50), (0, 0, 200), -1)
            cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
            cv2.putText(frame, f"! WARNING: {violation}", (10, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
            return frame, violation

        return frame, None
