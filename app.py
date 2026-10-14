from pathlib import Path
import sqlite3
import uuid
from datetime import datetime, timezone
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "database.db"
UPLOAD_FOLDER = BASE_DIR / "uploads"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf", "doc", "docx"}
MAX_FILE_SIZE = 10 * 1024 * 1024

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE
CORS(app, resources={r"/api/*": {"origins": ["http://127.0.0.1:5500", "http://localhost:5500"]}})


def db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database():
    with db_connection() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS legacy_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT DEFAULT 'Other',
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS security_incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            severity TEXT DEFAULT 'Medium',
            created_at TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS uploaded_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            original_name TEXT NOT NULL,
            size INTEGER NOT NULL,
            uploaded_at TEXT NOT NULL
        )""")


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.get("/")
def home():
    return jsonify(success=True, project="LEGACYVAULT AI", message="Your Digital Life. Your Rules. Your Legacy.")


@app.get("/api/health")
def health():
    return jsonify(success=True, project="LEGACYVAULT AI", database_exists=DATABASE_PATH.exists())


@app.route("/api/assets", methods=["GET", "POST"])
def assets():
    if request.method == "GET":
        with db_connection() as conn:
            rows = conn.execute("SELECT * FROM legacy_assets ORDER BY id DESC").fetchall()
        return jsonify(success=True, assets=[dict(row) for row in rows])
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify(success=False, message="Asset name is required."), 400
    category = str(data.get("category", "Other"))[:100]
    notes = str(data.get("notes", ""))[:2000]
    with db_connection() as conn:
        cur = conn.execute("INSERT INTO legacy_assets (name, category, notes, created_at) VALUES (?, ?, ?, ?)",
                           (name[:200], category, notes, datetime.now(timezone.utc).isoformat()))
        asset_id = cur.lastrowid
    return jsonify(success=True, id=asset_id, message="Asset saved."), 201


@app.route("/api/assets/<int:asset_id>", methods=["DELETE"])
def delete_asset(asset_id):
    with db_connection() as conn:
        cur = conn.execute("DELETE FROM legacy_assets WHERE id = ?", (asset_id,))
    if cur.rowcount == 0:
        return jsonify(success=False, message="Asset not found."), 404
    return jsonify(success=True, message="Asset deleted.")


@app.route("/api/incidents", methods=["GET", "POST"])
def incidents():
    if request.method == "GET":
        with db_connection() as conn:
            rows = conn.execute("SELECT * FROM security_incidents ORDER BY id DESC").fetchall()
        return jsonify(success=True, incidents=[dict(row) for row in rows])
    data = request.get_json(silent=True) or {}
    title = str(data.get("title", "")).strip()
    if not title:
        return jsonify(success=False, message="Incident title is required."), 400
    description = str(data.get("description", ""))[:4000]
    severity = str(data.get("severity", "Medium"))[:30]
    with db_connection() as conn:
        cur = conn.execute("INSERT INTO security_incidents (title, description, severity, created_at) VALUES (?, ?, ?, ?)",
                           (title[:200], description, severity, datetime.now(timezone.utc).isoformat()))
        incident_id = cur.lastrowid
    return jsonify(success=True, id=incident_id, message="Incident saved."), 201


@app.post("/api/upload")
def upload_file():
    if "file" not in request.files:
        return jsonify(success=False, message="Choose a file first."), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify(success=False, message="Choose a file first."), 400
    original_name = secure_filename(file.filename)
    if not original_name or not allowed_file(original_name):
        return jsonify(success=False, message="File type not allowed. Use PNG, JPG, JPEG, PDF, DOC or DOCX."), 400
    ext = original_name.rsplit(".", 1)[1].lower()
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    destination = UPLOAD_FOLDER / stored_name
    file.save(destination)
    size = destination.stat().st_size
    if size > MAX_FILE_SIZE:
        destination.unlink(missing_ok=True)
        return jsonify(success=False, message="File exceeds the 10 MB limit."), 413
    with db_connection() as conn:
        conn.execute("INSERT INTO uploaded_files (filename, original_name, size, uploaded_at) VALUES (?, ?, ?, ?)",
                     (stored_name, original_name, size, datetime.now(timezone.utc).isoformat()))
    return jsonify(success=True, message="File uploaded successfully.", filename=stored_name, original_name=original_name, size=size), 201


@app.get("/api/uploads")
def list_uploads():
    with db_connection() as conn:
        rows = conn.execute("SELECT filename, original_name, size, uploaded_at FROM uploaded_files ORDER BY id DESC").fetchall()
    return jsonify(success=True, files=[dict(row) for row in rows])


@app.get("/api/uploads/<path:filename>")
def download_upload(filename):
    with db_connection() as conn:
        row = conn.execute("SELECT original_name FROM uploaded_files WHERE filename = ?", (filename,)).fetchone()
    if not row or not (UPLOAD_FOLDER / filename).is_file():
        return jsonify(success=False, message="File not found."), 404
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True, download_name=row["original_name"])


@app.get("/api/previews/<path:filename>")
def preview_upload(filename):
    suffix = Path(filename).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg"}:
        return jsonify(success=False, message="Preview is available only for images."), 400
    with db_connection() as conn:
        row = conn.execute("SELECT filename FROM uploaded_files WHERE filename = ?", (filename,)).fetchone()
    if not row or not (UPLOAD_FOLDER / filename).is_file():
        return jsonify(success=False, message="File not found."), 404
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=False)


@app.errorhandler(413)
def too_large(_error):
    return jsonify(success=False, message="File is too large. Maximum size is 10 MB."), 413


if __name__ == "__main__":
    initialize_database()
    print("LEGACYVAULT AI backend is starting...")
    print(f"Database location: {DATABASE_PATH}")
    print(f"Upload folder: {UPLOAD_FOLDER}")
    app.run(host="127.0.0.1", port=5000, debug=False)
