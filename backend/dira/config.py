from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DIRA_", env_file=".env", extra="ignore")
    mode: Literal["simulation", "live"] = "simulation"
    data_dir: Path = Path(".data")
    api_token: str = ""
    allowed_hosts: str = "127.0.0.1,localhost,::1,testserver"
    allow_external_ingest: bool = False
    min_disk_free_gb: float = Field(default=2, ge=0, le=1000)
    media_timeout: float = Field(default=20, ge=1, le=300)
    allowed_origins: str = (
        "http://127.0.0.1:8000,http://localhost:8000,http://127.0.0.1:5173,http://localhost:5173"
    )
    qdrant_url: str = ""
    qdrant_path: str = ""
    embedding_model: str = ""
    embedding_dimension: int = Field(default=256, ge=16, le=4096)
    device: Literal["auto", "cpu", "mps", "cuda"] = "auto"
    router: Literal["anchors", "aurelio"] = "anchors"
    llm_url: str = ""
    llm_model: str = "local"
    llm_provider: Literal["local", "cloud"] = "local"
    cloud_auto_briefs: bool = False
    llm_api_key: str = ""
    asr_url: str = "ws://127.0.0.1:8001/asr"
    # Seconds of transcription backlog before a channel's speech restarts at the live edge; 0 disables.
    asr_max_lag: float = Field(default=90, ge=0, le=3600)
    hot_capacity: int = Field(default=4000, ge=10, le=100000)
    hot_seconds: int = Field(default=7200, ge=1)
    outbox_limit: int = Field(default=50000, ge=100)
    simulation_interval: float = Field(default=2.5, ge=0.1)
    brief_hour: int = Field(default=6, ge=0, le=23)
    narrative_interval: int = Field(default=300, ge=30)
    feed_config: Path = Path("infra/feeds.json")
    enable_ocr: bool = False
    video_hwaccel: Literal["auto", "none", "videotoolbox"] = "auto"
    ffmpeg_threads: int = Field(default=1, ge=1, le=8)
    ocr_model_dir: str = ""
    ocr_detection_model: str = "PP-OCRv6_small_det"
    ocr_recognition_model: str = "arabic_PP-OCRv5_mobile_rec"
    ocr_cpu_threads: int = Field(default=1, ge=1, le=16)
    diarization_model: str = ""
    visual_model: str = ""

    @model_validator(mode="after")
    def live_requirements(self):
        if self.mode == "live" and not self.embedding_model:
            raise ValueError("live mode requires DIRA_EMBEDDING_MODEL pointing to local weights")
        if self.router == "aurelio" and not self.embedding_model:
            raise ValueError("Aurelio requires a local embedding model")
        return self
