from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import config


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id():
    return uuid.uuid4().hex[:12]


class SqliteStore:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, email TEXT UNIQUE, name TEXT,
                    password_hash TEXT, role TEXT, created_at TEXT);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, title TEXT, company TEXT, location TEXT,
                    description TEXT, skills TEXT, created_by TEXT, created_at TEXT);
                CREATE TABLE IF NOT EXISTS matches (
                    id TEXT PRIMARY KEY, user_id TEXT, user_email TEXT, job_id TEXT,
                    job_title TEXT, resume_key TEXT, resume_name TEXT, score REAL,
                    verdict TEXT, result TEXT, created_at TEXT);
            """)

    def _run(self, sql, args=()):
        with self.lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur

    def create_user(self, email, name, password_hash, role="user"):
        user = {"id": new_id(), "email": email.lower(), "name": name, "password_hash": password_hash,
                "role": role, "created_at": now_iso()}
        self._run("INSERT INTO users VALUES (:id,:email,:name,:password_hash,:role,:created_at)", user)
        return user

    def get_user_by_email(self, email):
        row = self._run("SELECT * FROM users WHERE email=?", (email.lower(),)).fetchone()
        return dict(row) if row else None

    def put_job(self, job):
        row = dict(job, skills=json.dumps(job.get("skills", [])))
        self._run("INSERT OR REPLACE INTO jobs VALUES (:id,:title,:company,:location,:description,:skills,:created_by,:created_at)", row)
        return job

    def _job(self, row):
        job = dict(row)
        job["skills"] = json.loads(job["skills"] or "[]")
        return job

    def list_jobs(self):
        rows = self._run("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        return [self._job(r) for r in rows]

    def get_job(self, job_id):
        row = self._run("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self._job(row) if row else None

    def delete_job(self, job_id):
        self._run("DELETE FROM jobs WHERE id=?", (job_id,))

    def put_match(self, match):
        row = dict(match, result=json.dumps(match["result"]))
        self._run("INSERT INTO matches VALUES (:id,:user_id,:user_email,:job_id,:job_title,:resume_key,:resume_name,:score,:verdict,:result,:created_at)", row)
        return match

    def _match(self, row, full):
        match = dict(row)
        result = json.loads(match.pop("result"))
        if full:
            match["result"] = result
        return match

    def list_matches(self, user_id=None):
        if user_id:
            rows = self._run("SELECT * FROM matches WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()
        else:
            rows = self._run("SELECT * FROM matches ORDER BY created_at DESC").fetchall()
        return [self._match(r, False) for r in rows]

    def get_match(self, match_id):
        row = self._run("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
        return self._match(row, True) if row else None


def _to_dynamo(value):
    if isinstance(value, float):
        return Decimal(str(value))
    return value


def _from_dynamo(item):
    out = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            v = float(v)
        out[k] = v
    return out


class DynamoStore:
    def __init__(self):
        import boto3
        db = boto3.resource("dynamodb", region_name=config.AWS_REGION)
        self.jobs = db.Table(config.JOBS_TABLE)
        self.matches = db.Table(config.MATCHES_TABLE)

    def _scan(self, table):
        items, kwargs = [], {}
        while True:
            page = table.scan(**kwargs)
            items.extend(page.get("Items", []))
            if "LastEvaluatedKey" not in page:
                return items
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    def put_job(self, job):
        self.jobs.put_item(Item={k: _to_dynamo(v) for k, v in job.items()})
        return job

    def list_jobs(self):
        jobs = [_from_dynamo(i) for i in self._scan(self.jobs)]
        return sorted(jobs, key=lambda j: j.get("created_at", ""), reverse=True)

    def get_job(self, job_id):
        item = self.jobs.get_item(Key={"id": job_id}).get("Item")
        return _from_dynamo(item) if item else None

    def delete_job(self, job_id):
        self.jobs.delete_item(Key={"id": job_id})

    def put_match(self, match):
        item = {k: _to_dynamo(v) for k, v in match.items()}
        item["result"] = json.dumps(match["result"])
        self.matches.put_item(Item=item)
        return match

    def list_matches(self, user_id=None):
        if user_id:
            from boto3.dynamodb.conditions import Key
            items, kwargs = [], {"IndexName": "user_id-index", "KeyConditionExpression": Key("user_id").eq(user_id),
                                 "ScanIndexForward": False}
            while True:
                page = self.matches.query(**kwargs)
                items.extend(page.get("Items", []))
                if "LastEvaluatedKey" not in page:
                    break
                kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
        else:
            items = self._scan(self.matches)
        out = []
        for item in items:
            match = _from_dynamo(item)
            match.pop("result", None)
            out.append(match)
        return sorted(out, key=lambda m: m.get("created_at", ""), reverse=True)

    def get_match(self, match_id):
        item = self.matches.get_item(Key={"id": match_id}).get("Item")
        if not item:
            return None
        match = _from_dynamo(item)
        match["result"] = json.loads(match["result"])
        return match


def create_store():
    if config.is_aws():
        return DynamoStore()
    return SqliteStore(config.DATA_DIR / "app.db")
