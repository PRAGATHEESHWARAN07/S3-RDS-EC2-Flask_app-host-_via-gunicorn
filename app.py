import os
import uuid
from datetime import datetime
from functools import wraps

import boto3
import pymysql
from botocore.exceptions import ClientError
from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    session, abort, send_file
)
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "CHANGE_THIS_SECRET_KEY")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB per upload
csrf = CSRFProtect(app)

BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "txt", "rtf", "xls", "xlsx", "ppt", "pptx",
    "jpg", "jpeg", "png", "gif", "webp"
}

s3 = boto3.client("s3", region_name=AWS_REGION)

def db_connection():
    return pymysql.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        connect_timeout=10
    )

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("home"))
        return view(*args, **kwargs)
    return wrapped

def current_user():
    if "user_id" not in session:
        return None
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, first_name, last_name, email FROM users WHERE id=%s",
                (session["user_id"],)
            )
            return cur.fetchone()

@app.context_processor
def inject_user():
    return {"logged_in_user": current_user()}

@app.cli.command("init-db")
def init_db():
    """Create the application tables inside the configured database."""
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    first_name VARCHAR(80) NOT NULL,
                    last_name VARCHAR(80) NOT NULL,
                    email VARCHAR(190) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT UNSIGNED NOT NULL,
                    original_name VARCHAR(255) NOT NULL,
                    s3_key VARCHAR(700) NOT NULL UNIQUE,
                    content_type VARCHAR(150),
                    size_bytes BIGINT UNSIGNED NOT NULL,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_files_user_uploaded (user_id, uploaded_at),
                    CONSTRAINT fk_files_user FOREIGN KEY (user_id)
                        REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
    print("Database tables are ready.")

@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")

@app.post("/register")
def register():
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not all([first_name, last_name, email, password, confirm_password]):
        flash("Please complete every field.", "danger")
        return redirect(url_for("home") + "#register")
    if len(password) < 8:
        flash("Password must contain at least 8 characters.", "danger")
        return redirect(url_for("home") + "#register")
    if password != confirm_password:
        flash("Passwords do not match.", "danger")
        return redirect(url_for("home") + "#register")

    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (first_name,last_name,email,password_hash) VALUES (%s,%s,%s,%s)",
                    (first_name, last_name, email, generate_password_hash(password))
                )
        flash("Account created. You can now log in.", "success")
    except pymysql.err.IntegrityError:
        flash("An account with this email already exists.", "danger")
    except pymysql.MySQLError:
        app.logger.exception("Registration database error")
        flash("Could not create your account. Please try again.", "danger")
    return redirect(url_for("home") + "#login")

@app.post("/login")
def login():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, password_hash FROM users WHERE email=%s", (email,))
                user = cur.fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session.permanent = True
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    except pymysql.MySQLError:
        app.logger.exception("Login database error")
        flash("Unable to log in right now.", "danger")
    return redirect(url_for("home") + "#login")

@app.get("/logout")
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))

@app.get("/dashboard")
@login_required
def dashboard():
    user = current_user()
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS file_count, COALESCE(SUM(size_bytes),0) AS total_bytes "
                "FROM files WHERE user_id=%s", (session["user_id"],)
            )
            stats = cur.fetchone()
            cur.execute(
                "SELECT id, original_name, content_type, size_bytes, uploaded_at "
                "FROM files WHERE user_id=%s ORDER BY uploaded_at DESC LIMIT 5",
                (session["user_id"],)
            )
            recent_files = cur.fetchall()
    return render_template("dashboard.html", user=user, stats=stats, recent_files=recent_files)

@app.get("/manage")
@login_required
def manage():
    query = request.args.get("q", "").strip()
    file_type = request.args.get("type", "").strip().lower()
    sql = ("SELECT id, original_name, content_type, size_bytes, uploaded_at "
           "FROM files WHERE user_id=%s")
    params = [session["user_id"]]
    if query:
        sql += " AND original_name LIKE %s"
        params.append(f"%{query}%")
    if file_type == "image":
        sql += " AND content_type LIKE 'image/%'"
    elif file_type == "document":
        sql += " AND (content_type LIKE 'application/%' OR content_type LIKE 'text/%')"
    sql += " ORDER BY uploaded_at DESC"
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            files = cur.fetchall()
    return render_template("manage.html", files=files, query=query, file_type=file_type)

@app.post("/upload")
@login_required
def upload():
    if not BUCKET_NAME:
        flash("S3_BUCKET_NAME is not configured on the server.", "danger")
        return redirect(url_for("manage"))

    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        flash("Choose a file first.", "warning")
        return redirect(url_for("manage"))

    original_name = secure_filename(uploaded.filename)
    if not original_name or not allowed_file(original_name):
        flash("That file type is not allowed.", "danger")
        return redirect(url_for("manage"))

    # Unique object key prevents name collisions and isolates each user's objects.
    extension = original_name.rsplit(".", 1)[1].lower()
    object_key = f"users/{session['user_id']}/{uuid.uuid4().hex}.{extension}"
    content_type = uploaded.mimetype or "application/octet-stream"

    try:
        uploaded.stream.seek(0, 2)
        size_bytes = uploaded.stream.tell()
        uploaded.stream.seek(0)
        if size_bytes <= 0:
            flash("The selected file is empty.", "warning")
            return redirect(url_for("manage"))

        # Stream the upload to S3; no permanent upload file is created on EC2.
        s3.upload_fileobj(
            uploaded.stream,
            BUCKET_NAME,
            object_key,
            ExtraArgs={"ContentType": content_type}
        )
        try:
            with db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO files (user_id, original_name, s3_key, content_type, size_bytes) "
                        "VALUES (%s,%s,%s,%s,%s)",
                        (session["user_id"], original_name, object_key, content_type, size_bytes)
                    )
        except Exception:
            # Avoid an orphaned S3 object if metadata cannot be saved.
            s3.delete_object(Bucket=BUCKET_NAME, Key=object_key)
            raise
        flash("File uploaded successfully to S3.", "success")
    except (ClientError, pymysql.MySQLError):
        app.logger.exception("Upload failed")
        flash("Upload failed. Check the application logs and AWS/database access.", "danger")
    return redirect(url_for("manage"))

def get_owned_file(file_id):
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM files WHERE id=%s AND user_id=%s",
                (file_id, session["user_id"])
            )
            item = cur.fetchone()
    if not item:
        abort(404)
    return item

@app.get("/file/<int:file_id>/download")
@login_required
def download_file(file_id):
    item = get_owned_file(file_id)
    try:
        url = s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": BUCKET_NAME,
                "Key": item["s3_key"],
                "ResponseContentDisposition": f'attachment; filename="{item["original_name"]}"'
            },
            ExpiresIn=300
        )
        return redirect(url)
    except ClientError:
        app.logger.exception("Could not create download URL")
        flash("Could not prepare the download.", "danger")
        return redirect(url_for("manage"))

@app.get("/file/<int:file_id>/preview")
@login_required
def preview_file(file_id):
    item = get_owned_file(file_id)
    if not (item["content_type"] or "").startswith(("image/", "application/pdf")):
        flash("Preview is available for images and PDF files.", "warning")
        return redirect(url_for("manage"))
    try:
        url = s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": BUCKET_NAME,
                "Key": item["s3_key"],
                "ResponseContentDisposition": "inline",
                "ResponseContentType": item["content_type"] or "application/octet-stream"
            },
            ExpiresIn=300
        )
        return redirect(url)
    except ClientError:
        app.logger.exception("Could not create preview URL")
        flash("Could not prepare the preview.", "danger")
        return redirect(url_for("manage"))

@app.post("/file/<int:file_id>/delete")
@login_required
def delete_file(file_id):
    item = get_owned_file(file_id)
    try:
        s3.delete_object(Bucket=BUCKET_NAME, Key=item["s3_key"])
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM files WHERE id=%s AND user_id=%s",
                    (file_id, session["user_id"])
                )
        flash("File deleted from S3.", "success")
    except (ClientError, pymysql.MySQLError):
        app.logger.exception("Delete failed")
        flash("Could not delete the file.", "danger")
    return redirect(url_for("manage"))

@app.errorhandler(413)
def too_large(_error):
    flash("File is too large. Maximum upload size is 16 MB.", "danger")
    return redirect(url_for("manage"))

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
