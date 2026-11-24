
#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "Validating Docker Compose configuration..."
docker compose config --quiet

echo "Stopping n8n before importing workflows..."
docker compose stop n8n

echo "Importing n8n workflows..."
if docker compose --profile setup run --rm --no-deps n8n-import; then
    echo "Workflow import completed successfully."
else
    echo "Workflow import failed."
    echo "Restarting n8n..."
    docker compose start n8n
    exit 1
fi

echo "Restarting n8n..."
docker compose start n8n

echo "Setup completed successfully."
echo "Open n8n at http://localhost:5679"
