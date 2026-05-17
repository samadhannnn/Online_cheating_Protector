import os
import cv2
import base64
import time
from datetime import datetime
import numpy as np
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory
from flask_socketio import SocketIO, emit, join_room
from config import Config
from database import get_db_connection, init_db
from utils.streaming import VideoProcessor

app = Flask(__name__)
app.config.from_object(Config)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# Automatically initialize database on startup (crucial for Docker/Render deployments)
init_db()

processor = VideoProcessor()

@app.route('/screenshots/<path:filename>')
def serve_screenshot(filename):
    return send_from_directory(Config.SCREENSHOTS_DIR, filename)

def send_automated_email(student_id, exam_id, violation_text):
    with app.app_context():
        conn = get_db_connection()
        student = conn.execute('SELECT email, full_name FROM students WHERE id = ?', (student_id,)).fetchone()
        exam = conn.execute('SELECT title FROM exams WHERE id = ?', (exam_id,)).fetchone()
        violation = conn.execute('SELECT screenshot_path FROM violations WHERE student_id = ? AND exam_id = ? AND screenshot_path IS NOT NULL ORDER BY timestamp DESC LIMIT 1', (student_id, exam_id)).fetchone()
        res = conn.execute('SELECT warnings_count, is_disqualified FROM results WHERE student_id = ? AND exam_id = ?', (student_id, exam_id)).fetchone()
        warnings = res['warnings_count'] if res else 0
        is_disqualified = res['is_disqualified'] if res else False
        conn.close()
        
        if not student:
            return
            
        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            from email.mime.image import MIMEImage
            import os
            
            SENDER_EMAIL = "samadhanbodkhe222@gmail.com"
            SENDER_PASSWORD = "fbfe xrpc nspq lrwh"
            
            msg = MIMEMultipart()
            msg['From'] = SENDER_EMAIL
            msg['To'] = student['email']
            if is_disqualified or warnings >= 5:
                msg['Subject'] = f"NOTICE OF DISQUALIFICATION & 24-HOUR BAN - {exam['title']}"
                body = f"""Dear {student['full_name']},
                
This is an official notice from ProctorAI. You have repeatedly violated the examination rules during your {exam['title']} exam.

You have received {warnings} warnings. Because you reached the maximum allowed limit of 5 warnings:
1. Your exam has been forcefully terminated.
2. Your score has been automatically reduced to ZERO.
3. YOUR ACCOUNT IS NOW BANNED FOR 24 HOURS. You will not be able to access any further examinations until the ban expires.

Please find the attached photographic proof taken by the AI system of your latest violation: {violation_text}.

Regards,
ProctorAI Admin Team"""
            elif warnings == 4:
                msg['Subject'] = f"FINAL WARNING: ONE STRIKE AWAY FROM 24-HOUR BAN - {exam['title']}"
                body = f"""Dear {student['full_name']},
                
This is your FINAL WARNING from ProctorAI. You have been flagged for cheating during your {exam['title']} exam.

Current Warnings: 4/5
Violation: {violation_text}

WARNING: If you receive ONE MORE warning (Warning 5), your exam will be automatically terminated, your score will become ZERO, and your account will be BANNED for 24 hours. Stop this behavior immediately!

Please find the attached photographic proof taken by the AI system.

Regards,
ProctorAI Admin Team"""
            else:
                msg['Subject'] = f"WARNING {warnings}/5: Academic Violation Flagged - {exam['title']}"
                body = f"""Dear {student['full_name']},
                
This is an official WARNING from ProctorAI. You have been flagged for cheating during your {exam['title']} exam.

Current Warnings: {warnings}/5
Violation: {violation_text}

WARNING: DO NOT do this again! If you continue this behavior and reach 5 warnings, your exam will be automatically terminated, your score will become ZERO, and you will be BANNED for 24 hours.

Please find the attached photographic proof taken by the AI system.

Regards,
ProctorAI Admin Team"""

            msg.attach(MIMEText(body, 'plain'))
            
            if violation and violation['screenshot_path'] and os.path.exists(violation['screenshot_path']):
                with open(violation['screenshot_path'], 'rb') as f:
                    img_data = f.read()
                image = MIMEImage(img_data, name=os.path.basename(violation['screenshot_path']))
                msg.attach(image)
                
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
            server.quit()
        except Exception as e:
            print("Failed to send automated email:", str(e))

@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/student/register', methods=['GET', 'POST'])
def student_register():
    if request.method == 'POST':
        full_name = request.form['full_name']
        email = request.form['email']
        roll_number = request.form['roll_number']
        password = request.form['password']
        
        conn = get_db_connection()
        c = conn.cursor()
        try:
            c.execute('INSERT INTO students (full_name, email, roll_number, password) VALUES (?, ?, ?, ?)',
                      (full_name, email, roll_number, password))
            conn.commit()
            return redirect(url_for('student_login'))
        except:
            return "Registration failed. Email or Roll number may already exist."
        finally:
            conn.close()
            
    return render_template('student_login.html', register=True)

@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db_connection()
        student = conn.execute('SELECT * FROM students WHERE email = ? AND password = ?', (email, password)).fetchone()
        conn.close()
        
        if student:
            session['student_id'] = student['id']
            session['student_name'] = student['full_name']
            return redirect(url_for('student_dashboard'))
        else:
            return "Invalid credentials"
            
    return render_template('student_login.html', register=False)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        admin = conn.execute('SELECT * FROM admins WHERE username = ? AND password = ?', (username, password)).fetchone()
        conn.close()
        
        if admin:
            session['admin_id'] = admin['id']
            return redirect(url_for('admin_dashboard'))
        else:
            return "Invalid admin credentials"
            
    return render_template('admin_login.html')

@app.route('/student/dashboard')
def student_dashboard():
    if 'student_id' not in session:
        return redirect(url_for('student_login'))
        
    conn = get_db_connection()
    is_banned = conn.execute("SELECT (banned_until IS NOT NULL AND banned_until > datetime('now')) as banned FROM students WHERE id = ?", (session['student_id'],)).fetchone()['banned']
    
    exams = conn.execute('SELECT * FROM exams').fetchall()
    results = conn.execute('SELECT exam_id FROM results WHERE student_id = ?', (session['student_id'],)).fetchall()
    completed_exam_ids = [r['exam_id'] for r in results]
    conn.close()
    
    return render_template('student_dashboard.html', exams=exams, completed_exam_ids=completed_exam_ids, is_banned=bool(is_banned))

@app.route('/exam/start/<int:exam_id>')
def start_exam(exam_id):
    if 'student_id' not in session:
        return redirect(url_for('student_login'))
        
    student_id = session['student_id']
    
    conn = get_db_connection()
    c = conn.cursor()
    
    # Init session
    c.execute('INSERT INTO sessions (student_id, exam_id) VALUES (?, ?)', (student_id, exam_id))
    # Init result if not exists
    res = c.execute('SELECT * FROM results WHERE student_id = ? AND exam_id = ?', (student_id, exam_id)).fetchone()
    if not res:
        c.execute('INSERT INTO results (student_id, exam_id, score, warnings_count) VALUES (?, ?, 0, 0)', (student_id, exam_id))
    
    exam = c.execute('SELECT * FROM exams WHERE id = ?', (exam_id,)).fetchone()
    questions = c.execute('SELECT * FROM questions WHERE exam_id = ?', (exam_id,)).fetchall()
    
    # Ensure we have a pool of 20 questions, pick 10 randomly
    if len(questions) < 20:
        c.execute('DELETE FROM questions WHERE exam_id = ?', (exam_id,))
        dummy_questions = []
        if 'C Programming' in exam['title']:
            dummy_questions = [
                ('Who is the father of C language?', 'Steve Jobs', 'James Gosling', 'Dennis Ritchie', 'Rasmus Lerdorf', 'C'),
                ('Which keyword is used to prevent any changes in the variable?', 'immutable', 'mutable', 'const', 'volatile', 'C'),
                ('What is the size of an int data type in C?', 'Depends on compiler', '4 Bytes', '8 Bytes', '2 Bytes', 'A'),
                ('Which function is used to read formatted input from stdin?', 'printf()', 'scanf()', 'read()', 'input()', 'B'),
                ('What is a pointer in C?', 'A variable that stores address of another variable', 'A keyword', 'A function', 'An array', 'A'),
                ('Which loop guarantees execution at least once?', 'for', 'while', 'do-while', 'None', 'C'),
                ('What is the correct syntax to declare an array in C?', 'int array;', 'int array[10];', 'array[10] int;', 'int array()', 'B'),
                ('Which operator is used to access structure members?', '.', '->', '*', '&', 'A'),
                ('What does the sizeof operator return?', 'Size in bits', 'Size in bytes', 'Size in nibbles', 'Size in words', 'B'),
                ('Which header file is required for printf()?', 'math.h', 'string.h', 'stdio.h', 'stdlib.h', 'C'),
                ('Which of the following is not a valid C variable name?', 'int number;', 'float rate;', 'int variable_count;', 'int $main;', 'D'),
                ('What is short int in C programming?', 'The basic data type of C', 'Qualifier', 'Short is the qualifier and int is the basic data type', 'All of the mentioned', 'C'),
                ('What is the result of logical or relational expression in C?', 'True or False', '0 or 1', '0 if an expression is false and any positive number if an expression is true', 'None of the mentioned', 'B'),
                ('What is an array in C language?', 'A group of elements of same data type', 'An array contains more than one element', 'Array elements are stored in memory in continuous or contiguous locations', 'All of the mentioned', 'D'),
                ('What does an array name signify in C?', 'Value of the first element', 'Address of the first element', 'Address of the last element', 'Value of the last element', 'B'),
                ('How are String represented in memory in C?', 'An array of characters', 'The object of some class', 'Same as other primitive data types', 'LinkedList of characters', 'A'),
                ('Which of the following is an exit controlled loop?', 'While loop', 'For loop', 'do-while loop', 'None of the above', 'C'),
                ('What is the use of the break statement?', 'To exit a loop', 'To continue to the next iteration', 'To jump to a specific label', 'None of the above', 'A'),
                ('Which keyword is used to define a macro in C?', 'macro', 'define', '#define', 'None of the above', 'C'),
                ('What is the default return type of main() in C?', 'void', 'int', 'float', 'char', 'B')
            ]
        elif 'C++' in exam['title']:
            dummy_questions = [
                ('Who developed C++?', 'Dennis Ritchie', 'Bjarne Stroustrup', 'Ken Thompson', 'Brian Kernighan', 'B'),
                ('Which principle is NOT part of OOP?', 'Encapsulation', 'Compilation', 'Inheritance', 'Polymorphism', 'B'),
                ('What does cout stand for?', 'character output', 'computer output', 'common output', 'console output', 'A'),
                ('Which symbol is used for a single line comment?', '//', '/*', '<!--', '#', 'A'),
                ('What is the correct way to inherit a class in C++?', 'class A : class B', 'class A extends B', 'class A : public B', 'class A inherits B', 'C'),
                ('Which of the following is a scope resolution operator?', '.', ':', '::', '->', 'C'),
                ('Can a class have multiple constructors?', 'Yes', 'No', 'Only two', 'Depends on compiler', 'A'),
                ('What is a virtual function?', 'A function with no body', 'A function redefined in a derived class', 'A private function', 'A static function', 'B'),
                ('Which access specifier makes members accessible only within the class?', 'public', 'protected', 'private', 'internal', 'C'),
                ('What does new operator do?', 'Allocates memory on stack', 'Allocates memory on heap', 'Deletes memory', 'Copies memory', 'B'),
                ('Which of the following is used for comments in C++?', '/* comment */', '// comment', 'both // comment or /* comment */', '// comment */', 'C'),
                ('What is the difference between delete and delete[] in C++?', 'delete is syntactically correct but delete[] is wrong', 'delete is used to delete normal objects whereas delete[] is used to pointer objects', 'delete is used to delete single object whereas delete[] is used to array of objects', 'delete is a keyword whereas delete[] is an identifier', 'C'),
                ('What happens if the following program is executed in C and C++? int main() { void *ptr; int *p = ptr; return 0; }', 'Error in C and successful execution in C++', 'Error in both C and C++', 'Error in C++ and successful execution in C', 'Successful execution in both C and C++', 'C'),
                ('What is a template in C++?', 'A template is a formula for creating a generic class or function', 'A template is used to manipulate templates', 'A template is a keyword', 'A template is an object', 'A'),
                ('Which of the following approach is used by C++?', 'Left-right', 'Right-left', 'Bottom-up', 'Top-down', 'C'),
                ('What is a pure virtual function?', 'A function with no body', 'A virtual function equated to zero', 'A static virtual function', 'A private virtual function', 'B'),
                ('Which of the following is not a type of inheritance in C++?', 'Multiple', 'Multilevel', 'Hierarchical', 'Distributed', 'D'),
                ('What is the default access specifier for a class in C++?', 'public', 'private', 'protected', 'internal', 'B'),
                ('What is the use of the friend keyword in C++?', 'To declare a friend class', 'To declare a friend function', 'Both A and B', 'None of the above', 'C'),
                ('Which operator cannot be overloaded in C++?', '+', '-', '*', '::', 'D')
            ]
        elif 'Java' in exam['title']:
            dummy_questions = [
                ('Which company created Java?', 'Microsoft', 'Apple', 'Sun Microsystems', 'Google', 'C'),
                ('What is the size of boolean variable?', '8 bit', '16 bit', '32 bit', '1 bit', 'D'),
                ('What is the default value of local variables?', 'null', '0', 'Depends on data type', 'Not assigned', 'D'),
                ('Which method is the entry point for any Java program?', 'start()', 'main()', 'init()', 'run()', 'B'),
                ('Which keyword is used to inherit a class?', 'implements', 'extends', 'inherits', 'super', 'B'),
                ('What does JVM stand for?', 'Java Variable Machine', 'Java Virtual Machine', 'Java Visual Machine', 'Java Verified Machine', 'B'),
                ('Is Java purely object oriented?', 'Yes', 'No', 'Partially', 'Depends', 'B'),
                ('Which class is the superclass of all classes in Java?', 'Object', 'String', 'Main', 'System', 'A'),
                ('What is the use of final keyword?', 'To prevent modification', 'To make it last', 'To clean memory', 'None', 'A'),
                ('Which package is automatically imported in all Java programs?', 'java.util', 'java.io', 'java.lang', 'java.net', 'C'),
                ('What is a correct syntax to output "Hello World" in Java?', 'System.out.println("Hello World");', 'echo("Hello World");', 'Console.WriteLine("Hello World");', 'print ("Hello World");', 'A'),
                ('Java is short for "JavaScript".', 'True', 'False', 'Sometimes', 'None of the above', 'B'),
                ('How do you insert comments in Java code?', '// This is a comment', '/* This is a comment', '# This is a comment', '<!-- This is a comment -->', 'A'),
                ('Which data type is used to create a variable that should store text?', 'String', 'myString', 'Txt', 'string', 'A'),
                ('How do you create a variable with the numeric value 5?', 'num x = 5', 'float x = 5;', 'int x = 5;', 'x = 5;', 'C'),
                ('How do you create a variable with the floating number 2.8?', 'int x = 2.8;', 'float x = 2.8f;', 'byte x = 2.8', 'x = 2.8f;', 'B'),
                ('Which method can be used to find the length of a string?', 'getSize()', 'length()', 'len()', 'getLength()', 'B'),
                ('Which operator is used to add together two values?', 'The + sign', 'The & sign', 'The * sign', 'The / sign', 'A'),
                ('The value of a string variable can be surrounded by single quotes.', 'True', 'False', 'Depends on compiler', 'None of the above', 'B'),
                ('Which keyword is used to create a class in Java?', 'MyClass', 'class', 'class()', 'className', 'B')
            ]
        elif 'Python' in exam['title']:
            dummy_questions = [
                ('Which keyword is used to define a function in Python?', 'func', 'def', 'function', 'define', 'B'),
                ('What is the output of 3 ** 2?', '6', '9', '32', 'Error', 'B'),
                ('Is Python case-sensitive?', 'Yes', 'No', 'Only in Windows', 'Only in Mac', 'A'),
                ('Which data type is mutable?', 'Tuple', 'String', 'List', 'Integer', 'C'),
                ('What does len() do?', 'Finds the length', 'Converts to list', 'Deletes item', 'Sorts item', 'A'),
                ('Which of these is a dictionary?', '[1, 2]', '(1, 2)', '{1, 2}', '{"a": 1, "b": 2}', 'D'),
                ('How do you insert comments in Python?', '//', '/*', '<!--', '#', 'D'),
                ('What is a lambda function?', 'A multi-line function', 'An anonymous inline function', 'A built-in module', 'A class', 'B'),
                ('Which operator is used for floor division?', '/', '//', '%', '**', 'B'),
                ('What is the file extension for Python files?', '.pt', '.pyth', '.py', '.p', 'C'),
                ('What is the maximum possible length of an identifier in Python?', '31 characters', '63 characters', '79 characters', 'None of the above', 'D'),
                ('Who developed Python Programming Language?', 'Wick van Rossum', 'Rasmus Lerdorf', 'Guido van Rossum', 'Niene Stom', 'C'),
                ('Which type of Programming does Python support?', 'object-oriented programming', 'structured programming', 'functional programming', 'all of the mentioned', 'D'),
                ('Is Python code compiled or interpreted?', 'Python code is both compiled and interpreted', 'Python code is neither compiled nor interpreted', 'Python code is only compiled', 'Python code is only interpreted', 'A'),
                ('Which of the following is used to define a block of code in Python language?', 'Indentation', 'Key', 'Brackets', 'All of the mentioned', 'A'),
                ('Which keyword is used for function in Python language?', 'Function', 'Def', 'Fun', 'Define', 'B'),
                ('Which of the following character is used to give single-line comments in Python?', '//', '#', '!', '/*', 'B'),
                ('What will be the output of the following Python code? print("abc.DEF".capitalize())', 'Abc.def', 'abc.def', 'ABC.DEF', 'Abc.Def', 'A'),
                ('Which of the following declarations is incorrect?', '_x = 2', '__x = 3', '__xyz__ = 5', 'None of these', 'D'),
                ('What is the output of math.ceil(3.4)?', '3', '4', '4.0', '3.0', 'B')
            ]
        else: # Default or ML
            dummy_questions = [
                ('What is supervised learning?', 'Learning without labels', 'Learning with labeled data', 'Learning from environment', 'Learning from scratch', 'B'),
                ('Which is a classification algorithm?', 'Linear Regression', 'Logistic Regression', 'K-Means', 'PCA', 'B'),
                ('What does SVM stand for?', 'Simple Vector Machine', 'Support Vector Machine', 'System Vector Machine', 'Standard Vector Machine', 'B'),
                ('What is overfitting?', 'Model learns too well including noise', 'Model fails to learn', 'Model is too simple', 'Model is just right', 'A'),
                ('Which metric is used for regression models?', 'Accuracy', 'Precision', 'MSE', 'Recall', 'C'),
                ('What is the purpose of cross-validation?', 'To train faster', 'To evaluate model generalization', 'To clean data', 'To increase data size', 'B'),
                ('What is a decision tree?', 'A flowchart-like tree structure', 'A neural network', 'A clustering algorithm', 'A database', 'A'),
                ('Which algorithm is used for clustering?', 'Random Forest', 'KNN', 'K-Means', 'Naive Bayes', 'C'),
                ('What does PCA do?', 'Increases dimensions', 'Reduces dimensions', 'Classifies data', 'Predicts values', 'B'),
                ('What is a hyperparameter?', 'A parameter learned by the model', 'A parameter set before training', 'A type of data', 'An output value', 'B'),
                ('Which of the following is a type of Reinforcement Learning?', 'Q-Learning', 'Linear Regression', 'Decision Tree', 'K-Means', 'A'),
                ('What is the main objective of unsupervised learning?', 'Predict target variable', 'Find hidden patterns in data', 'Classify data', 'Reinforce good actions', 'B'),
                ('Which algorithm is mainly used for Natural Language Processing?', 'CNN', 'RNN/LSTM', 'SVM', 'K-Means', 'B'),
                ('What is a confusion matrix?', 'A matrix used for clustering', 'A table used to evaluate classification performance', 'A type of neural network layer', 'A regularization technique', 'B'),
                ('Which technique is used to prevent overfitting in neural networks?', 'Dropout', 'Increasing learning rate', 'Decreasing data size', 'Removing hidden layers', 'A'),
                ('What is backpropagation?', 'Forward pass of data', 'Algorithm to calculate gradients for weight updates', 'A type of activation function', 'A clustering method', 'B'),
                ('What is the learning rate in Gradient Descent?', 'The number of epochs', 'The size of steps taken towards the minimum', 'The batch size', 'The number of layers', 'B'),
                ('Which activation function outputs values between 0 and 1?', 'ReLU', 'Tanh', 'Sigmoid', 'Linear', 'C'),
                ('What does CNN stand for?', 'Convolutional Neural Network', 'Complex Neural Network', 'Computer Neural Network', 'Central Neural Network', 'A'),
                ('What is one-hot encoding?', 'A method to convert categorical variables into binary vectors', 'A scaling technique', 'A type of regularization', 'A dimensionality reduction technique', 'A')
            ]
            
        c.executemany('INSERT INTO questions (exam_id, question_text, option_a, option_b, option_c, option_d, correct_option) VALUES (?, ?, ?, ?, ?, ?, ?)', 
                      [(exam_id, *q) for q in dummy_questions])
                      
    # Assign 10 questions to the student if not already assigned
    existing_answers = c.execute('SELECT question_id FROM student_answers WHERE student_id = ? AND exam_id = ?', (student_id, exam_id)).fetchall()
    
    if existing_answers:
        q_ids = [str(r['question_id']) for r in existing_answers]
        placeholders = ','.join('?' * len(q_ids))
        questions = c.execute(f'SELECT * FROM questions WHERE id IN ({placeholders})', q_ids).fetchall()
    else:
        questions = c.execute('SELECT * FROM questions WHERE exam_id = ? ORDER BY RANDOM() LIMIT 10', (exam_id,)).fetchall()
        for q in questions:
            c.execute('INSERT INTO student_answers (student_id, exam_id, question_id, selected_option) VALUES (?, ?, ?, ?)', (student_id, exam_id, q['id'], ''))
        
    conn.commit()
    
    # Create or get session
    session_rec = c.execute('SELECT * FROM sessions WHERE student_id = ? AND exam_id = ?', (student_id, exam_id)).fetchone()
    
    if not session_rec:
        c.execute('INSERT INTO sessions (student_id, exam_id) VALUES (?, ?)', (student_id, exam_id))
        conn.commit()
        session_rec = c.execute('SELECT * FROM sessions WHERE student_id = ? AND exam_id = ?', (student_id, exam_id)).fetchone()
        
    # Calculate true remaining time to prevent infinite time via refresh exploit
    start_time_str = session_rec['start_time']
    try:
        start_time = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        remaining_seconds = max(0, int((exam['duration_minutes'] * 60) - elapsed))
    except Exception:
        remaining_seconds = exam['duration_minutes'] * 60
        
    # Notify admin dashboard dynamically
    student = c.execute('SELECT full_name, roll_number FROM students WHERE id = ?', (student_id,)).fetchone()
    if student:
        socketio.emit('new_student_joined', {
            'student_id': student_id,
            'exam_id': exam_id,
            'full_name': student['full_name'],
            'roll_number': student['roll_number'],
            'title': exam['title'],
            'warnings_count': session_rec['warnings_count']
        }, room='admin_room', namespace='/')
        
    conn.close()
    
    return render_template('exam_dashboard.html', exam=exam, questions=questions, student_id=student_id, remaining_seconds=remaining_seconds)

@app.route('/admin/analytics')
def admin_analytics():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
        
    conn = get_db_connection()
    
    total_students = conn.execute('SELECT COUNT(*) as count FROM students').fetchone()['count']
    total_violations = conn.execute('SELECT COUNT(*) as count FROM violations').fetchone()['count']
    total_disqualified = conn.execute('SELECT COUNT(*) as count FROM results WHERE is_disqualified = TRUE').fetchone()['count']
    
    recent_violations = conn.execute('''
        SELECT v.violation_type, v.timestamp, s.full_name, e.title
        FROM violations v
        JOIN students s ON v.student_id = s.id
        JOIN exams e ON v.exam_id = e.id
        ORDER BY v.timestamp DESC LIMIT 10
    ''').fetchall()
    
    student_records = conn.execute('''
        SELECT r.student_id, r.exam_id, s.full_name, s.roll_number, s.email, e.title, r.score, r.warnings_count, r.is_disqualified, (s.banned_until IS NOT NULL AND s.banned_until > datetime('now')) as is_banned
        FROM results r
        JOIN students s ON r.student_id = s.id
        JOIN exams e ON r.exam_id = e.id
        ORDER BY r.id DESC
    ''').fetchall()
    
    conn.close()
    
    return render_template('analytics.html', 
                           total_students=total_students, 
                           total_violations=total_violations, 
                           total_disqualified=total_disqualified,
                           recent_violations=recent_violations,
                           student_records=student_records)

@app.route('/admin/screenshots')
def admin_screenshots():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
        
    conn = get_db_connection()
    violations = conn.execute('''
        SELECT v.id, v.violation_type, v.timestamp, v.screenshot_path, s.full_name, e.title
        FROM violations v
        JOIN students s ON v.student_id = s.id
        JOIN exams e ON v.exam_id = e.id
        WHERE v.screenshot_path IS NOT NULL
        ORDER BY v.timestamp DESC
    ''').fetchall()
    conn.close()
    
    return render_template('screenshots.html', violations=violations)

@app.route('/exam/submit', methods=['POST'])
def submit_exam():
    if 'student_id' not in session:
        return jsonify({'status': 'error'})
        
    data = request.json
    exam_id = data.get('exam_id')
    answers = data.get('answers', {})
    
    conn = get_db_connection()
    c = conn.cursor()
    
    # Check if disqualified
    res = c.execute('SELECT is_disqualified, warnings_count FROM results WHERE student_id = ? AND exam_id = ?', (session['student_id'], exam_id)).fetchone()
    if res and res['is_disqualified']:
        conn.close()
        return jsonify({'status': 'submitted', 'score': 0, 'redirect': url_for('exam_result', exam_id=exam_id)})
        
    exam = c.execute('SELECT * FROM exams WHERE id = ?', (exam_id,)).fetchone()
    ans_records = c.execute('''
        SELECT a.question_id, q.correct_option 
        FROM student_answers a 
        JOIN questions q ON a.question_id = q.id 
        WHERE a.student_id = ? AND a.exam_id = ?
    ''', (session['student_id'], exam_id)).fetchall()
    
    score = 0
    marks_per_q = exam['total_marks'] / max(len(ans_records), 1)
    
    # Update answers
    for qid_str, selected in answers.items():
        c.execute('UPDATE student_answers SET selected_option = ? WHERE student_id = ? AND exam_id = ? AND question_id = ?', 
                  (selected, session['student_id'], exam_id, int(qid_str)))
                  
    # Calculate score
    for r in ans_records:
        qid = str(r['question_id'])
        selected = answers.get(qid, '')
        if selected == r['correct_option']:
            score += marks_per_q
            
    c.execute('UPDATE results SET score = ? WHERE student_id = ? AND exam_id = ?', (score, session['student_id'], exam_id))
    c.execute('UPDATE sessions SET is_active = FALSE WHERE student_id = ? AND exam_id = ?', (session['student_id'], exam_id))
    
    conn.commit()
    conn.close()
    
    socketio.emit('session_ended', {
        'student_id': session['student_id'],
        'score': score,
        'full_name': session['student_name'],
        'title': exam['title'],
        'warnings_count': res['warnings_count'] if res else 0,
        'is_disqualified': res['is_disqualified'] if res else False
    }, room='admin_room', namespace='/')
    
    return jsonify({'status': 'submitted', 'score': score, 'redirect': url_for('exam_result', exam_id=exam_id)})

@app.route('/exam/result/<int:exam_id>')
def exam_result(exam_id):
    if 'student_id' not in session:
        return redirect(url_for('student_login'))
        
    student_id = session['student_id']
    
    conn = get_db_connection()
    exam = conn.execute('SELECT * FROM exams WHERE id = ?', (exam_id,)).fetchone()
    res = conn.execute('SELECT * FROM results WHERE student_id = ? AND exam_id = ?', (student_id, exam_id)).fetchone()
    
    questions = conn.execute('''
        SELECT q.*, a.selected_option
        FROM student_answers a
        JOIN questions q ON a.question_id = q.id
        WHERE a.student_id = ? AND a.exam_id = ?
    ''', (student_id, exam_id)).fetchall()
    conn.close()
    
    return render_template('exam_result.html', exam=exam, result=res, questions=questions)

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
        
    conn = get_db_connection()
    active_sessions = conn.execute('''
        SELECT s.id as session_id, st.id as student_id, st.full_name, st.roll_number, e.title, e.id as exam_id, s.warnings_count 
        FROM sessions s 
        JOIN students st ON s.student_id = st.id 
        JOIN exams e ON s.exam_id = e.id 
        WHERE s.is_active = TRUE
    ''').fetchall()
    
    banned_students = conn.execute('''
        SELECT id as student_id, full_name, roll_number, email, banned_until 
        FROM students 
        WHERE banned_until IS NOT NULL AND banned_until > datetime('now')
    ''').fetchall()
    
    recent_results = conn.execute('''
        SELECT r.student_id, r.exam_id, s.full_name, s.roll_number, e.title, r.score, r.warnings_count, r.is_disqualified
        FROM results r
        JOIN students s ON r.student_id = s.id
        JOIN exams e ON r.exam_id = e.id
        WHERE r.score IS NOT NULL
        ORDER BY r.id DESC LIMIT 8
    ''').fetchall()
    
    conn.close()
    
    return render_template('admin_dashboard.html', active_sessions=active_sessions, banned_students=banned_students, recent_results=recent_results)

@app.route('/api/terminate_session', methods=['POST'])
def terminate_session():
    if 'admin_id' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'})
        
    data = request.json
    student_id = data.get('student_id')
    exam_id = data.get('exam_id')
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE sessions SET is_active = FALSE WHERE student_id = ? AND exam_id = ?', (student_id, exam_id))
    c.execute('UPDATE results SET is_disqualified = TRUE, score = 0 WHERE student_id = ? AND exam_id = ?', (student_id, exam_id))
    conn.commit()
    conn.close()
    
    # Notify student via socket
    socketio.emit('force_terminate', {'student_id': student_id}, room=f"student_{student_id}")
    
    # Fetch details to notify dashboard
    conn = get_db_connection()
    s_data = conn.execute('SELECT full_name FROM students WHERE id = ?', (student_id,)).fetchone()
    e_data = conn.execute('SELECT title FROM exams WHERE id = ?', (exam_id,)).fetchone()
    res = conn.execute('SELECT warnings_count FROM results WHERE student_id = ? AND exam_id = ?', (student_id, exam_id)).fetchone()
    conn.close()
    
    socketio.emit('session_ended', {
        'student_id': student_id,
        'score': 0,
        'full_name': s_data['full_name'] if s_data else 'Unknown',
        'title': e_data['title'] if e_data else 'Unknown',
        'warnings_count': res['warnings_count'] if res else 0,
        'is_disqualified': True
    }, room='admin_room', namespace='/')
    
    return jsonify({'status': 'success'})

@app.route('/api/warnings/<int:student_id>/<int:exam_id>')
def get_warnings(student_id, exam_id):
    conn = get_db_connection()
    res = conn.execute('SELECT warnings_count, is_disqualified FROM results WHERE student_id = ? AND exam_id = ?', (student_id, exam_id)).fetchone()
    conn.close()
    if res:
        return jsonify({'warnings': res['warnings_count'], 'disqualified': res['is_disqualified']})
    return jsonify({'warnings': 0, 'disqualified': False})

@app.route('/admin/suspended')
def admin_suspended():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
        
    conn = get_db_connection()
    banned_students = conn.execute('''
        SELECT id as student_id, full_name, roll_number, email, banned_until 
        FROM students 
        WHERE banned_until IS NOT NULL AND banned_until > datetime('now')
    ''').fetchall()
    conn.close()
    
    return render_template('suspended.html', banned_students=banned_students)

@app.route('/admin/unban', methods=['POST'])
def unban_student():
    if 'admin_id' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'})
        
    data = request.json
    student_id = data.get('student_id')
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE students SET banned_until = NULL WHERE id = ?', (student_id,))
    # Optionally, we could also reset their is_disqualified status or warnings,
    # but the user only asked to unban them so they can take OTHER exams.
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'success', 'message': 'Student has been successfully unbanned.'})

@app.route('/admin/send_proof', methods=['POST'])
def send_proof():
    if 'admin_id' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'})
        
    data = request.json
    student_id = data.get('student_id')
    exam_id = data.get('exam_id')
    violation_text = data.get('violation', 'Cheating Detected')
    
    conn = get_db_connection()
    student = conn.execute('SELECT email, full_name FROM students WHERE id = ?', (student_id,)).fetchone()
    exam = conn.execute('SELECT title FROM exams WHERE id = ?', (exam_id,)).fetchone()
    
    # Get latest violation screenshot
    violation = conn.execute('SELECT screenshot_path FROM violations WHERE student_id = ? AND exam_id = ? AND screenshot_path IS NOT NULL ORDER BY timestamp DESC LIMIT 1', (student_id, exam_id)).fetchone()
    
    # Get warning count
    res = conn.execute('SELECT warnings_count, is_disqualified FROM results WHERE student_id = ? AND exam_id = ?', (student_id, exam_id)).fetchone()
    warnings = res['warnings_count'] if res else 0
    is_disqualified = res['is_disqualified'] if res else False
    
    conn.close()
    
    if not student:
        return jsonify({'status': 'error', 'message': 'Student not found'})
        
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.image import MIMEImage
        import os
        
        SENDER_EMAIL = "samadhanbodkhe222@gmail.com"
        SENDER_PASSWORD = "fbfe xrpc nspq lrwh" # User needs to replace this
        
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = student['email']
        if is_disqualified or warnings >= 5:
            msg['Subject'] = f"NOTICE OF DISQUALIFICATION & 24-HOUR BAN - {exam['title']}"
            body = f"""Dear {student['full_name']},
            
This is an official notice from ProctorAI. You have repeatedly violated the examination rules during your {exam['title']} exam.

You have received {warnings} warnings. Because you reached the maximum allowed limit of 5 warnings:
1. Your exam has been forcefully terminated.
2. Your score has been automatically reduced to ZERO.
3. YOUR ACCOUNT IS NOW BANNED FOR 24 HOURS. You will not be able to access any further examinations until the ban expires.

Please find the attached photographic proof taken by the AI system of your latest violation: {violation_text}.

Regards,
ProctorAI Admin Team"""
        elif warnings == 4:
            msg['Subject'] = f"FINAL WARNING: ONE STRIKE AWAY FROM 24-HOUR BAN - {exam['title']}"
            body = f"""Dear {student['full_name']},
            
This is your FINAL WARNING from ProctorAI. You have been flagged for cheating during your {exam['title']} exam.

Current Warnings: 4/5
Violation: {violation_text}

WARNING: If you receive ONE MORE warning (Warning 5), your exam will be automatically terminated, your score will become ZERO, and your account will be BANNED for 24 hours. Stop this behavior immediately!

Please find the attached photographic proof taken by the AI system.

Regards,
ProctorAI Admin Team"""
        else:
            msg['Subject'] = f"WARNING {warnings}/5: Academic Violation Flagged - {exam['title']}"
            body = f"""Dear {student['full_name']},
            
This is an official WARNING from ProctorAI. You have been flagged for cheating during your {exam['title']} exam.

Current Warnings: {warnings}/5
Violation: {violation_text}

WARNING: DO NOT do this again! If you continue this behavior and reach 5 warnings, your exam will be automatically terminated, your score will become ZERO, and you will be BANNED for 24 hours.

Please find the attached photographic proof taken by the AI system.

Regards,
ProctorAI Admin Team"""

        msg.attach(MIMEText(body, 'plain'))
        
        if violation and violation['screenshot_path'] and os.path.exists(violation['screenshot_path']):
            with open(violation['screenshot_path'], 'rb') as f:
                img_data = f.read()
            image = MIMEImage(img_data, name=os.path.basename(violation['screenshot_path']))
            msg.attach(image)
            
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        return jsonify({'status': 'success', 'message': 'Proof emailed successfully'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('landing'))


# SocketIO for Live Video Streaming and Real-time Alerts
@socketio.on('join')
def on_join(data):
    room = f"student_{data['student_id']}"
    join_room(room)

@socketio.on('admin_join')
def on_admin_join(data):
    join_room('admin_room')

@socketio.on('video_frame')
def handle_video_frame(data):
    student_id = data.get('student_id')
    exam_id = data.get('exam_id')
    frame_data = data.get('image') # Base64 encoded JPEG
    
    if not frame_data:
        return True
        
    # Decode base64
    encoded_data = frame_data.split(',')[1]
    nparr = np.frombuffer(base64.b64decode(encoded_data), np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if frame is None:
        return True
        
    # Process frame
    processed_frame, violation = processor.process_frame(frame, student_id, exam_id)
    
    # Encode processed frame back to base64 — high quality = less blur
    _, buffer = cv2.imencode('.jpg', processed_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    processed_base64 = base64.b64encode(buffer).decode('utf-8')
    processed_image_url = 'data:image/jpeg;base64,' + processed_base64
    
    # Emit processed frame back to student only
    emit('processed_frame', {'image': processed_image_url}, room=f"student_{student_id}")
    
    # Stream to admin room only (not broadcast to avoid hitting student sockets)
    emit('admin_video_stream', {
        'student_id': student_id,
        'image': processed_image_url,
        'violation': violation
    }, room='admin_room')
    
    # If violation, alert student
    if violation:
        # Fetch warning count AFTER log_violation has already incremented it
        conn = get_db_connection()
        res = conn.execute('SELECT warnings_count FROM results WHERE student_id = ? AND exam_id = ?', (student_id, exam_id)).fetchone()
        conn.close()
        
        warnings_count = res['warnings_count'] if res else 0
        
        emit('cheating_alert', {
            'message': violation,
            'warnings_count': warnings_count
        }, room=f"student_{student_id}")
        
        # Only send to admin room (NOT broadcast which would hit all students)
        emit('admin_violation_alert', {
            'student_id': student_id,
            'exam_id': exam_id,
            'violation': violation,
            'warnings_count': warnings_count,
            'image': processed_image_url
        }, room='admin_room')
        
        if warnings_count >= 5:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute('UPDATE results SET is_disqualified = TRUE, score = 0 WHERE student_id = ? AND exam_id = ?', (student_id, exam_id))
            c.execute('UPDATE sessions SET is_active = FALSE WHERE student_id = ? AND exam_id = ?', (student_id, exam_id))
            c.execute("UPDATE students SET banned_until = datetime('now', '+24 hours') WHERE id = ?", (student_id,))
            conn.commit()
            conn.close()
            emit('force_terminate', {'student_id': student_id, 'reason': 'Maximum warnings reached. Exam submitted with 0 marks and account banned for 24 hours.'}, room=f"student_{student_id}")
            
            # Fetch student name and title
            conn = get_db_connection()
            s_data = conn.execute('SELECT full_name FROM students WHERE id = ?', (student_id,)).fetchone()
            e_data = conn.execute('SELECT title FROM exams WHERE id = ?', (exam_id,)).fetchone()
            conn.close()
            
            emit('session_ended', {
                'student_id': student_id,
                'score': 0,
                'full_name': s_data['full_name'] if s_data else 'Unknown',
                'title': e_data['title'] if e_data else 'Unknown',
                'warnings_count': 5,
                'is_disqualified': True
            }, room='admin_room', namespace='/')
            
        # Automatically dispatch warning/ban email asynchronously
        socketio.start_background_task(send_automated_email, student_id, exam_id, violation)

    return True

browser_violation_cooldowns = {}

@socketio.on('browser_violation')
def handle_browser_violation(data):
    student_id = data.get('student_id')
    exam_id = data.get('exam_id')
    violation_type = data.get('type')
    
    import time
    current_time = time.time()
    
    # 5 seconds cooldown per student for browser violations
    if student_id in browser_violation_cooldowns:
        if current_time - browser_violation_cooldowns[student_id] < 5:
            return # Ignore violation to prevent spam
            
    browser_violation_cooldowns[student_id] = current_time
    
    from utils.logger import log_violation
    is_logged = log_violation(student_id, exam_id, f"Browser Activity: {violation_type}", None)
    if is_logged is False:
        return
    
    conn = get_db_connection()
    res = conn.execute('SELECT warnings_count FROM results WHERE student_id = ? AND exam_id = ?', (student_id, exam_id)).fetchone()
    conn.close()
    warnings_count = res['warnings_count'] if res else 0
    
    emit('cheating_alert', {
        'message': f"Prohibited Browser Activity: {violation_type}",
        'warnings_count': warnings_count
    }, room=f"student_{student_id}")
    
    # Only emit to admin room — NOT broadcast (would hit student sockets too)
    emit('admin_violation_alert', {
        'student_id': student_id,
        'exam_id': exam_id,
        'violation': f"Browser Activity: {violation_type}",
        'warnings_count': warnings_count
    }, room='admin_room')
    
    if warnings_count >= 5:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('UPDATE results SET is_disqualified = TRUE, score = 0 WHERE student_id = ? AND exam_id = ?', (student_id, exam_id))
        c.execute('UPDATE sessions SET is_active = FALSE WHERE student_id = ? AND exam_id = ?', (student_id, exam_id))
        c.execute("UPDATE students SET banned_until = datetime('now', '+24 hours') WHERE id = ?", (student_id,))
        conn.commit()
        conn.close()
        emit('force_terminate', {'student_id': student_id, 'reason': 'Maximum warnings reached. Exam submitted with 0 marks and account banned for 24 hours.'}, room=f"student_{student_id}")
        
        # Fetch student name and title
        conn = get_db_connection()
        s_data = conn.execute('SELECT full_name FROM students WHERE id = ?', (student_id,)).fetchone()
        e_data = conn.execute('SELECT title FROM exams WHERE id = ?', (exam_id,)).fetchone()
        conn.close()
        
        emit('session_ended', {
            'student_id': student_id,
            'score': 0,
            'full_name': s_data['full_name'] if s_data else 'Unknown',
            'title': e_data['title'] if e_data else 'Unknown',
            'warnings_count': 5,
            'is_disqualified': True
        }, room='admin_room')
        
    # Automatically dispatch warning/ban email asynchronously
    socketio.start_background_task(send_automated_email, student_id, exam_id, f"Browser Activity: {violation_type}")

if __name__ == '__main__':
    # Initialize DB before running
    init_db()
    socketio.run(app, host='0.0.0.0', port=5001, debug=True)
