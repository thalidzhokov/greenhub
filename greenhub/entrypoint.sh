#!/usr/bin/env bash
set -euo pipefail

: "${GH_REPO:?GH_REPO не задан}"
: "${GH_TOKEN:?GH_TOKEN не задан}"

# env_file может оставить кавычки вокруг значений — убираем
GH_REPO="${GH_REPO%\"}"; GH_REPO="${GH_REPO#\"}"
GH_TOKEN="${GH_TOKEN%\"}"; GH_TOKEN="${GH_TOKEN#\"}"
export GH_REPO GH_TOKEN

git config --global init.defaultBranch main

REPO_DIR=/repo

if [ ! -d "$REPO_DIR/.git" ]; then
    echo "Клонируем $GH_REPO в $REPO_DIR"
    git clone "${GH_REPO/https:\/\//https:\/\/x-access-token:${GH_TOKEN}@}" "$REPO_DIR"
fi

exec python /app/greenhub/main.py "$REPO_DIR"
