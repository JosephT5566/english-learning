#!/usr/bin/env bash

set -euo pipefail

readonly required_variables=(
	GCP_PROJECT_ID
	GCP_REGION
	ARTIFACT_REGION
	ARTIFACT_REPOSITORY
	API_IMAGE_NAME
	API_SERVICE
	MIGRATION_JOB
	RUNTIME_SERVICE_ACCOUNT
	MIGRATION_SERVICE_ACCOUNT
	RUNTIME_DATABASE_SECRET
	RUNTIME_DATABASE_SECRET_VERSION
	MIGRATION_DATABASE_SECRET
	MIGRATION_DATABASE_SECRET_VERSION
	GOOGLE_OAUTH_CLIENT_ID
	GOOGLE_ALLOWED_EMAILS
	CORS_ALLOWED_ORIGINS
)

for variable_name in "${required_variables[@]}"; do
	if [[ -z "${!variable_name:-}" ]]; then
		echo "Missing required release variable: ${variable_name}." >&2
		exit 1
	fi
done

if [[ -n "$(git status --porcelain)" ]]; then
	echo "Refusing to release from a dirty worktree." >&2
	exit 1
fi

readonly release_id="${RELEASE_ID:-$(git rev-parse --short=12 HEAD)}"
if [[ ! "${release_id}" =~ ^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$ ]]; then
	echo "RELEASE_ID must be a lowercase Cloud Run revision suffix." >&2
	exit 1
fi

readonly image="${ARTIFACT_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REPOSITORY}/${API_IMAGE_NAME}:${release_id}"
readonly environment_variables="^|^APP_ENV=production|LOG_LEVEL=INFO|DATABASE_CONNECT_TIMEOUT_SECONDS=5|GOOGLE_OAUTH_CLIENT_ID=${GOOGLE_OAUTH_CLIENT_ID}|GOOGLE_ALLOWED_EMAILS=${GOOGLE_ALLOWED_EMAILS}|CORS_ALLOWED_ORIGINS=${CORS_ALLOWED_ORIGINS}"

echo "Building immutable release image ${image}."
gcloud builds submit apps/api \
	--project "${GCP_PROJECT_ID}" \
	--tag "${image}"

echo "Creating or updating the single-task migration job."
gcloud run jobs deploy "${MIGRATION_JOB}" \
	--project "${GCP_PROJECT_ID}" \
	--region "${GCP_REGION}" \
	--image "${image}" \
	--service-account "${MIGRATION_SERVICE_ACCOUNT}" \
	--tasks 1 \
	--parallelism 1 \
	--max-retries 0 \
	--task-timeout 10m \
	--command alembic \
	--args upgrade,head \
	--set-env-vars "${environment_variables}" \
	--set-secrets "DATABASE_URL=${MIGRATION_DATABASE_SECRET}:${MIGRATION_DATABASE_SECRET_VERSION}"

echo "Running migrations before creating the candidate application revision."
gcloud run jobs execute "${MIGRATION_JOB}" \
	--project "${GCP_PROJECT_ID}" \
	--region "${GCP_REGION}" \
	--wait

echo "Deploying a tagged candidate revision with zero production traffic."
gcloud run deploy "${API_SERVICE}" \
	--project "${GCP_PROJECT_ID}" \
	--region "${GCP_REGION}" \
	--image "${image}" \
	--revision-suffix "${release_id}" \
	--tag candidate \
	--no-traffic \
	--allow-unauthenticated \
	--ingress all \
	--service-account "${RUNTIME_SERVICE_ACCOUNT}" \
	--port 8080 \
	--cpu 1 \
	--memory 512Mi \
	--concurrency 20 \
	--min-instances 0 \
	--max-instances 1 \
	--timeout 30s \
	--set-env-vars "${environment_variables}" \
	--set-secrets "DATABASE_URL=${RUNTIME_DATABASE_SECRET}:${RUNTIME_DATABASE_SECRET_VERSION}" \
	--startup-probe httpGet.path=/health/live,initialDelaySeconds=0,timeoutSeconds=2,periodSeconds=2,failureThreshold=15 \
	--liveness-probe httpGet.path=/health/live,initialDelaySeconds=0,timeoutSeconds=2,periodSeconds=10,failureThreshold=3

echo "Candidate deployed without production traffic."
echo "Run the smoke checks from doc/training/issues/issue-26/runbook.md before moving traffic."
