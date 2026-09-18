#!/usr/bin/env bash

set -euo pipefail

readonly image_name="${1:-english-learning-api:verify}"
readonly container_name="english-learning-api-verify-$$"

cleanup() {
	docker rm --force "${container_name}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

configured_user="$(docker image inspect --format '{{.Config.User}}' "${image_name}")"
if [[ "${configured_user}" != "10001:10001" ]]; then
	echo "Expected image user 10001:10001, received ${configured_user:-<empty>}." >&2
	exit 1
fi

docker run \
	--detach \
	--name "${container_name}" \
	--publish 127.0.0.1::8080 \
	"${image_name}" >/dev/null

port_binding="$(docker port "${container_name}" 8080/tcp)"
health_url="http://${port_binding}/health/live"

for attempt in {1..30}; do
	if curl --fail --silent --show-error "${health_url}" >/dev/null 2>&1; then
		break
	fi
	if [[ "${attempt}" == "30" ]]; then
		docker logs "${container_name}" >&2
		echo "Container liveness did not become available." >&2
		exit 1
	fi
	sleep 0.25
done

runtime_uid="$(docker exec "${container_name}" id -u)"
runtime_gid="$(docker exec "${container_name}" id -g)"
if [[ "${runtime_uid}:${runtime_gid}" != "10001:10001" ]]; then
	echo "Expected runtime user 10001:10001, received ${runtime_uid}:${runtime_gid}." >&2
	exit 1
fi

if docker exec "${container_name}" sh -c 'test -e /app/.env || command -v uv >/dev/null'; then
	echo "Final image contains a runtime environment file or the build-only uv binary." >&2
	exit 1
fi

readiness_status="$(
	curl --silent --output /dev/null --write-out '%{http_code}' \
		"http://${port_binding}/health/ready"
)"
if [[ "${readiness_status}" != "503" ]]; then
	echo "Expected readiness 503 without PostgreSQL, received ${readiness_status}." >&2
	exit 1
fi

docker stop --timeout 10 "${container_name}" >/dev/null

exit_code="$(docker inspect --format '{{.State.ExitCode}}' "${container_name}")"
if [[ "${exit_code}" != "0" ]]; then
	docker logs "${container_name}" >&2
	echo "Container exited with status ${exit_code} after SIGTERM." >&2
	exit 1
fi

container_logs="$(docker logs "${container_name}" 2>&1)"
if [[ "${container_logs}" != *'Application shutdown complete'* ]]; then
	printf '%s\n' "${container_logs}" >&2
	echo "Container did not record a completed application shutdown." >&2
	exit 1
fi

echo "Container verified: minimal non-root runtime, meaningful probes, and graceful SIGTERM exit."
