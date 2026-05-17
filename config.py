import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'my_precious_secret_key')
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    DATABASE_PATH = os.path.join(BASE_DIR, 'database', 'cheating_system.db')
    MODELS_DIR = os.path.join(BASE_DIR, 'models')
    YOLO_MODEL_PATH = os.path.join(MODELS_DIR, 'yolov8n.pt')
    EYE_MODEL_PATH = os.path.join(MODELS_DIR, 'eye_model.h5')
    HEAD_MODEL_PATH = os.path.join(MODELS_DIR, 'head_model.h5')
    SCREENSHOTS_DIR = os.path.join(BASE_DIR, 'screenshots')
    LOGS_DIR = os.path.join(BASE_DIR, 'logs')
    RESULTS_DIR = os.path.join(BASE_DIR, 'results')
    
    # Ensure dirs exist
    for d in [MODELS_DIR, SCREENSHOTS_DIR, LOGS_DIR, RESULTS_DIR, os.path.join(BASE_DIR, 'database')]:
        os.makedirs(d, exist_ok=True)
