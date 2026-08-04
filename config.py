import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    BOT_TOKEN: str
    # Объявляем как строку, чтобы Pydantic не пытался автоматически парсить её в JSON
    ADMIN_IDS_RAW: str = ""

    @property
    def ADMIN_IDS(self) -> list[int]:
        """Динамически превращает строку из .env '123,456' в список чисел [123, 456]"""
        if not self.ADMIN_IDS_RAW:
            return []
        try:
            return [int(x.strip()) for x in self.ADMIN_IDS_RAW.split(",") if x.strip()]
        except ValueError:
            return []

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        extra="ignore"
    )

config = Settings()
