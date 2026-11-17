#!/usr/bin/env bash

set -euo pipefail
set +x
umask 077

if [[ ! "${1:-}" =~ ^https://[^/]+/?$ || -z "${RELEASE_SMOKE_ID_TOKEN:-}" ]]; then
  echo 'smoke_configuration_valid=false' >&2
  exit 1
fi

temporary_directory="$(mktemp -d)"
trap 'rm -rf "${temporary_directory}"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Keep credentials and bodies in private temporary files, never curl arguments or logs.
python3 - "${1%/}" "${temporary_directory}" <<'PY'
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit
from uuid import UUID, uuid4

base, directory = sys.argv[1], Path(sys.argv[2])
sequence = 0
card_id = None
archived = False
refresh = None
access_header = None
logged_out = False


def header_file(name, token):
    path = directory / name
    path.write_text('Authorization: Bearer ' + token + '\n')
    return path


def request(label, method, path, expected, authorization=None, body=None, key=None):
    global sequence
    sequence += 1
    response = directory / f'response-{sequence}.json'
    arguments = ['curl', '--silent', '--show-error', '--proto', '=https',
                 '--connect-timeout', '10', '--max-time', '30',
                 '--request', method, '--output', str(response), '--write-out', '%{http_code}']
    if authorization:
        arguments += ['--header', '@' + str(authorization)]
    if body is not None:
        payload = directory / f'request-{sequence}.json'
        payload.write_text(json.dumps(body, separators=(',', ':')))
        arguments += ['--header', 'Content-Type: application/json', '--data-binary', '@' + str(payload)]
    if key:
        arguments += ['--header', 'Idempotency-Key: ' + key]
    arguments.append(base + path)
    # Capture even curl failures; its stderr and response body must not reach the job log.
    result = subprocess.run(arguments, capture_output=True, text=True, check=False)
    if result.returncode or not result.stdout.isdigit():
        raise ValueError('request failed')
    status = int(result.stdout)
    print(f'{label}_status={status}', flush=True)
    if status not in expected:
        raise ValueError('unexpected status')
    return status, json.loads(response.read_text()) if status != 204 else None


def identity(value):
    if not isinstance(value['id'], int) or value['id'] <= 0 or not isinstance(value['email'], str):
        raise ValueError('invalid identity')
    return value['id'], value['email']


def accept(value):
    access, renewed = value['access_token'], value['refresh_token']
    if not access.startswith('ela_') or not renewed.startswith('elr_'):
        raise ValueError('invalid app tokens')
    return header_file('app.headers', access), renewed


try:
    parsed = urlsplit(base)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError('invalid origin')
    request('health_live', 'GET', '/health/live', {200})
    request('health_ready', 'GET', '/health/ready', {200})
    google = os.environ['RELEASE_SMOKE_ID_TOKEN']
    google_header = header_file('google.headers', google)
    request('google_bearer_rejected', 'GET', '/v1/me', {401}, google_header)
    _, session = request('exchange', 'POST', '/v1/auth/session', {200}, body={'credential': google})
    access_header, refresh = accept(session)
    _, me = request('owned_identity', 'GET', '/v1/me', {200}, access_header)
    if identity(me) != identity(session['user']):
        raise ValueError('identity changed')
    print('owned_identity_matches=true')

    deck_title = 'Release smoke (synthetic)'
    deck_id = None
    cursor = None
    seen = set()
    while True:
        query = {'target_language': 'en', 'status': 'active', 'limit': 100}
        if cursor:
            query['cursor'] = cursor
        _, page = request('owned_decks', 'GET', '/v1/decks?' + urlencode(query), {200}, access_header)
        matches = [item for item in page['items'] if item['title'] == deck_title and item['target_language'] == 'en']
        if matches:
            deck_id = str(UUID(matches[0]['id']))
            break
        cursor = page['next_cursor']
        if not cursor:
            break
        if cursor in seen:
            raise ValueError('repeated cursor')
        seen.add(cursor)
    if deck_id is None:
        _, deck = request('synthetic_deck_created', 'POST', '/v1/decks', {201}, access_header,
                          {'title': deck_title, 'target_language': 'en', 'explanation_language': 'en'}, str(uuid4()))
        deck_id = str(UUID(deck['id']))
    print('synthetic_deck_ready=true')
    _, card = request('synthetic_card_created', 'POST', '/v1/cards', {201}, access_header,
                      {'deck_id': deck_id, 'term': 'release-smoke-' + str(uuid4()),
                       'meaning': 'Synthetic release verification card'}, str(uuid4()))
    card_id = str(UUID(card['id']))
    state = card['review_state']
    if datetime.fromisoformat(state['next_review_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc):
        raise ValueError('new card is not due')
    print('synthetic_card_due=true')
    payload = {'items': [{'card_id': card_id, 'decision': 'yes_a_bit', 'expected_version': state['version']}]}
    key = str(uuid4())
    _, first = request('review_write', 'POST', '/v1/reviews', {200}, access_header, payload, key)
    _, replay = request('review_replay', 'POST', '/v1/reviews', {200}, access_header, payload, key)
    if first != replay or len(first['items']) != 1 or first['items'][0]['card_id'] != card_id:
        raise ValueError('review replay mismatch')
    print('review_replay_identical=true')
    # DELETE is the existing soft-archive route; review events and the deck remain.
    request('synthetic_card_archived', 'DELETE', '/v1/cards/' + card_id, {204}, access_header)
    archived = True
    original_refresh = refresh
    _, rotated = request('refresh', 'POST', '/v1/auth/refresh', {200}, body={'refresh_token': original_refresh})
    access_header, refresh = accept(rotated)
    if refresh == original_refresh or identity(rotated['user']) != identity(me):
        raise ValueError('refresh did not rotate for the same identity')
    status, reused = request('rotated_refresh_rejected', 'POST', '/v1/auth/refresh', {409, 401}, body={'refresh_token': original_refresh})
    if reused['error']['code'] != ('refresh_superseded' if status == 409 else 'refresh_reused'):
        raise ValueError('unexpected reuse boundary')
    print('refresh_rotation_verified=true')
    request('logout', 'POST', '/v1/auth/logout', {204}, access_header, {'refresh_token': refresh})
    logged_out = True
    request('logged_out_access_rejected', 'GET', '/v1/me', {401}, access_header)
    print('smoke_passed=true')
except Exception:
    # Do not expose JSON, exception messages, response content or credentials.
    print('smoke_passed=false', file=sys.stderr)
    sys.exit(1)
finally:
    if card_id and not archived:
        try:
            request('cleanup_card_archived', 'DELETE', '/v1/cards/' + card_id, {204}, access_header)
        except Exception:
            print('cleanup_card_archived=false', file=sys.stderr)
    if refresh and not logged_out:
        try:
            request('cleanup_logout', 'POST', '/v1/auth/logout', {204}, access_header, {'refresh_token': refresh})
        except Exception:
            print('cleanup_logout=false', file=sys.stderr)
PY
