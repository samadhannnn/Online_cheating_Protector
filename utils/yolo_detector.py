from ultralytics import YOLO
from config import Config
import cv2
import os

class YOLODetector:
    def __init__(self):
        # We assume the user has yolov8n.pt in models folder or it will be downloaded automatically
        # by ultralytics if not found at that exact path. We will pass the model name.
        if os.path.exists(Config.YOLO_MODEL_PATH):
            self.model = YOLO(Config.YOLO_MODEL_PATH)
        else:
            self.model = YOLO('yolov8n.pt') # downloads to current dir
            self.model.save(Config.YOLO_MODEL_PATH)

    def detect(self, frame):
        frame_h, frame_w = frame.shape[:2]
        frame_area = frame_h * frame_w
        # Only detect relevant classes: person (0), cell phone (67)
        results = self.model(frame, verbose=False, classes=[0, 67])
        detections = []
        person_count = 0
        phone_detected = False
        person_boxes = []

        if len(results) > 0:
            boxes = results[0].boxes
            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])
                cls = int(box.cls[0])
                label = self.model.names[cls]

                if label == 'person' and conf > 0.60:
                    bw = float(x2 - x1)
                    bh = float(y2 - y1)
                    box_area = bw * bh
                    area_ratio = box_area / frame_area

                    # Person must occupy at least 8% of frame
                    if area_ratio > 0.08:
                        is_new_person = True
                        for pbox in person_boxes:
                            px1, py1, px2, py2 = pbox
                            cx = x1 + bw/2
                            cy = y1 + bh/2
                            if px1 < cx < px2 and py1 < cy < py2:
                                is_new_person = False
                                break
                        if is_new_person:
                            person_boxes.append((x1, y1, x2, y2))
                            person_count += 1

                # Raised to 0.60 to avoid false positives from hands rubbing eyes or touching hair
                elif label == 'cell phone' and conf > 0.60:
                    phone_detected = True

                detections.append({
                    'label': label,
                    'confidence': conf,
                    'box': [int(x1), int(y1), int(x2), int(y2)]
                })

        return detections, person_count, phone_detected
