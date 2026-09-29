import os
import re
from io import BytesIO
from urllib.parse import quote

from flask import Flask, abort, render_template, request, redirect, url_for, flash, send_file
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.core.exceptions import ResourceNotFoundError, HttpResponseError
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this-in-app-service")
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_MB", "50")) * 1024 * 1024

STORAGE_ACCOUNT_NAME = os.environ.get("STORAGE_ACCOUNT_NAME", "")
BLOB_CONTAINER_NAME = os.environ.get("BLOB_CONTAINER_NAME", "uploads")
ALLOWED_EXTENSIONS = {
    ext.strip().lower()
    for ext in os.environ.get("ALLOWED_EXTENSIONS", "txt,pdf,png,jpg,jpeg,csv,xlsx,docx,pptx,zip").split(",")
    if ext.strip()
}


def get_user():
    # These headers are injected by Azure App Service Authentication (Easy Auth).
    name = request.headers.get("X-MS-CLIENT-PRINCIPAL-NAME", "unknown-user")
    object_id = request.headers.get("X-MS-CLIENT-PRINCIPAL-ID", "")
    if not object_id:
        # Local-only fallback. In Azure, Easy Auth should require authentication.
        object_id = "local-development"
    safe_id = re.sub(r"[^A-Za-z0-9._-]", "_", object_id)
    return {"name": name, "id": safe_id}


def get_container_client():
    if not STORAGE_ACCOUNT_NAME:
        raise RuntimeError("STORAGE_ACCOUNT_NAME is not configured.")
    account_url = f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net"
    credential = DefaultAzureCredential()
    service = BlobServiceClient(account_url=account_url, credential=credential)
    return service.get_container_client(BLOB_CONTAINER_NAME)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def user_blob_name(user_id, filename):
    return f"{user_id}/{filename}"


@app.get("/")
def index():
    user = get_user()
    files = []
    error = None
    try:
        container = get_container_client()
        prefix = f"{user['id']}/"
        for blob in container.list_blobs(name_starts_with=prefix):
            files.append({
                "name": blob.name[len(prefix):],
                "size": blob.size,
                "modified": blob.last_modified,
            })
    except Exception as exc:
        error = str(exc)
    return render_template("index.html", user=user, files=files, error=error,
                           max_upload_mb=app.config["MAX_CONTENT_LENGTH"] // 1024 // 1024,
                           allowed_extensions=sorted(ALLOWED_EXTENSIONS))


@app.post("/upload")
def upload():
    user = get_user()
    file = request.files.get("file")
    if not file or not file.filename:
        flash("업로드할 파일을 선택하세요.", "error")
        return redirect(url_for("index"))

    filename = secure_filename(file.filename)
    if not filename or not allowed_file(filename):
        flash("허용되지 않은 파일 형식입니다.", "error")
        return redirect(url_for("index"))

    try:
        blob = get_container_client().get_blob_client(user_blob_name(user["id"], filename))
        blob.upload_blob(
            file.stream,
            overwrite=True,
            content_settings=ContentSettings(content_type=file.mimetype or "application/octet-stream"),
        )
        flash(f"{filename} 업로드가 완료되었습니다.", "success")
    except HttpResponseError as exc:
        flash(f"Storage 업로드 실패: {exc.message}", "error")
    return redirect(url_for("index"))


@app.get("/download/<path:filename>")
def download(filename):
    user = get_user()
    safe_name = secure_filename(filename)
    if safe_name != filename:
        abort(400)
    try:
        blob = get_container_client().get_blob_client(user_blob_name(user["id"], safe_name))
        props = blob.get_blob_properties()
        data = blob.download_blob().readall()
        return send_file(
            BytesIO(data),
            mimetype=props.content_settings.content_type or "application/octet-stream",
            as_attachment=True,
            download_name=safe_name,
        )
    except ResourceNotFoundError:
        abort(404)


@app.post("/delete/<path:filename>")
def delete(filename):
    user = get_user()
    safe_name = secure_filename(filename)
    if safe_name != filename:
        abort(400)
    try:
        get_container_client().delete_blob(user_blob_name(user["id"], safe_name))
        flash(f"{safe_name} 파일을 삭제했습니다.", "success")
    except ResourceNotFoundError:
        flash("파일을 찾을 수 없습니다.", "error")
    return redirect(url_for("index"))


@app.errorhandler(413)
def too_large(_):
    return f"파일 크기는 {app.config['MAX_CONTENT_LENGTH'] // 1024 // 1024}MB 이하여야 합니다.", 413


@app.get("/health")
def health():
    return {"status": "ok"}, 200
