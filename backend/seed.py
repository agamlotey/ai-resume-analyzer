import config
import nlp
from auth import create_auth
from store import create_store, now_iso

JOBS = [
    {
        "id": "job-ml-intern",
        "title": "Machine Learning Intern",
        "company": "Nimbus Analytics",
        "location": "Bengaluru (Hybrid)",
        "description": """We are looking for a Machine Learning Intern to join our data science team.

Responsibilities:
- Build and evaluate machine learning models using Python, scikit-learn and PyTorch.
- Clean and analyze large datasets with Pandas and NumPy, and present insights with data visualization.
- Work on NLP features such as text classification and keyword extraction.
- Deploy models as REST APIs using Flask or FastAPI and Docker on AWS.

Requirements:
- Pursuing a B.Tech or Bachelor's degree in Computer Science or a related field.
- Strong Python and SQL skills, good understanding of statistics and machine learning.
- Familiarity with Git, Linux and deep learning frameworks such as TensorFlow or PyTorch.
- Good communication and teamwork skills.""",
    },
    {
        "id": "job-cloud-dev",
        "title": "Junior Cloud Developer",
        "company": "Stratus Cloud Labs",
        "location": "Remote",
        "description": """Junior Cloud Developer

You will build and operate cloud-native applications on AWS.

What you will do:
- Develop serverless and container-based services using AWS Lambda, EC2, S3 and DynamoDB.
- Write infrastructure as code with CloudFormation or Terraform.
- Build CI/CD pipelines with GitHub Actions or Jenkins, and containerize apps with Docker and Kubernetes.
- Write REST APIs in Python or Node.js and monitor them with CloudWatch.

What we need:
- 1+ years of experience with AWS (internships count).
- Bachelor's degree in Computer Science, IT or similar.
- Solid Linux, Git and Python skills; knowledge of NoSQL and SQL databases.
- Problem solving mindset and teamwork.""",
    },
    {
        "id": "job-fullstack",
        "title": "Full Stack Developer",
        "company": "Brightpath Software",
        "location": "Gurugram",
        "description": """Full Stack Developer (MERN)

Responsibilities:
- Build responsive web applications using React, JavaScript, TypeScript, HTML and CSS.
- Develop backend services with Node.js and Express, and design REST APIs.
- Work with MongoDB and PostgreSQL databases.
- Write unit tests with Jest and take part in agile sprints using Jira.

Requirements:
- 2+ years of experience in full stack web development.
- Bachelor's degree in Engineering or equivalent.
- Experience with Git, Docker and deploying to AWS or Azure.
- Strong communication and problem solving skills.""",
    },
    {
        "id": "job-data-analyst",
        "title": "Data Analyst",
        "company": "Kestrel Retail",
        "location": "Mumbai",
        "description": """Data Analyst

Responsibilities:
- Analyze sales and customer data using SQL, Excel and Python (Pandas).
- Build dashboards in Power BI or Tableau and present findings to business teams.
- Apply statistics to find trends, run A/B tests and support decision making.

Requirements:
- 1-3 years of experience in data analysis.
- Bachelor's degree in Statistics, Mathematics, Computer Science or related.
- Strong Excel, SQL and data visualization skills; excellent communication.""",
    },
]


def seed(store, auth):
    existing = {j["id"] for j in store.list_jobs()}
    for job in JOBS:
        if job["id"] in existing:
            continue
        store.put_job(dict(job, skills=nlp.parse_jd(job["description"])["skills"],
                           created_by=config.ADMIN_EMAIL, created_at=now_iso()))
        print("added job:", job["title"])
    if config.ADMIN_PASSWORD:
        auth.create_admin(config.ADMIN_EMAIL, config.ADMIN_PASSWORD)
        print("admin account ready:", config.ADMIN_EMAIL)
    else:
        print("ADMIN_PASSWORD not set, skipping admin account")


if __name__ == "__main__":
    s = create_store()
    seed(s, create_auth(s))
