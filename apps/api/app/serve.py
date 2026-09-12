"""Production HTTP process entrypoint."""

import os

import uvicorn

DEFAULT_PORT = 8080
GRACEFUL_SHUTDOWN_SECONDS = 8


def load_port() -> int:
    """Return the platform-provided port after bounded validation."""

    raw_port = os.environ.get("PORT", str(DEFAULT_PORT))
    try:
        port = int(raw_port)
    except ValueError:
        raise RuntimeError(
            "Invalid PORT; expected an integer from 1 through 65535."
        ) from None

    if not 1 <= port <= 65535:
        raise RuntimeError("Invalid PORT; expected an integer from 1 through 65535.")
    return port


def main() -> None:
    """Run one Uvicorn process and leave signal handling to the server."""

    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host="0.0.0.0",
        port=load_port(),
        timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_SECONDS,
    )


if __name__ == "__main__":
    main()
