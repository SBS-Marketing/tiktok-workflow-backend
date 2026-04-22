from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    pexels_api_key: str = ""
    zernio_api_key: str = ""
    zernio_api_url: str = "https://zernio.com/api/v1"
    supabase_url: str = "https://rqwvmqffwjskzhhumrdf.supabase.co"
    supabase_key: str = ""
    media_dir: str = "./media"
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> list:
        origins = [o.strip() for o in self.cors_origins.split(",")]
        # "*" means allow all (use in Railway with Lovable frontend)
        if "*" in origins:
            return ["*"]
        return origins


settings = Settings()
