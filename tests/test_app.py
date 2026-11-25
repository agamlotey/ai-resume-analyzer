import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = tempfile.mkdtemp()
os.environ.update(APP_MODE="local", DATA_DIR=TMP, SECRET_KEY="test", ADMIN_EMAIL="admin@test.com",
                  ADMIN_PASSWORD="Admin12345")
sys.path.insert(0, str(ROOT / "backend"))

import nlp  # noqa: E402
import seed  # noqa: E402
from app import app, auth, store  # noqa: E402

SAMPLES = ROOT / "samples"


class NlpTests(unittest.TestCase):
    def test_skill_aliases(self):
        found = nlp.find_skills("Worked with ReactJS, node.js, sklearn, C++ and Amazon Web Services")
        for skill in ("React", "Node.js", "scikit-learn", "C++", "AWS"):
            self.assertIn(skill, found)

    def test_no_false_positives(self):
        found = nlp.find_skills("JavaScript developer, mysql user, rest of the team in spring 2024")
        self.assertNotIn("Java", found)
        self.assertNotIn("SQL", found)
        self.assertNotIn("REST APIs", found)
        self.assertNotIn("Spring Boot", found)

    def test_experience_ranges(self):
        self.assertAlmostEqual(nlp.years_from_ranges("May 2025 - July 2025"), 0.25)
        self.assertAlmostEqual(nlp.years_from_ranges("2021 - 2024"), 3.0)
        self.assertEqual(nlp.jd_years("Requires 2+ years of experience"), 2)

    def test_education(self):
        self.assertEqual(nlp.education_level("B.Tech in Computer Science")[1], "Bachelor's")
        self.assertEqual(nlp.education_level("M.Tech from IIT")[1], "Master's")

    def test_pdf_and_docx_extract(self):
        for name in ("resume_ml_student.pdf", "resume_ml_student.docx"):
            text = nlp.extract_text(name, (SAMPLES / name).read_bytes())
            self.assertIn("Riya Mehta", text)

    def test_match_ranks_right_job_higher(self):
        resume = (SAMPLES / "resume_ml_student.docx").read_bytes()
        text = nlp.extract_text("r.docx", resume)
        jobs = {j["id"]: j["description"] for j in seed.JOBS}
        ml = nlp.match(text, jobs["job-ml-intern"])["score"]
        web = nlp.match(text, jobs["job-fullstack"])["score"]
        self.assertGreater(ml, web + 20)


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed.seed(store, auth)
        cls.client = app.test_client()

    def login(self, email, password):
        res = self.client.post("/api/auth/login", json={"email": email, "password": password})
        self.assertEqual(res.status_code, 200, res.get_json())
        return {"Authorization": "Bearer " + res.get_json()["token"]}

    def test_full_flow(self):
        res = self.client.post("/api/auth/register", json={"email": "riya@test.com", "password": "Riya12345", "name": "Riya"})
        self.assertEqual(res.status_code, 201, res.get_json())
        user = {"Authorization": "Bearer " + res.get_json()["token"]}

        self.assertEqual(self.client.get("/api/jobs").status_code, 401)
        jobs = self.client.get("/api/jobs", headers=user).get_json()["jobs"]
        self.assertEqual(len(jobs), len(seed.JOBS))

        data = {"job_id": "job-ml-intern",
                "resume": (io.BytesIO((SAMPLES / "resume_ml_student.pdf").read_bytes()), "resume.pdf")}
        res = self.client.post("/api/analyze", headers=user, data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 201, res.get_json())
        match = res.get_json()["match"]
        self.assertGreater(match["score"], 60)

        history = self.client.get("/api/matches", headers=user).get_json()["matches"]
        self.assertEqual(history[0]["id"], match["id"])
        file = self.client.get(f"/api/matches/{match['id']}/resume", headers=user)
        self.assertEqual(file.status_code, 200)
        self.assertTrue(file.data.startswith(b"%PDF"))

        self.assertEqual(self.client.post("/api/jobs", headers=user, json={"title": "x"}).status_code, 403)
        self.assertEqual(self.client.get("/api/stats", headers=user).status_code, 403)

        other = self.client.post("/api/auth/register", json={"email": "sam@test.com", "password": "Sam123456"})
        other_h = {"Authorization": "Bearer " + other.get_json()["token"]}
        self.assertEqual(self.client.get(f"/api/matches/{match['id']}", headers=other_h).status_code, 404)

        admin = self.login("admin@test.com", "Admin12345")
        self.assertEqual(self.client.get(f"/api/matches/{match['id']}", headers=admin).status_code, 200)
        res = self.client.post("/api/jobs", headers=admin, json={
            "title": "DevOps Intern", "description": "Work with Docker, Kubernetes, Jenkins and AWS on Linux servers."})
        self.assertEqual(res.status_code, 201)
        self.assertIn("Kubernetes", res.get_json()["job"]["skills"])
        stats = self.client.get("/api/stats", headers=admin).get_json()
        self.assertGreaterEqual(stats["total_matches"], 1)

    def test_custom_jd_and_bad_input(self):
        h = self.login("admin@test.com", "Admin12345")
        jd = (SAMPLES / "jd_backend_python.txt").read_text()
        data = {"job_description": jd, "job_title": "Backend",
                "resume": (io.BytesIO((SAMPLES / "resume_web_dev.docx").read_bytes()), "web.docx")}
        res = self.client.post("/api/analyze", headers=h, data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 201)
        bad = {"job_description": jd, "resume": (io.BytesIO(b"hello"), "x.exe")}
        res = self.client.post("/api/analyze", headers=h, data=bad, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 400)
        res = self.client.post("/api/auth/login", json={"email": "admin@test.com", "password": "wrong"})
        self.assertEqual(res.status_code, 401)


if __name__ == "__main__":
    unittest.main()
