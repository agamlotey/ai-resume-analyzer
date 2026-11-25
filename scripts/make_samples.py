import subprocess
import textwrap
from pathlib import Path

import docx
from docx.shared import Pt

OUT = Path(__file__).resolve().parent.parent / "samples"

RESUMES = {
    "resume_ml_student": """Riya Mehta
riya.mehta@example.com | +91 98765 43210 | github.com/riyamehta | linkedin.com/in/riyamehta

Summary
Final year B.Tech Computer Science student focused on machine learning and NLP. Built and deployed 4 ML projects used by 300+ students.

Education
B.Tech in Computer Science and Engineering, Thapar Institute of Engineering and Technology, 2022 - 2026, CGPA 8.7

Experience
Machine Learning Intern, DataWorks Pvt Ltd, May 2025 - July 2025
- Built a text classification model with scikit-learn and PyTorch that improved ticket routing accuracy by 18%.
- Cleaned 2 million rows of customer data using Pandas and NumPy.
- Deployed the model as a REST API with Flask and Docker on AWS EC2.

Projects
Resume Screener: NLP pipeline in Python that extracts skills from resumes; reduced manual screening time by 60%.
Crop Disease Detection: CNN in TensorFlow and Keras with 94% accuracy on 15,000 leaf images.
Sales Dashboard: data visualization with Matplotlib and Power BI for a college fest.

Skills
Python, SQL, Machine Learning, Deep Learning, NLP, PyTorch, TensorFlow, scikit-learn, Pandas, NumPy, Flask, Docker, Git, Linux, AWS

Achievements
Winner, Smart India Hackathon 2024 (software edition). Led a team of 5.
""",
    "resume_web_dev": """ARJUN SINGH
arjun.singh@example.com | 9876501234

Objective
Web developer who enjoys building clean user interfaces.

Education
Bachelor of Computer Applications (BCA), Punjab University, 2021 - 2024

Experience
Frontend Developer, PixelCraft Studio, 2024 - Present
- Developed responsive websites using HTML, CSS, JavaScript and React.
- Worked with designers in Figma and used Git for version control.

Projects
Portfolio website with React and Tailwind.
Weather app using JavaScript and a public REST API.

Skills
HTML, CSS, JavaScript, React, Tailwind CSS, Bootstrap, Git, GitHub, Figma, Communication
""",
}

JD = {
    "jd_backend_python.txt": """Backend Developer (Python)

We are hiring a Backend Developer to build APIs for our hiring platform.

Responsibilities:
- Design and build REST APIs in Python using Flask or FastAPI.
- Store data in PostgreSQL and Redis, and design schemas for scale.
- Containerize services with Docker and deploy them on AWS (EC2, S3, Lambda).
- Write unit tests with pytest and maintain CI/CD pipelines with GitHub Actions.

Requirements:
- 1+ years of experience building backend services (internships count).
- Bachelor's degree in Computer Science or related field.
- Strong Python, SQL, Git and Linux skills.
- Good communication and problem solving skills.
""",
}


def write_docx(name, text):
    document = docx.Document()
    document.core_properties.author = ""
    document.core_properties.last_modified_by = ""
    style = document.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)
    for line in text.strip().splitlines():
        document.add_paragraph(line)
    path = OUT / f"{name}.docx"
    document.save(path)
    return path


def write_pdf(name, text):
    txt = OUT / f"{name}.txt.tmp"
    txt.write_text("\n".join(textwrap.fill(l, 78) if l else "" for l in text.splitlines()))
    pdf = OUT / f"{name}.pdf"
    with open(pdf, "wb") as f:
        subprocess.run(["cupsfilter", "-m", "application/pdf", str(txt)], stdout=f, stderr=subprocess.DEVNULL, check=True)
    txt.unlink()
    return pdf


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for name, text in RESUMES.items():
        print(write_docx(name, text))
    print(write_pdf("resume_ml_student", RESUMES["resume_ml_student"]))
    for name, text in JD.items():
        (OUT / name).write_text(text)
        print(OUT / name)
