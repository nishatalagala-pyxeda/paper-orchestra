#!/usr/bin/env bash
# Portable TeX installation; does not change the system PATH or install globally.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Darwin ]] || { echo 'This script is for macOS.' >&2; exit 1; }
mkdir -p .tools
if [[ ! -d .tools/TinyTeX ]]; then
  curl -fL --retry 2 https://github.com/rstudio/tinytex-releases/releases/download/v2026.11/TinyTeX-darwin-v2026.11.tar.xz -o .tools/tinytex.tar.xz
  tar -xJf .tools/tinytex.tar.xz -C .tools
fi
TEX_MANAGER="$PWD/.tools/TinyTeX/bin/universal-darwin/tlmgr"
"$TEX_MANAGER" update --self
"$TEX_MANAGER" install silence cleveref enumitem
