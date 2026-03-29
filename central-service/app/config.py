import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://imsor:imsor_dev_password@localhost:5432/imsor",
)

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
