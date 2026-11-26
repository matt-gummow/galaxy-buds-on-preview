#!/bin/bash
# Build the native probe and archive the four runtime files. Requires macOS and Xcode CLI tools.
set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "Usage: build-kit.sh BudsOverlap.apk /path/to/output.zip" >&2
    exit 2
fi
src="$(cd "$(dirname "$0")" && pwd -P)"
apk="$1"
out_dir="$(cd "$(dirname "$2")" && pwd -P)"
output="$out_dir/$(basename "$2")"
if [ ! -f "$apk" ] || [ -e "$output" ]; then
    echo "A signed input APK and a new output ZIP path are required." >&2
    exit 2
fi
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mac-fold.XXXXXXXX")"
trap 'rm -rf "$tmp"' EXIT
kit_name=Mac-Fold-Switch-Test
kit="$tmp/$kit_name"
mkdir "$kit"
install -m 755 "$src/Start-Mac-Fold.command" "$kit/"
install -m 644 "$src/fold.sh" "$kit/"
install -m 644 "$apk" "$kit/BudsOverlap.apk"
/usr/bin/unzip -tqq "$kit/BudsOverlap.apk"
/usr/bin/unzip -Z1 "$kit/BudsOverlap.apk" > "$tmp/apk-entries"
/usr/bin/grep -qx classes.dex "$tmp/apk-entries"
/usr/bin/grep -qx AndroidManifest.xml "$tmp/apk-entries"
(
    cd "$src"
    xcrun clang -Os -fobjc-arc -arch arm64 -mmacosx-version-min=13.0 \
        -framework Foundation -framework IOBluetooth -framework CoreAudio \
        -Wl,-sectcreate,__TEXT,__info_plist,MacBudsProbe-Info.plist \
        -o "$kit/MacBudsProbe" MacBudsProbe.m
)
codesign --force --sign - --identifier dev.budson.macfold.probe "$kit/MacBudsProbe"
codesign --verify --strict "$kit/MacBudsProbe"
[ "$(xcrun lipo -archs "$kit/MacBudsProbe")" = arm64 ]
"$kit/MacBudsProbe" selftest

# Nest the permission-preserving ZIP inside the Actions artifact; upload-artifact normalizes loose file modes.
(cd "$tmp" && /usr/bin/zip -q -X -r bundle.zip "$kit_name")
mkdir "$tmp/check"
/usr/bin/unzip -q "$tmp/bundle.zip" -d "$tmp/check"
unpacked="$tmp/check/$kit_name"
[ -x "$unpacked/Start-Mac-Fold.command" ]
[ -x "$unpacked/MacBudsProbe" ]
cmp "$apk" "$unpacked/BudsOverlap.apk"
codesign --verify --strict "$unpacked/MacBudsProbe"
"$unpacked/MacBudsProbe" selftest
/bin/bash -n "$unpacked/Start-Mac-Fold.command"
/bin/bash -n "$unpacked/fold.sh"
mv "$tmp/bundle.zip" "$output"
