#!/usr/bin/env bash
set -euo pipefail

native="${1:?pass the patched GalaxyBudsClient checkout}/GalaxyBudsClient.Platform.OSX/Native/src"
tests="$(cd "$(dirname "$0")" && pwd)"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT

"${CXX:-c++}" -std=c++17 -Wall -Wextra -Werror -I "$native" \
    "$tests/handoff_gate_test.cpp" -o "$build/gate"
"$build/gate"
echo 'Passed handoff ticket and protocol fixture tests.'

if [[ "$(uname -s)" == Darwin ]]; then
    xcrun clang++ -std=c++17 -fobjc-arc -I "$native" \
        "$native/Bluetooth.mm" "$tests/handoff_transport_test.mm" \
        -framework Foundation -framework CoreFoundation -framework IOBluetooth -framework IOKit -o "$build/transport"
    "$build/transport"
    echo 'Passed handoff transport tests with simulated devices.'
fi
