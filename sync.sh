#!/bin/bash
set -e

USER=${CAMWATCH_USER:-$(whoami)}
HOST=${CAMWATCH_HOST:-pidork.local}

rsync -av \
  --include='*.py' \
  --include='*.sh' \
  --include='*.service' \
  --include='*.json' \
  --include='requirements.txt' \
  --exclude='*' \
  ./ "${USER}@${HOST}:~/camwatch/"
