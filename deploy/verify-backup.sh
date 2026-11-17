#!/bin/sh
# Restore only into an isolated temporary database.
set -eu
umask 077
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
bundle=$(CDPATH= cd -- "${1:?Usage: verify-backup.sh BACKUP_DIRECTORY}" && pwd)
(cd "$bundle" && sha256sum -c SHA256SUMS)
gzip -t "$bundle/database.sql.gz"
tar -tzf "$bundle/media.tar.gz" > /dev/null
stage=$(mktemp -d)
database=restore_check_$(date -u +%Y%m%d%H%M%S)_$$
cd "$project_dir"
db() { docker compose -f docker-compose.prod.yml exec -T db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot "$@"' sh "$@"; }
cleanup() { db -e "DROP DATABASE IF EXISTS $database"; rm -rf -- "$stage"; }
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
gzip -dc "$bundle/database.sql.gz" > "$stage/database.sql"
db -e "CREATE DATABASE $database CHARACTER SET utf8mb4"
db "$database" < "$stage/database.sql"
count=$(db -N -s -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$database'")
test "$count" -gt 0
mkdir "$stage/media"
tar -xzf "$bundle/media.tar.gz" -C "$stage/media"
printf 'Restore verified: %s tables; media extracted.\n' "$count"
