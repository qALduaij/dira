import json
import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def http_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or any(c.isspace() for c in value):
        raise ValueError("source must be an HTTP(S) URL")
    return value


class Channel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    enabled: bool = False
    extractor: Literal["yt-dlp", "streamlink"] = "yt-dlp"
    source_url: str = ""
    source_url_file: Path | None = None
    cookie_file: Path | None = None
    quality: str = "best"
    refresh_seconds: int = Field(default=300, ge=10, le=86400)

    @model_validator(mode="after")
    def validate_source(self):
        if self.source_url:
            http_url(self.source_url)
        if self.source_url and self.source_url_file:
            raise ValueError("choose source_url or source_url_file")
        if self.enabled and not (self.source_url or self.source_url_file):
            raise ValueError("enabled channel requires an operator-supplied source")
        return self

    def source(self):
        return http_url(self.source_url_file.read_text().strip() if self.source_url_file else self.source_url)


class Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    domain_proxies: dict[str, str] = Field(default_factory=dict)
    channels: list[Channel]

    @model_validator(mode="after")
    def validate_catalog(self):
        if len({c.id for c in self.channels}) != len(self.channels):
            raise ValueError("duplicate channel ID")
        for domain, env in self.domain_proxies.items():
            if not domain or domain != domain.lower().strip(".") or any(x in domain for x in "/:@ *"):
                raise ValueError("proxy rules require lowercase DNS names")
            if not env or not env.isidentifier():
                raise ValueError("proxy value must be an environment variable name")
        return self

    @classmethod
    def load(cls, path: Path):
        return cls.model_validate(json.loads(path.read_text()))

    def channel(self, channel_id: str):
        channel = next((c for c in self.channels if c.id == channel_id), None)
        if channel is None:
            raise KeyError(channel_id)
        if not channel.enabled:
            raise ValueError("channel disabled")
        return channel


def proxy_for(url: str, routes: dict[str, str]) -> str | None:
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    matches = [d for d in routes if host == d or host.endswith("." + d)]
    if not matches:
        return None
    value = os.environ.get(routes[max(matches, key=len)], "")
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https", "socks5", "socks5h") or not parsed.hostname:
        raise ValueError("required regional proxy is missing or invalid")
    return value


class ExtractorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DIRA_EXTRACTOR_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )
    config: Path = Path("infra/extractors.json")
    token: str = ""
    publish_base: str = "rtsp://127.0.0.1:8554"
    startup_timeout: float = Field(default=75, ge=1, le=300)
    stall_timeout: float = Field(default=30, ge=1, le=300)
    retry_seconds: float = Field(default=2, ge=0.1, le=30)
    max_retry_seconds: float = Field(default=30, ge=1, le=300)

    @model_validator(mode="after")
    def validate_destination(self):
        parsed = urlsplit(self.publish_base)
        if (
            parsed.scheme != "rtsp"
            or not parsed.hostname
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ValueError("publish_base must be a credential-free internal RTSP address")
        if self.retry_seconds > self.max_retry_seconds:
            raise ValueError("retry interval exceeds maximum")
        return self
