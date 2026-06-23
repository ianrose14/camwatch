#!/bin/bash
set -e

USER=${CAMWATCH_USER:-$(whoami)}
HOST=${CAMWATCH_HOST:-pidork.local}

rsync -av --exclude='.git' --exclude='camwatch.db' --exclude='snapshots/' ./ "${USER}@${HOST}:~/camwatch/"
