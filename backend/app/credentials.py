from __future__ import annotations

from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True)
class ExchangeCredentials:
    api_key: str
    api_secret: str
    password: str


class InMemoryCredentialStore:
    """
    Stores exchange credentials in-memory only.
    Electron is responsible for persisting secrets in OS keychain.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._by_exchange: dict[str, ExchangeCredentials] = {}

    def set(self, exchange: str, api_key: str, api_secret: str, password: str = "") -> None:
        with self._lock:
            self._by_exchange[exchange.lower()] = ExchangeCredentials(
                api_key=api_key,
                api_secret=api_secret,
                password=password or "",
            )

    def get(self, exchange: str) -> ExchangeCredentials | None:
        with self._lock:
            return self._by_exchange.get(exchange.lower())

    def clear(self, exchange: str) -> None:
        with self._lock:
            self._by_exchange.pop(exchange.lower(), None)


credential_store = InMemoryCredentialStore()

