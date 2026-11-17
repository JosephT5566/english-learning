"""Exchange fake Google credentials for real app tokens in product HTTP tests."""

from fastapi.testclient import TestClient


def access_headers(client: TestClient, credential: str) -> dict[str, str]:
    tokens = getattr(client, "_test_access_tokens", None)
    if tokens is None:
        tokens = {}
        client._test_access_tokens = tokens
    if credential not in tokens:
        response = client.post("/v1/auth/session", json={"credential": credential})
        assert response.status_code == 200
        tokens[credential] = response.json()["access_token"]
    return {"Authorization": f"Bearer {tokens[credential]}"}
