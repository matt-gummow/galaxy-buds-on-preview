#!/bin/bash
set -eu
probe_dir="$(cd "$(dirname "$0")/.." && pwd)"
output_dir="$(mktemp -d)"
trap 'rm -f "$output_dir/DirectUITests"; rmdir "$output_dir"' EXIT
xcrun clang -fobjc-arc -fblocks -Wall -Wextra -Werror -mmacosx-version-min=13.0 \
  -framework AppKit -framework Foundation \
  "$probe_dir/tests/DirectUITests.m" -o "$output_dir/DirectUITests"
"$output_dir/DirectUITests"
