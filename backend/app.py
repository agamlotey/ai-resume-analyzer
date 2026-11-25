from __future__ import annotations

import io
import logging
import re
import socket
import urllib.request
from collections import Counter
from pathlib import Path

from flask import Flask, g, jsonify, request, send_file, send_from_directory

import config
import nlp
from auth import AuthError, create_auth, require_login
from storage import create_storage
from store import create_store, new_id, now_iso

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("resume-analyzer")

FRONTEND_DIR = config.PROJECT_DIR / "frontend"

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_MB * 1024 * 1024

store = create_store()
storage = create_storage()
auth = create_auth(store)
login_required = require_login(auth)
admin_required = require_login(auth, admin=True)

if not config.is_aws():
    from seed import seed
    seed(store, auth)


def instance_info():
    try:
        token_req = urllib.request.Request("http://169.254.169.254/latest/api/token", method="PUT",
                                           headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"})
        token = urllib.request.urlopen(token_req, timeout=0.3).read().decode()
        info = {}
        for key, path in (("instance_id", "instance-id"), ("availability_zone", "placement/availability-zone")):
            req = urllib.request.Request(f"http://169.254.169.254/latest/meta-data/{path}",
                                         headers={"X-aws-ec2-metadata-token": token})
            info[key] = urllib.request.urlopen(req, timeout=0.3).read().decode()
        return info
    except Exception:
        return {"instance_id": socket.gethostname(), "availability_zone": "local"}


INSTANCE = instance_info()


@app.errorhandler(AuthError)
def handle_auth_error(e):
    return jsonify(error=str(e)), e.status


@app.errorhandler(413)
def too_large(e):
    return jsonify(error=f"File is too large. The limit is {config.MAX_UPLOAD_MB} MB."), 413


@app.get("/api/health")
def health():
    return jsonify(status="ok", mode=config.APP_MODE, auth=auth.kind, storage=storage.kind,
                   database="dynamodb" if config.is_aws() else "sqlite", **INSTANCE)


@app.post("/api/auth/register")
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name = (data.get("name") or "").strip() or email.split("@")[0]
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify(error="Please enter a valid email address."), 400
    if len(password) < 8 or not re.search(r"\d", password) or not re.search(r"[a-z]", password) \
            or not re.search(r"[A-Z]", password):
        return jsonify(error="Password needs at least 8 characters, with an uppercase letter, a lowercase letter and a number."), 400
    auth.register(email, password, name)
    token = auth.login(email, password)
    return jsonify(token=token, user=auth.verify(token)), 201


@app.post("/api/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    token = auth.login((data.get("email") or "").strip().lower(), data.get("password") or "")
    return jsonify(token=token, user=auth.verify(token))


@app.get("/api/auth/me")
@login_required
def me():
    return jsonify(user=g.user)


@app.get("/api/jobs")
@login_required
def list_jobs():
    return jsonify(jobs=store.list_jobs())


@app.post("/api/jobs")
@admin_required
def create_job():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    if not title or len(description) < 30:
        return jsonify(error="A job needs a title and a description of at least 30 characters."), 400
    job = {
        "id": new_id(),
        "title": title,
        "company": (data.get("company") or "").strip(),
        "location": (data.get("location") or "").strip(),
        "description": description,
        "skills": nlp.parse_jd(description)["skills"],
        "created_by": g.user["email"],
        "created_at": now_iso(),
    }
    store.put_job(job)
    return jsonify(job=job), 201


@app.delete("/api/jobs/<job_id>")
@admin_required
def delete_job(job_id):
    store.delete_job(job_id)
    return jsonify(deleted=job_id)


@app.post("/api/analyze")
@login_required
def analyze():
    file = request.files.get("resume")
    if not file or not file.filename:
        return jsonify(error="Please choose a resume file to upload."), 400
    ext = Path(file.filename).suffix.lower()
    if ext not in config.ALLOWED_EXTENSIONS:
        return jsonify(error="Please upload a PDF, DOCX or TXT file."), 400

    job_id = request.form.get("job_id") or ""
    if job_id:
        job = store.get_job(job_id)
        if not job:
            return jsonify(error="That job posting no longer exists."), 404
        jd_text, job_title = job["description"], job["title"]
    else:
        jd_text = (request.form.get("job_description") or "").strip()
        job_title = (request.form.get("job_title") or "").strip() or "Custom job description"
        if len(jd_text) < 30:
            return jsonify(error="Please paste a job description (at least 30 characters) or pick a job posting."), 400

    data = file.read()
    try:
        resume_text = nlp.extract_text(file.filename, data)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception:
        log.exception("Could not read resume")
        return jsonify(error="Could not read this file. Try saving it again as PDF or DOCX."), 400
    if len(resume_text.split()) < 20:
        return jsonify(error="Very little text was found in this resume. If it is a scanned image, upload a text-based PDF or DOCX."), 400

    match_id = new_id()
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", file.filename)[-80:]
    resume_key = f"resumes/{g.user['id']}/{match_id}/{safe_name}"
    storage.save(resume_key, data, file.mimetype or "application/octet-stream")

    result = nlp.match(resume_text, jd_text)
    record = {
        "id": match_id,
        "user_id": g.user["id"],
        "user_email": g.user["email"],
        "job_id": job_id,
        "job_title": job_title,
        "resume_key": resume_key,
        "resume_name": file.filename,
        "score": result["score"],
        "verdict": result["verdict"],
        "result": result,
        "created_at": now_iso(),
    }
    store.put_match(record)
    log.info("match %s user=%s score=%s", match_id, g.user["email"], result["score"])
    return jsonify(match=record, served_by=INSTANCE["instance_id"]), 201


def _can_see(match):
    return match and (g.user["role"] == "admin" or match["user_id"] == g.user["id"])


@app.get("/api/matches")
@login_required
def list_matches():
    if g.user["role"] == "admin" and request.args.get("all") == "1":
        return jsonify(matches=store.list_matches())
    return jsonify(matches=store.list_matches(g.user["id"]))


@app.get("/api/matches/<match_id>")
@login_required
def get_match(match_id):
    match = store.get_match(match_id)
    if not _can_see(match):
        return jsonify(error="Match not found."), 404
    return jsonify(match=match)


@app.get("/api/matches/<match_id>/resume")
@login_required
def get_resume(match_id):
    match = store.get_match(match_id)
    if not _can_see(match):
        return jsonify(error="Match not found."), 404
    url = storage.download_url(match["resume_key"], match["resume_name"])
    if url:
        return jsonify(url=url)
    return send_file(io.BytesIO(storage.read(match["resume_key"])), download_name=match["resume_name"])


@app.get("/api/stats")
@admin_required
def stats():
    matches = store.list_matches()
    missing = Counter()
    for m in matches[:200]:
        full = store.get_match(m["id"])
        missing.update(full["result"]["missing_skills"])
    scores = [m["score"] for m in matches]
    return jsonify(
        total_matches=len(matches),
        total_users=len({m["user_id"] for m in matches}),
        total_jobs=len(store.list_jobs()),
        average_score=round(sum(scores) / len(scores), 1) if scores else 0,
        top_missing_skills=missing.most_common(8),
    )


@app.get("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/<path:path>")
def frontend_files(path):
    if path.startswith("api/"):
        return jsonify(error="Not found"), 404
    if (FRONTEND_DIR / path).is_file():
        return send_from_directory(FRONTEND_DIR, path)
    return send_from_directory(FRONTEND_DIR, "index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
