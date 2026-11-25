import argparse
import json
import threading
import time
import urllib.request
import uuid
from collections import Counter
from pathlib import Path

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "resume_ml_student.docx"


def post_json(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())


def analyze(base, token, data):
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"job_id\"\r\n\r\njob-ml-intern\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"resume\"; filename=\"resume.docx\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(base + "/api/analyze", data=body, headers={
        "Authorization": "Bearer " + token, "Content-Type": f"multipart/form-data; boundary={boundary}"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def main():
    parser = argparse.ArgumentParser(description="Send many analyze requests to show auto scaling and load balancing")
    parser.add_argument("url")
    parser.add_argument("--email", default="admin@demo.com")
    parser.add_argument("--password", default="Admin12345")
    parser.add_argument("--threads", type=int, default=20)
    parser.add_argument("--minutes", type=float, default=5)
    args = parser.parse_args()

    base = args.url.rstrip("/")
    token = post_json(base + "/api/auth/login", {"email": args.email, "password": args.password})["token"]
    data = SAMPLE.read_bytes()
    stop = time.time() + args.minutes * 60
    served, errors, lock = Counter(), Counter(), threading.Lock()

    def worker():
        while time.time() < stop:
            try:
                result = analyze(base, token, data)
                with lock:
                    served[result["served_by"]] += 1
            except Exception as e:
                with lock:
                    detail = getattr(e, "code", "") or getattr(e, "reason", "")
                    errors[(type(e).__name__ + " " + str(detail)).strip()] += 1

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(args.threads)]
    for t in threads:
        t.start()
    while any(t.is_alive() for t in threads):
        time.sleep(10)
        with lock:
            print(time.strftime("%H:%M:%S"), "requests per instance:", dict(served), "errors:", dict(errors))


if __name__ == "__main__":
    main()
