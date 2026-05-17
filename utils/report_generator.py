from database import get_db_connection
import pandas as pd
import os
from config import Config

def generate_student_report(student_id, exam_id):
    conn = get_db_connection()
    c = conn.cursor()
    
    # Get student info
    student = c.execute('SELECT * FROM students WHERE id = ?', (student_id,)).fetchone()
    exam = c.execute('SELECT * FROM exams WHERE id = ?', (exam_id,)).fetchone()
    result = c.execute('SELECT * FROM results WHERE student_id = ? AND exam_id = ?', (student_id, exam_id)).fetchone()
    violations = c.execute('SELECT * FROM violations WHERE student_id = ? AND exam_id = ?', (student_id, exam_id)).fetchall()
    
    conn.close()
    
    report = {
        'student_name': student['full_name'],
        'roll_number': student['roll_number'],
        'exam_title': exam['title'],
        'score': result['score'] if result else 0,
        'warnings': result['warnings_count'] if result else 0,
        'is_disqualified': result['is_disqualified'] if result else False,
        'violations': [dict(v) for v in violations]
    }
    return report

def export_all_reports():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT students.full_name, students.roll_number, exams.title as exam, results.score, results.warnings_count, results.is_disqualified FROM results JOIN students ON results.student_id = students.id JOIN exams ON results.exam_id = exams.id", conn)
    conn.close()
    
    report_path = os.path.join(Config.RESULTS_DIR, 'final_reports.csv')
    df.to_csv(report_path, index=False)
    return report_path
