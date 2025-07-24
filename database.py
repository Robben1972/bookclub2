import sqlite3
from datetime import datetime
from config import YOUR_ADMIN_ID

class Database:
    def __init__(self):
        self.conn = sqlite3.connect('book_club.db')
        self.create_tables()

    def create_tables(self):
        with self.conn:
            self.conn.execute('''CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                username TEXT,
                is_active INTEGER DEFAULT 1,
                is_admin INTEGER DEFAULT 0
            )''')
            self.conn.execute('''CREATE TABLE IF NOT EXISTS books (
                user_id INTEGER,
                book_name TEXT,
                start_page INTEGER,
                last_page INTEGER,
                finished INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, book_name),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )''')
            self.conn.execute('''CREATE TABLE IF NOT EXISTS daily_reading (
                user_id INTEGER,
                date TEXT,
                pages_read INTEGER,
                PRIMARY KEY (user_id, date),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )''')
            self.conn.execute('''CREATE TABLE IF NOT EXISTS weekly_reading (
                user_id INTEGER,
                week TEXT,
                pages_read INTEGER,
                PRIMARY KEY (user_id, week),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )''')

    def add_user(self, user_id, name, username):
        with self.conn:
            self.conn.execute('INSERT OR REPLACE INTO users (user_id, name, username, is_active, is_admin) VALUES (?, ?, ?, 1, ?)',
                           (user_id, name, username, 1 if str(user_id) == YOUR_ADMIN_ID else 0))

    def get_user(self, user_id):
        return self.conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()

    def get_all_users(self):
        return self.conn.execute('SELECT * FROM users').fetchall()

    def is_user_active(self, user_id):
        user = self.get_user(user_id)
        return user[3] if user else False

    def activate_user(self, user_id):
        with self.conn:
            self.conn.execute('UPDATE users SET is_active = 1 WHERE user_id = ?', (user_id,))

    def deactivate_user(self, user_id):
        with self.conn:
            self.conn.execute('UPDATE users SET is_active = 0 WHERE user_id = ?', (user_id,))

    def is_admin(self, user_id):
        user = self.get_user(user_id)
        return user[4] if user else False

    def add_book(self, user_id, book_name, start_page, last_page, finished):
        with self.conn:
            self.conn.execute('INSERT INTO books (user_id, book_name, start_page, last_page, finished) VALUES (?, ?, ?, ?, ?)',
                           (user_id, book_name, start_page, last_page, finished))
            self.update_reading_stats(user_id, last_page - start_page)

    def update_book_progress(self, user_id, book_name, last_page, finished):
        with self.conn:
            current = self.conn.execute('SELECT last_page FROM books WHERE user_id = ? AND book_name = ?',
                                     (user_id, book_name)).fetchone()
            if current:
                pages = last_page - current[0]
                self.conn.execute('UPDATE books SET start_page = last_page, last_page = ?, finished = ? WHERE user_id = ? AND book_name = ?',
                               (last_page, finished, user_id, book_name))
                self.update_reading_stats(user_id, pages)

    def mark_book_finished(self, user_id, book_name):
        with self.conn:
            self.conn.execute('UPDATE books SET finished = 1 WHERE user_id = ? AND book_name = ?',
                           (user_id, book_name))

    def get_user_books(self, user_id):
        return self.conn.execute('SELECT * FROM books WHERE user_id = ?', (user_id,)).fetchall()

    def get_book(self, user_id, book_name):
        return self.conn.execute('SELECT * FROM books WHERE user_id = ? AND book_name = ?',
                               (user_id, book_name)).fetchone()

    def update_reading_stats(self, user_id, pages):
        today = datetime.now().strftime('%Y-%m-%d')
        week = datetime.now().strftime('%Y-%W')
        with self.conn:
            cursor = self.conn.execute('SELECT pages_read FROM daily_reading WHERE user_id = ? AND date = ?',
                                    (user_id, today))
            current_pages = cursor.fetchone()
            new_pages = pages + (current_pages[0] if current_pages else 0)
            self.conn.execute('INSERT OR REPLACE INTO daily_reading (user_id, date, pages_read) VALUES (?, ?, ?)',
                           (user_id, today, new_pages))
            cursor = self.conn.execute('SELECT pages_read FROM weekly_reading WHERE user_id = ? AND week = ?',
                                    (user_id, week))
            current_week_pages = cursor.fetchone()
            new_week_pages = pages + (current_week_pages[0] if current_week_pages else 0)
            self.conn.execute('INSERT OR REPLACE INTO weekly_reading (user_id, week, pages_read) VALUES (?, ?, ?)',
                           (user_id, week, new_week_pages))

    def get_daily_reading(self, user_id):
        today = datetime.now().strftime('%Y-%m-%d')
        result = self.conn.execute('SELECT pages_read FROM daily_reading WHERE user_id = ? AND date = ?',
                                 (user_id, today)).fetchone()
        return result[0] if result else 0

    def clear_daily(self):
        today = datetime.now().strftime('%Y-%m-%d')
        with self.conn:
            self.conn.execute('DELETE FROM daily_reading WHERE date != ?', (today,))

    def clear_weekly(self):
        with self.conn:
            self.conn.execute('DELETE FROM weekly_reading')

    def get_top_reader(self):
        week = datetime.now().strftime('%Y-%W')
        return self.conn.execute('''
            SELECT u.user_id, u.name, u.username 
            FROM weekly_reading w 
            JOIN users u ON w.user_id = u.user_id 
            WHERE w.week = ? 
            ORDER BY w.pages_read DESC 
            LIMIT 1
        ''', (week,)).fetchone()

    def delete_user(self, user_id):
        with self.conn:
            self.conn.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
            self.conn.execute('DELETE FROM books WHERE user_id = ?', (user_id,))
            self.conn.execute('DELETE FROM daily_reading WHERE user_id = ?', (user_id,))
            self.conn.execute('DELETE FROM weekly_reading WHERE user_id = ?', (user_id,))