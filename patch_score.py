import sqlite3

def check():
    conn = sqlite3.connect('jobs.db')
    c = conn.cursor()
    c.execute('SELECT title, skills, source FROM jobs LIMIT 5')
    for row in c.fetchall():
        print(row)

check()
