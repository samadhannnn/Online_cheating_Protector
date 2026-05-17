# ProctorAI - Online Cheating Protector

A complete end-to-end production-level AI-powered online examination proctoring system.

## Features
- **Student Portal**: Secure login, dynamic exam interface, live webcam feed, real-time warnings.
- **Admin Dashboard**: Live real-time streaming of all active candidates, session termination.
- **AI Models**: YOLOv8 for mobile phone and multiple persons detection. Custom CNNs for eye tracking and head pose estimation. MediaPipe for face detection.
- **Cheating Detection**: Mobile phone usage, multiple persons, looking away, suspicious head/eye movements, browser tab switching, fullscreen exit.
- **Auto Submission**: Automatically disqualifies and submits exams with 0 marks after 5 warnings.
- **Production Ready**: WebSockets for real-time low latency streaming, Render deployment configuration, SQLite database, premium Tailwind UI.

## Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the application:
   ```bash
   python app.py
   ```
   Or using gunicorn:
   ```bash
   gunicorn --worker-class eventlet -w 1 app:app
   ```

## Render / Docker Deployment
This project is configured with a custom `Dockerfile` containing all heavy system dependencies required by OpenCV and AI processing. 
To deploy, simply link your GitHub to Render, create a New Web Service, and select **Docker** as the Environment. 

## Default Credentials
- **Admin**: Username: `admin`, Password: `admin123`
- **Student**: Register via the portal.
