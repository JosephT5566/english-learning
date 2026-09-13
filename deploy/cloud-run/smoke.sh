#!/usr/bin/env bash

set -euo pipefail

readonly api_base_url="${1:-}"
if [[ ! "${api_base_url}" =~ ^https://[^/]+/?$ ]]; then
	echo "Usage: GOOGLE_ID_TOKEN=... $0 https://candidate-api-host" >&2
	exit 1
fi

readonly google_id_token="${GOOGLE_ID_TOKEN:-}"
readonly normalized_base_url="${api_base_url%/}"

curl --fail --silent --show-error \
	"${normalized_base_url}/health/live" >/dev/null
curl --fail --silent --show-error \
	"${normalized_base_url}/health/ready" >/dev/null

if [[ -z "${google_id_token}" ]]; then
	echo "Public liveness and database readiness passed."
	echo "Supply GOOGLE_ID_TOKEN in the environment for owned-read checks."
	exit 0
fi

readonly authorization_header="Authorization: Bearer ${google_id_token}"
curl --fail --silent --show-error \
	--header "${authorization_header}" \
	"${normalized_base_url}/v1/me" >/dev/null
curl --fail --silent --show-error \
	--header "${authorization_header}" \
	"${normalized_base_url}/v1/decks?target_language=en&status=active&limit=1" >/dev/null

echo "Public health and authenticated owned-read checks passed."

if [[ "${CONFIRM_REVIEW_WRITE:-}" != "yes" ]]; then
	echo "Set CONFIRM_REVIEW_WRITE=yes to submit and exactly replay one due-card review."
	exit 0
fi

readonly temporary_directory="$(mktemp -d)"
cleanup() {
	rm -rf "${temporary_directory}"
}
trap cleanup EXIT

readonly due_response="${temporary_directory}/due.json"
curl --fail --silent --show-error \
	--header "${authorization_header}" \
	"${normalized_base_url}/v1/reviews/due?target_language=en&limit=1" \
	--output "${due_response}"

readonly review_target="$({
	python3 -c \
		'import json,sys; items=json.load(open(sys.argv[1]))["items"]; print("{}\t{}".format(items[0]["id"], items[0]["review_state"]["version"])) if items else sys.exit(2)' \
		"${due_response}"
} || {
	echo "No due English card is available for the controlled review write." >&2
	exit 2
})"
IFS=$'\t' read -r card_id expected_version <<<"${review_target}"

readonly idempotency_key="$(python3 -c 'import uuid; print(uuid.uuid4())')"
readonly review_payload="$(
	python3 -c \
		'import json,sys; print(json.dumps({"items":[{"card_id":sys.argv[1],"decision":"yes_a_bit","expected_version":int(sys.argv[2])}]}))' \
		"${card_id}" "${expected_version}"
)"
readonly first_response="${temporary_directory}/first.json"
readonly replay_response="${temporary_directory}/replay.json"

for output_file in "${first_response}" "${replay_response}"; do
	curl --fail --silent --show-error \
		--request POST \
		--header "${authorization_header}" \
		--header "Content-Type: application/json" \
		--header "Idempotency-Key: ${idempotency_key}" \
		--data "${review_payload}" \
		--output "${output_file}" \
		"${normalized_base_url}/v1/reviews"
done

python3 -c \
	'import json,sys; first=json.load(open(sys.argv[1])); replay=json.load(open(sys.argv[2])); assert first == replay, "review replay differed from the committed result"' \
	"${first_response}" "${replay_response}"

echo "Controlled review write and exact idempotent replay passed."
