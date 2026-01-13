import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./shaggydog.db")

VISION_MODEL = os.getenv("VISION_MODEL", "gpt-4.1-mini")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gpt-image-1.5")
