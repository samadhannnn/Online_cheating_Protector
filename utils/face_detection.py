import cv2
import os

class FaceDetector:
    def __init__(self):
        # Use OpenCV's built-in Haar cascade for face detection
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        self.face_cascade = cv2.CascadeClassifier(cascade_path)

    def detect(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # Detect faces
        faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(20, 20))
        
        # Convert to list of tuples (x, y, w, h)
        return [(int(x), int(y), int(w), int(h)) for (x, y, w, h) in faces]

