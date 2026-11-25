#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PROVISION_CREDENTIAL=false

if [[ "${1:-}" == "--provision-credential" ]]; then
    PROVISION_CREDENTIAL=true
elif [[ $# -gt 0 ]]; then
    echo "Usage: $0 [--provision-credential]" >&2
    exit 2
fi

echo "Validating Docker Compose configuration..."
docker compose config --quiet

if [[ "$PROVISION_CREDENTIAL" == true ]]; then
    if [[ ! -f .env ]]; then
        echo "Missing .env file." >&2
        exit 1
    fi

    set -a
    source .env
    set +a

    if [[ -z "${RETENTION_API_KEY:-}" ]]; then
        echo "RETENTION_API_KEY is not configured." >&2
        exit 1
    fi

    echo "Credential provisioning enabled."
    echo "WARNING: An existing credential with the same ID may be overwritten."
fi

echo "Stopping n8n before importing..."
docker compose stop n8n

restart_n8n() {
    echo "Starting n8n..."
    docker compose start n8n
}

trap restart_n8n EXIT

if [[ "$PROVISION_CREDENTIAL" == true ]]; then
    echo "Importing Retention API credential..."

    python3 scripts/create_n8n_credential.py |
        docker compose --profile setup run \
            --rm \
            -T \
            --no-deps \
            --entrypoint sh \
            n8n-import \
            -c '
                set -eu
                umask 077

                credential_file="$(mktemp)"
                trap '"'"'rm -f "$credential_file"'"'"' EXIT

                cat > "$credential_file"

                n8n import:credentials \
                    --input="$credential_file"
            '
fi

echo "Importing n8n workflows..."

docker compose --profile setup run \
    --rm \
    --no-deps \
    n8n-import

echo "Workflow import completed successfully."

restart_n8n
trap - EXIT

echo "Setup completed successfully."