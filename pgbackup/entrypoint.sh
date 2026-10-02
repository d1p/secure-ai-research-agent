#!/bin/sh
set -e
mkdir -p /var/log
touch /var/log/backup.log
echo "pgbackup: starting crond"
exec crond -f -l 8
