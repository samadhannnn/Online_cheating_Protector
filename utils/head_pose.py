import cv2
import numpy as np
import tensorflow as tf
from config import Config
import os

class HeadPoseEstimator:
    def __init__(self):
        self.model = None
        if os.path.exists(Config.HEAD_MODEL_PATH):
            try:
                self.model = tf.keras.models.load_model(Config.HEAD_MODEL_PATH)
            except:
                pass
                
        self.classes = ['center', 'left', 'right', 'down', 'up']

    def predict(self, face_roi):
        if self.model is None or face_roi is None or face_roi.size == 0:
            return "center"
            
        try:
            img = cv2.resize(face_roi, (224, 224))
            img = img / 255.0
            img = np.expand_dims(img, axis=0)
            
            preds = self.model.predict(img, verbose=0)
            class_idx = np.argmax(preds[0])
            return self.classes[class_idx]
        except:
            return "center"
