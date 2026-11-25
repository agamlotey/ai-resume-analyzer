import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent


def _load_env_file():
    env_path = PROJECT_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_env_file()

APP_MODE = os.getenv("APP_MODE", "local")
AWS_REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))

DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_DIR / "data"))
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")

S3_BUCKET = os.getenv("S3_BUCKET", "")
JOBS_TABLE = os.getenv("JOBS_TABLE", "")
MATCHES_TABLE = os.getenv("MATCHES_TABLE", "")
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID", "")
COGNITO_CLIENT_ID = os.getenv("COGNITO_CLIENT_ID", "")

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@demo.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

MAX_UPLOAD_MB = 5
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def is_aws():
    return APP_MODE == "aws"
