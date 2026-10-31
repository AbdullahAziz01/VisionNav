#!/bin/sh
set -e
python /app/tools/seed_runtime_weights.py
exec "$@"
