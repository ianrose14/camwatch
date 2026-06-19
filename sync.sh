#!/bin/bash
set -e

USER=${CAMWATCH_USER:-$(whoami)}
HOST=${CAMWATCH_HOST:-pidork}

rsync -av --exclude='.git' ./ "${USER}@${HOST}:~/camwatch/"
