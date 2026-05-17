import sqlite3
import os
from config import Config

def get_db_connection():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Students
    c.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            roll_number TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            banned_until DATETIME DEFAULT NULL
        )
    ''')
    
    # Admins
    c.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    
    # Exams
    c.execute('''
        CREATE TABLE IF NOT EXISTS exams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            total_marks INTEGER NOT NULL
        )
    ''')
    
    # Questions
    c.execute('''
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id INTEGER,
            question_text TEXT NOT NULL,
            option_a TEXT NOT NULL,
            option_b TEXT NOT NULL,
            option_c TEXT NOT NULL,
            option_d TEXT NOT NULL,
            correct_option TEXT NOT NULL,
            FOREIGN KEY (exam_id) REFERENCES exams (id)
        )
    ''')
    
    # Results
    c.execute('''
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            exam_id INTEGER,
            score INTEGER NOT NULL,
            warnings_count INTEGER NOT NULL,
            is_disqualified BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (student_id) REFERENCES students (id),
            FOREIGN KEY (exam_id) REFERENCES exams (id)
        )
    ''')
    
    # Violations
    c.execute('''
        CREATE TABLE IF NOT EXISTS violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            exam_id INTEGER,
            violation_type TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            screenshot_path TEXT,
            FOREIGN KEY (student_id) REFERENCES students (id),
            FOREIGN KEY (exam_id) REFERENCES exams (id)
        )
    ''')
    
    # Sessions
    c.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            exam_id INTEGER,
            is_active BOOLEAN DEFAULT TRUE,
            warnings_count INTEGER DEFAULT 0,
            start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students (id),
            FOREIGN KEY (exam_id) REFERENCES exams (id)
        )
    ''')
    
    # Student Answers
    c.execute('''
        CREATE TABLE IF NOT EXISTS student_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            exam_id INTEGER,
            question_id INTEGER,
            selected_option TEXT,
            FOREIGN KEY (student_id) REFERENCES students (id),
            FOREIGN KEY (exam_id) REFERENCES exams (id),
            FOREIGN KEY (question_id) REFERENCES questions (id)
        )
    ''')
    
    conn.commit()
    
    # Insert default admin if not exists
    c.execute('SELECT * FROM admins WHERE username="admin"')
    if not c.fetchone():
        c.execute('INSERT INTO admins (username, password) VALUES (?, ?)', ('admin', 'admin123'))
        
    # Insert mock exams if not exists
    c.execute('SELECT * FROM exams')
    if not c.fetchall():
        mock_exams = [
            ('C Programming', 10, 20),
            ('C++', 10, 20),
            ('Java', 10, 20),
            ('Python', 10, 20),
            ('Machine Learning', 10, 20)
        ]
        c.executemany('INSERT INTO exams (title, duration_minutes, total_marks) VALUES (?, ?, ?)', mock_exams)
        conn.commit()
        
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully.")
