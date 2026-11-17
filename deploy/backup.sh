#!/bin/sh
set -eu
umask 077
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
backup_dir=${CAMPUS_TRACE_BACKUP_DIR:-"$project_dir/backups"}
mkdir -p "$backup_dir"
backup_dir=$(CDPATH= cd -- "$backup_dir" && pwd)
stage=$(mktemp -d "$backup_dir/.incomplete-XXXXXXXX")
cleanup() { rm -rf -- "$stage"; }
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
cd "$project_dir"
# Check export before compression; POSIX sh cannot propagate the first pipe failure.
docker compose -f docker-compose.prod.yml exec -T db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump --single-transaction --routines --triggers --no-tablespaces -uroot "$MYSQL_DATABASE"' > "$stage/database.sql"
test -s "$stage/database.sql"
gzip -9 "$stage/database.sql"
gzip -t "$stage/database.sql.gz"
docker compose -f docker-compose.prod.yml exec -T backend tar -czf - -C /app/media . > "$stage/media.tar.gz"
tar -tzf "$stage/media.tar.gz" > /dev/null
(cd "$stage" && sha256sum database.sql.gz media.tar.gz > SHA256SUMS && sha256sum -c SHA256SUMS > /dev/null)
stamp=$(date -u +%Y%m%dT%H%M%SZ)-$$
mv -- "$stage" "$backup_dir/backup-$stamp"
find "$backup_dir" -mindepth 1 -maxdepth 1 -type d -name 'backup-????????T??????Z-*' -mtime +14 -exec rm -rf -- {} +
printf 'Backup verified: %s\n' "$backup_dir/backup-$stamp"
