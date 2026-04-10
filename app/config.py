import os


class Settings:
    secret_key: str = os.getenv("ATTENDANCE_SECRET_KEY", "dev-change-me")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))
    checkin_rate_limit_per_minute: int = int(os.getenv("CHECKIN_RATE_LIMIT_PER_MINUTE", "120"))


settings = Settings()
