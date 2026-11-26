#!/bin/bash
set -euo pipefail
source_dir="$(cd "$(dirname "$0")" && pwd)"
output_dir="${1:?Pass an output directory}"
mkdir -p "$output_dir"
output_dir="$(cd "$output_dir" && pwd)"
bundle="$output_dir/Buds On Connection Check.app"
mkdir -p "$bundle/Contents/MacOS"
cp "$source_dir/Info.plist" "$bundle/Contents/Info.plist"
xcrun clang -fobjc-arc -fblocks -O2 -Wall -Wextra -arch arm64 -mmacosx-version-min=13.0 \
  -framework AppKit -framework IOBluetooth \
  "$source_dir/main.m" "$source_dir/DirectTransport.m" \
  -o "$bundle/Contents/MacOS/BudsOnConnectionCheck"
/usr/bin/plutil -lint "$bundle/Contents/Info.plist"
/usr/bin/codesign --force --sign - "$bundle"
/usr/bin/codesign --verify --strict "$bundle"
/usr/bin/lipo -verify_arch arm64 "$bundle/Contents/MacOS/BudsOnConnectionCheck"
/usr/bin/pkgbuild --component "$bundle" --install-location /Applications \
  --identifier io.github.matt-gummow.budson-direct-check --version "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$bundle/Contents/Info.plist")" \
  "$output_dir/Buds-On-Connection-Check-arm64.pkg"
(cd "$output_dir" && /usr/bin/shasum -a 256 Buds-On-Connection-Check-arm64.pkg > SHA256.txt)
