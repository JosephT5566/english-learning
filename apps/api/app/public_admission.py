"""Bounded process-local admission for anonymous content reads."""

import hashlib
import ipaddress
import math
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.config import Settings

SOURCE_CAPACITY = 4096
SOURCE_IDLE_SECONDS = 600


@dataclass(frozen=True)
class AdmissionRejection:
    reason: str
    retry_after_seconds: int


@dataclass
class _Bucket:
    tokens: float
    updated_at: float
    last_used_at: float


class PublicPermit:
    def __init__(self, admission: "PublicAdmission") -> None:
        self._admission = admission
        self._released = False

    def release(self) -> None:
        with self._admission._lock:
            if not self._released:
                self._released = True
                self._admission._in_flight -= 1


class PublicAdmission:
    def __init__(
        self, settings: Settings, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._salt = secrets.token_bytes(32)
        self._source_rate = settings.public_review_requests_per_minute / 60
        self._source_burst = settings.public_review_burst
        self._global_rate = settings.public_review_global_requests_per_minute / 60
        self._global_burst = settings.public_review_global_burst
        self._max_in_flight = settings.public_review_max_in_flight
        self._in_flight = 0
        now = clock()
        self._global = _Bucket(float(self._global_burst), now, now)
        self._sources: dict[str, _Bucket] = {}

    def client_key(self, address: str | None) -> str:
        try:
            parsed = ipaddress.ip_address(address or "")
            if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped:
                parsed = parsed.ipv4_mapped
            normalized = str(parsed)
        except ValueError:
            normalized = "unverified-source"
        return hashlib.blake2b(
            normalized.encode("ascii"), key=self._salt, digest_size=16
        ).hexdigest()

    @staticmethod
    def _refill(bucket: _Bucket, now: float, rate: float, capacity: int) -> None:
        bucket.tokens = min(
            capacity, bucket.tokens + max(0, now - bucket.updated_at) * rate
        )
        bucket.updated_at = now

    def try_acquire(self, client_key: str) -> PublicPermit | AdmissionRejection:
        with self._lock:
            now = self._clock()
            self._refill(self._global, now, self._global_rate, self._global_burst)
            source = self._sources.get(client_key)
            if source is None:
                expired = [
                    key
                    for key, bucket in self._sources.items()
                    if now - bucket.last_used_at >= SOURCE_IDLE_SECONDS
                    and bucket.tokens
                    + max(0, now - bucket.updated_at) * self._source_rate
                    >= self._source_burst
                ]
                for key in expired:
                    del self._sources[key]
                if len(self._sources) >= SOURCE_CAPACITY:
                    return AdmissionRejection("source_capacity", 1)
                source = _Bucket(float(self._source_burst), now, now)
                self._sources[client_key] = source
            self._refill(source, now, self._source_rate, self._source_burst)
            source.last_used_at = now
            delay = max(
                (1 - source.tokens) / self._source_rate,
                (1 - self._global.tokens) / self._global_rate,
            )
            if delay > 0:
                return AdmissionRejection("rate_limited", max(1, math.ceil(delay)))
            if self._in_flight >= self._max_in_flight:
                return AdmissionRejection("busy", 1)
            source.tokens -= 1
            self._global.tokens -= 1
            self._in_flight += 1
            return PublicPermit(self)
