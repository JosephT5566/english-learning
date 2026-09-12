from unittest.mock import Mock

import pytest

from app import serve


def test_load_port_uses_platform_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PORT", raising=False)

    assert serve.load_port() == 8080


@pytest.mark.parametrize("port", ["1", "8080", "65535"])
def test_load_port_accepts_valid_tcp_port(
    monkeypatch: pytest.MonkeyPatch, port: str
) -> None:
    monkeypatch.setenv("PORT", port)

    assert serve.load_port() == int(port)


@pytest.mark.parametrize("port", ["", "not-a-port", "0", "65536"])
def test_load_port_rejects_invalid_value(
    monkeypatch: pytest.MonkeyPatch, port: str
) -> None:
    monkeypatch.setenv("PORT", port)

    with pytest.raises(RuntimeError, match="Invalid PORT"):
        serve.load_port()


def test_main_binds_all_interfaces_and_configures_graceful_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = Mock()
    monkeypatch.setattr(serve.uvicorn, "run", run)
    monkeypatch.setenv("PORT", "9000")

    serve.main()

    run.assert_called_once_with(
        "app.main:create_app",
        factory=True,
        host="0.0.0.0",
        port=9000,
        timeout_graceful_shutdown=8,
    )
