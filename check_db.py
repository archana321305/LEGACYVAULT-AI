import sqlite3
from pathlib import Path

db_path = Path(__file__).resolve().parent / "database.db"

print("Database exists:", db_path.exists())

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()

print("Database tables:", tables)

conn.close()