#!/bin/sh
# Build one block spec into docs/pdf/. Run from src/riscv.
# usage: scripts/spec_pdf/build.sh docs/designs/<name>.md
set -eu
src=$1
dir=$(dirname "$0")
name=$(basename "$src" .md)
title=$(sed -n 's/^# //p;q' "$src")
mkdir -p docs/pdf
SOURCE_DATE_EPOCH=$(git log -1 --format=%ct -- "$src")
FORCE_SOURCE_DATE=1
export SOURCE_DATE_EPOCH FORCE_SOURCE_DATE
pandoc "$src" -o "docs/pdf/$name.pdf" --from=gfm --pdf-engine=xelatex \
    --shift-heading-level-by=-1 --lua-filter="$dir/spec.lua" -H "$dir/header.tex" \
    -V geometry:a4paper,margin=2cm -V fontsize=11pt \
    -V mainfont="Liberation Serif" -V monofont="Liberation Mono" \
    -V "header-includes=\\newcommand{\\specname}{$title}" \
    --metadata title="$title" --metadata date=""
