"""Execute the release smoke against a local curl boundary stub, without sockets."""

import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[4]
SCRIPT = ROOT / "deploy/cloud-run/smoke.sh"
GOOGLE = "synthetic-google-token-never-print"
ACCESS = "ela_synthetic-never-print"
REFRESH = "elr_synthetic-never-print"
DECK = "11111111-1111-4111-8111-111111111111"
CARD = "22222222-2222-4222-8222-222222222222"

STUB = r"""
import json, os, pathlib, sys
from urllib.parse import urlsplit, parse_qs
a=sys.argv[1:]
def arg(flag, default=None):
    return a[a.index(flag)+1] if flag in a else default
url=next(x for x in a if x.startswith("https://"))
path=urlsplit(url).path
method=arg("--request", "GET")
headers={}
for i,x in enumerate(a):
    if x=="--header":
        h=a[i+1]
        for line in (pathlib.Path(h[1:]).read_text().splitlines() if h.startswith("@") else [h]):
            k,v=line.split(":",1); headers[k.lower()]=v.strip()
raw=arg("--data-binary", arg("--data"))
raw=pathlib.Path(raw[1:]).read_text() if raw and raw.startswith("@") else raw
body=json.loads(raw) if raw else None
p=pathlib.Path(os.environ["SMOKE_STUB_STATE"])
s=json.loads(p.read_text())
s["requests"].append({"method":method,"path":path,"query":parse_qs(urlsplit(url).query),"body":body,"headers":headers})
status=200; result={}
google="synthetic-google-token-never-print"; access="ela_synthetic-never-print"; refresh="elr_synthetic-never-print"
deck="11111111-1111-4111-8111-111111111111"; card="22222222-2222-4222-8222-222222222222"
def tokens(suffix=""):
    return {"access_token":access+suffix,"refresh_token":refresh+suffix,"user":{"id":1,"email":"private-smoke@example.invalid"}}
if path.startswith("/health/"): pass
elif path=="/v1/auth/session":
    assert body=={"credential":google}; result=tokens()
elif path=="/v1/me":
    if headers.get("authorization")=="Bearer "+google or s.get("logout") or s.get("revoked"):
        status=401
    else: result={"id":1,"email":"private-smoke@example.invalid"}
elif path=="/v1/decks" and method=="GET":
    # Existing deck is deliberately on page two, never assume the first page.
    result={"items":[],"next_cursor":"page two"} if "cursor" not in parse_qs(urlsplit(url).query) else {"items":([{ "id":deck,"title":"Release smoke (synthetic)","target_language":"en","explanation_language":"en"}] if s["existing"] else []),"next_cursor":None}
elif path=="/v1/decks":
    assert body=={"title":"Release smoke (synthetic)","target_language":"en","explanation_language":"en"}
    status=201; result={"id":deck}
elif path=="/v1/cards" and method=="POST":
    assert body["deck_id"]==deck and body["term"] and body["meaning"]
    assert headers.get("idempotency-key")
    status=201; result={"id":card,"review_state":{"version":1,"next_review_at":"2000-01-01T00:00:00Z"}}
elif path=="/v1/reviews":
    expected={"items":[{"card_id":card,"decision":"yes_a_bit","expected_version":1}]}
    assert body==expected
    previous=s.get("review")
    if previous: assert previous=={"body":body,"key":headers.get("idempotency-key")}
    s["review"]={"body":body,"key":headers.get("idempotency-key")}
    result={"batch_id":"batch","items":[{"card_id":card}]}
    if previous and s.get("bad_replay"): result["batch_id"]="different"
elif path=="/v1/cards/"+card and method=="DELETE":
    status=204; s["archived"]=True
elif path=="/v1/auth/refresh":
    assert body=={"refresh_token":refresh}
    if s.get("rotated"):
        status=401 if s["outside"] else 409
        result={"error":{"code":"refresh_reused" if s["outside"] else "refresh_superseded"}}
        s["revoked"]=s["outside"]
    else: result=tokens("_rotated"); s["rotated"]=True
elif path=="/v1/auth/logout":
    assert body=={"refresh_token":refresh+("_rotated" if s.get("rotated") else "")}
    status=204; s["logout"]=True
else: raise AssertionError("unexpected request")
if s.get("fail_exchange") and path=="/v1/auth/session":
    status=403; result={"error":{"message":google+access+refresh+"private-smoke@example.invalid"}}
p.write_text(json.dumps(s))
output=arg("--output")
if output: pathlib.Path(output).write_text(json.dumps(result) if status!=204 else "")
if "--write-out" in a: print(status,end="")
"""


def run_smoke(
    tmp_path: Path, **options: bool
) -> tuple[subprocess.CompletedProcess, dict]:
    binary = tmp_path / "bin"
    binary.mkdir()
    (binary / "python3").symlink_to(sys.executable)
    curl = binary / "curl"
    curl.write_text(f"#!{sys.executable}\n" + STUB)
    curl.chmod(0o700)
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps({"requests": [], "existing": False, "outside": False, **options})
    )
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    result = subprocess.run(
        ["bash", "-x", str(SCRIPT), "https://candidate.invalid"],
        env={
            "PATH": f"{binary}{os.pathsep}{os.defpath}",
            "RELEASE_SMOKE_ID_TOKEN": GOOGLE,
            "SMOKE_STUB_STATE": str(state),
            "TMPDIR": str(temporary),
        },
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    for private in (
        GOOGLE,
        ACCESS,
        REFRESH,
        "private-smoke@example.invalid",
        "Synthetic release verification card",
        "release-smoke-",
    ):
        assert private not in result.stdout + result.stderr
    assert list(temporary.iterdir()) == []
    return result, json.loads(state.read_text())


@pytest.mark.parametrize("existing,outside", [(False, False), (True, True)])
def test_machine_smoke_order_rotation_archive_and_safe_output(
    tmp_path, existing, outside
):
    result, state = run_smoke(tmp_path, existing=existing, outside=outside)
    assert result.returncode == 0
    expected = [
        ("GET", "/health/live"),
        ("GET", "/health/ready"),
        ("GET", "/v1/me"),
        ("POST", "/v1/auth/session"),
        ("GET", "/v1/me"),
        ("GET", "/v1/decks"),
        ("GET", "/v1/decks"),
    ]
    if not existing:
        expected.append(("POST", "/v1/decks"))
    expected += [
        ("POST", "/v1/cards"),
        ("POST", "/v1/reviews"),
        ("POST", "/v1/reviews"),
        ("DELETE", f"/v1/cards/{CARD}"),
        ("POST", "/v1/auth/refresh"),
        ("POST", "/v1/auth/refresh"),
        ("POST", "/v1/auth/logout"),
        ("GET", "/v1/me"),
    ]
    assert [(r["method"], r["path"]) for r in state["requests"]] == expected
    assert state["archived"] and state["logout"]
    assert "review_replay_identical=true" in result.stdout


@pytest.mark.parametrize("options", [{"fail_exchange": True}, {"bad_replay": True}])
def test_machine_smoke_failure_is_content_safe_and_cleans_up(tmp_path, options):
    result, state = run_smoke(tmp_path, **options)
    assert result.returncode != 0
    assert "smoke_passed=false" in result.stderr
    if options.get("bad_replay"):
        assert state["archived"]


def test_smoke_workflow_uses_machine_identity_and_optional_ttls(tmp_path):
    workflow = (ROOT / ".github/workflows/smoke-api-candidate.yml").read_text()
    assert "google_id_token" not in workflow
    assert workflow.count("uses: google-github-actions/auth@v3") == 2
    assert "service_account: ${{ env.GCP_GITHUB_SERVICE_ACCOUNT }}" in workflow
    assert "service_account: ${{ vars.RELEASE_SMOKE_EMAIL }}" in workflow
    assert "environment: production" in workflow
    assert "id-token: write" in workflow
    assert workflow.index("- name: Resolve tagged candidate") < workflow.index(
        "- name: Authenticate smoke principal"
    )
    for field in (
        "token_format: id_token",
        "id_token_include_email: true",
        "create_credentials_file: false",
        "vars.RELEASE_SMOKE_EMAIL",
        "vars.RELEASE_SMOKE_AUDIENCE",
        "::add-mask::",
    ):
        assert field in workflow

    environment = candidate_environment(tmp_path, {})
    for name in SMOKE_SETTINGS + TTL_SETTINGS:
        assert f"|{name}=" not in environment
    for name in TTL_SETTINGS:
        environment = candidate_environment(tmp_path, {name: "123"})
        assert f"|{name}=123" in environment
        for other in set(TTL_SETTINGS) - {name}:
            assert f"|{other}=" not in environment
    environment = candidate_environment(tmp_path, {SMOKE_SETTINGS[0]: "synthetic"})
    assert "|RELEASE_SMOKE_AUDIENCE=synthetic" in environment
    assert "|RELEASE_SMOKE_SUBJECT=|RELEASE_SMOKE_EMAIL=" in environment


SMOKE_SETTINGS = (
    "RELEASE_SMOKE_AUDIENCE",
    "RELEASE_SMOKE_SUBJECT",
    "RELEASE_SMOKE_EMAIL",
)
TTL_SETTINGS = (
    "AUTH_ACCESS_TTL_SECONDS",
    "AUTH_REFRESH_IDLE_TTL_SECONDS",
    "AUTH_REFRESH_ABSOLUTE_TTL_SECONDS",
    "AUTH_REFRESH_REUSE_GRACE_SECONDS",
)


def candidate_environment(tmp_path: Path, values: dict[str, str]) -> str:
    workflow = (ROOT / ".github/workflows/deploy-api-candidate.yml").read_text()
    step = workflow.split("- name: Deploy zero-traffic candidate\n", 1)[1]
    step = step.split("\n      - name:", 1)[0]
    program = textwrap.dedent(step.split("run: |\n", 1)[1])
    fragment, separator, _ = program.partition("\ngcloud run deploy ")
    assert separator
    # Model Actions substitution, then execute only environment assembly, never gcloud.
    fragment = re.sub(
        r"\$\{\{ vars\.(\w+) \}\}",
        lambda match: values.get(match[1], ""),
        fragment,
    )
    bindings = re.findall(
        r"^      (\w+): \$\{\{ vars\.(\w+) \}\}$", workflow, re.MULTILINE
    )
    marker = tmp_path / "command-executed"
    result = subprocess.run(
        ["bash", "-c", fragment + '\nprintf "%s" "${environment_variables}"'],
        env={
            **{name: values.get(source, "") for name, source in bindings},
            "PATH": os.defpath,
            "PROBE": str(marker),
        },
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not marker.exists(), "Configuration executed a shell command"
    return result.stdout


@pytest.mark.parametrize("name", SMOKE_SETTINGS + TTL_SETTINGS)
@pytest.mark.parametrize(
    "payload",
    [
        '$(printf executed > "${PROBE}")',
        'synthetic \' " ; & * ? `printf executed > "${PROBE}"` \\\nline',
    ],
)
def test_candidate_configuration_is_literal(tmp_path, name, payload):
    values = {setting: "synthetic" for setting in SMOKE_SETTINGS}
    values[name] = payload
    environment = candidate_environment(tmp_path, values)
    assert f"|{name}={payload}" in environment
