#!/usr/bin/env bash
# End-to-end check of the deployment recommended in docs/deployment.md: the image behind
# nginx, with trusted proxies, seen from two clients with their own IP addresses.
# Requires Docker. Usage: scripts/check_deployment.sh
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
version="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$root/src/fakeverse/__init__.py")"
network="fakeverse-e2e-$$"
conf="$(mktemp)"
cleanup() {
    docker rm -f "$network-api" "$network-proxy" > /dev/null 2>&1 || true
    docker network rm "$network" > /dev/null 2>&1 || true
    docker rmi -f "$network:image" > /dev/null 2>&1 || true
    rm -f "$conf"
}
trap cleanup EXIT

cat > "$conf" <<'NGINX'
server {
    listen 80;
    client_max_body_size 64k;
    location = /metrics { deny all; }
    location / {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
NGINX
chmod 644 "$conf"

docker build -q -t "$network:image" "$root" > /dev/null
docker network create --subnet 172.31.250.0/24 "$network" > /dev/null
docker run -d --name "$network-api" --network "$network" --network-alias api \
    -e FAKEVERSE_TRUSTED_PROXIES=172.31.250.10/32 \
    -e FAKEVERSE_RATE_LIMIT=1/hour -e FAKEVERSE_RATE_BURST=3 \
    -e FAKEVERSE_METRICS_ENABLED=true "$network:image" > /dev/null
docker run -d --name "$network-proxy" --network "$network" --ip 172.31.250.10 \
    -v "$conf:/etc/nginx/conf.d/default.conf:ro" nginx:alpine > /dev/null

for _ in $(seq 1 30); do
    [ "$(docker inspect -f '{{.State.Health.Status}}' "$network-api")" = healthy ] && break
    sleep 2
done

status() {
    local ip="$1"
    shift
    docker run --rm --network "$network" --ip "$ip" curlimages/curl:latest \
        -s -o /dev/null -w "%{http_code}" "$@"
}
expect() {
    if [ "$2" != "$3" ]; then
        echo "FAIL: $1: expected $3, got $2"
        exit 1
    fi
    echo "ok: $1"
}

url="http://$network-proxy/v1/universes"
for i in 1 2 3; do
    expect "client A request $i" "$(status 172.31.250.21 -H "X-Forwarded-For: 9.9.9.$i" "$url")" 200
done
expect "client A is limited despite a forged X-Forwarded-For" \
    "$(status 172.31.250.21 -H 'X-Forwarded-For: 9.9.9.9' "$url")" 429
expect "client B has its own quota" "$(status 172.31.250.22 "$url")" 200
expect "metrics are not public" "$(status 172.31.250.22 "http://$network-proxy/metrics")" 403
cache="$(docker run --rm --network "$network" --ip 172.31.250.23 curlimages/curl:latest -s -D - \
    -o /dev/null "http://$network-proxy/v1/universes/lotr/generate/person?seed=1&data_version=$version" \
    | tr -d '\r' | grep -i '^cache-control:' | cut -d' ' -f2-)"
expect "pinned requests are immutable" "$cache" "public, max-age=31536000, immutable"
echo "Deployment check passed."
