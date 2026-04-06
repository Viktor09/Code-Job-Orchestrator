import datetime
import os
import re

import flask
import requests

app = flask.Flask(__name__)
JOB_API_URL = ""
jobs_store = []

@app.route("/")
def index():
    return flask.render_template("index.html")

def _find_job(job_id):
    for job in jobs_store:
        if job["id"] == job_id:
            return job
    return None


def _make_job_id_from_label(job_label):
    base = re.sub(r"[^a-zA-Z0-9_-]", "-", job_label.strip())
    base = re.sub(r"-+", "-", base).strip("-")
    if not base:
        base = "job"

    job_id = base
    suffix = 2
    while _find_job(job_id) is not None:
        job_id = f"{base}-{suffix}"
        suffix += 1
    return job_id


@app.route("/api/jobs", methods=["GET"])
def list_jobs():
    return flask.jsonify(jobs_store), 200


@app.route("/api/jobs/<job_id>/log", methods=["GET"])
def get_job_log(job_id):
    job = _find_job(job_id)
    if not job:
        return flask.jsonify({"error": "Job not found"}), 404
    return flask.jsonify({"logs": job.get("logsCustom", "No logs available")}), 200


def _submit_impl():
    if 'executable' not in flask.request.files:
        return flask.jsonify({"status": "Missing executable"}), 400

    executable = flask.request.files['executable']
    additional_files = flask.request.files.getlist('additional_files')
    job_label = flask.request.form.get('job_label', '').strip()

    if not job_label:
        return flask.jsonify({"status": "Missing job label"}), 400

    job_id = _make_job_id_from_label(job_label)
    submitted_at = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    files_to_send = [
        ('executable', (executable.filename, executable.stream, executable.mimetype))
    ]
    
    for f in additional_files:
        if f.filename:
            files_to_send.append(('additional_files', (f.filename, f.stream, f.mimetype)))

    status = "pending"
    logs = (
        f"[{submitted_at}] Job queued\n"
        f"Executable: {executable.filename}\n"
        f"Label: {job_label or 'n/a'}\n"
    )

    if JOB_API_URL:
        try:
            response = requests.post(JOB_API_URL, files=files_to_send)
            try:
                gateway_payload = response.json()
            except ValueError:
                gateway_payload = {"raw": response.text}

            if 200 <= response.status_code < 300:
                status = gateway_payload.get("status", "pending")
                logs += f"Gateway accepted job\nResponse: {gateway_payload}"
                message = "Job submitted"
            else:
                status = "failed"
                logs += f"Gateway returned HTTP {response.status_code}\nResponse: {gateway_payload}"
                message = "Job submission failed at gateway"
        except requests.exceptions.RequestException:
            status = "failed"
            message = "Error connecting to gateway"
            logs += "Could not connect to upstream job API"
    else:
        message = "Job submitted (local mode)"
        logs += "No JOB_API_URL configured; stored locally only"

    job_record = {
        "id": job_id,
        "executableName": executable.filename,
        "additionalFilesList": [f.filename for f in additional_files if f.filename],
        "label": job_label,
        "status": status,
        "submittedAt": submitted_at,
        "logsCustom": logs,
    }
    jobs_store.insert(0, job_record)

    return flask.jsonify({"success": status != "failed", "jobId": job_id, "message": message}), 200


@app.route("/api/jobs", methods=["POST"])
def submit_job():
    return _submit_impl()


@app.route("/api/submit", methods=["POST"])
def submit_compat():
    return _submit_impl()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)