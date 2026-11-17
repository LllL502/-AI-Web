#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 https://your-domain.example" >&2
  exit 2
fi

base_url=${1%/}
curl --fail --silent --show-error --max-time 15 "$base_url/" >/dev/null
curl --fail --silent --show-error --max-time 15 "$base_url/api/v1/health/" | grep -q '"status":"ok"'
echo "CampusTrace production health check: PASS"

