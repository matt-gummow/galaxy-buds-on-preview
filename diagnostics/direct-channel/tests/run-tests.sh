#!/bin/bash
set -eu
probe_dir="$(cd "$(dirname "$0")/.." && pwd)"
output_dir="$(mktemp -d)"
trap 'rm -f "$output_dir/DirectTransportTests"; rmdir "$output_dir"' EXIT
xcrun clang -fobjc-arc -Wall -Wextra -Werror -framework Foundation -framework IOBluetooth \
    "$probe_dir/DirectTransport.m" "$probe_dir/tests/DirectTransportTests.m" -o "$output_dir/DirectTransportTests"
"$output_dir/DirectTransportTests"
