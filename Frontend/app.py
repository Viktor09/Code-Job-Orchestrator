import os
import flask
import requests

app = flask.Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")
JOB_API_URL = os.getenv("JOB_API_URL")
KONG_AUTH_LOGIN_URL = os.getenv("KONG_AUTH_LOGIN_URL")
KONG_AUTH_REGISTER_URL = os.getenv("KONG_AUTH_REGISTER_URL")
UPLOAD_BASE_DIR = os.getenv("UPLOAD_BASE_DIR")

@app.route("/")
def root():
    return flask.redirect(flask.url_for("login"))

@app.route("/app")
def index():
    return flask.render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if flask.request.method == "GET":
        return flask.render_template("login.html")

    user_email = flask.request.form.get("user_email")
    password = flask.request.form.get("password")

    response = requests.post(
        KONG_AUTH_LOGIN_URL,
        json={"user_email": user_email, "password": password}
    )
    payload = response.json()

    if not response.ok:
        return flask.render_template("login.html", error=payload.get("error"))

    flask.session["access_token"] = payload.get("access_token")
    return flask.redirect(flask.url_for("index"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if flask.request.method == "GET":
        return flask.render_template("register.html")

    user_name = flask.request.form.get("user_name")
    user_email = flask.request.form.get("user_email")
    password = flask.request.form.get("password")

    response = requests.post(
        KONG_AUTH_REGISTER_URL,
        json={"user_name": user_name, "user_email": user_email, "password": password}
    )

    if not response.ok:
        return flask.render_template("register.html", error="Registration failed")

    return flask.redirect(flask.url_for("login"))

@app.route("/api/jobs", methods=["GET"])
def list_jobs():
    access_token = flask.session.get("access_token")
    if not access_token:
        return flask.jsonify({"error": "Unauthorized"}), 401

    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        response = requests.get(JOB_API_URL, headers=headers, timeout=15)
    except requests.RequestException:
        return flask.jsonify({"error": "Could not connect to Job API"}), 502

    try:
        payload = response.json()
    except ValueError:
        return flask.jsonify({"error": "Invalid response from Job API"}), 502

    if not response.ok:
        if isinstance(payload, dict) and payload.get("error"):
            return flask.jsonify(payload), response.status_code
        return flask.jsonify({"error": "Failed to fetch jobs"}), response.status_code

    jobs = payload.get("jobs", []) if isinstance(payload, dict) else []

    mapped_jobs = []
    for job in jobs:
        mapped_jobs.append({
            "id": job.get("job_id"),
            "executableName": os.path.basename(job.get("executable_path", "")),
            "status": job.get("status"),
            "submittedAt": job.get("created_at")
        })

    return flask.jsonify(mapped_jobs), 200

@app.route("/api/jobs/<job_id>/log", methods=["GET"])
def get_job_log(job_id):
    access_token = flask.session.get("access_token")
    if not access_token:
        return flask.jsonify({"error": "Unauthorized"}), 401

    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        response = requests.get(f"{JOB_API_URL}/{job_id}", headers=headers, timeout=15)
    except requests.RequestException:
        return flask.jsonify({"error": "Could not connect to Job API"}), 502

    try:
        job = response.json()
    except ValueError:
        return flask.jsonify({"error": "Invalid response from Job API"}), 502

    if not response.ok:
        return flask.jsonify(job if isinstance(job, dict) else {"error": "Failed to fetch job"}), response.status_code

    logs = f"Job ID: {job.get('job_id')}\nStatus: {job.get('status')}\nError: {job.get('error_message')}"
    return flask.jsonify({"logs": logs}), 200

@app.route("/api/jobs", methods=["POST"])
def submit_job():
    job_label = flask.request.form.get("job_label")
    executable = flask.request.files.get("executable")
    
    target_dir = os.path.join(UPLOAD_BASE_DIR, job_label)
    os.makedirs(target_dir, exist_ok=True)
    
    executable_path = os.path.join(target_dir, executable.filename)
    executable.save(executable_path)

    headers = {"Authorization": "Bearer " + flask.session.get("access_token", "")}
    gateway_request = {
        "label": job_label,
        "executable_path": executable_path,
        "parameters_json": {}
    }
    
    response = requests.post(JOB_API_URL, json=gateway_request, headers=headers)
    return flask.jsonify(response.json())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)