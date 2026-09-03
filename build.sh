#!/usr/bin/env bash

set -e

pip install -r requirements.txt

curl -fsSL https://deno.land/install.sh | sh

export PATH="$HOME/.deno/bin:$PATH"

deno --version
yt-dlp --version
