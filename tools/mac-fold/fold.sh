# Source in bash 3.2+. Status variables are private to this process. Never enable shell tracing.
FOLD_PACKAGE=dev.budson.overlap.probe
FOLD_ADB=
FOLD_SERIAL=
FOLD_USER=
FOLD_PEER=
FOLD_INSTALLED=no
FOLD_INSTALL_UNCERTAIN=no
FOLD_PACKAGE_PATH=
FOLD_READY=no

_fold_message() { printf '%s\n' "$*" >&2; }

# The system Perl on macOS supplies a wall-clock deadline for an individual adb client.
# An expired request never stops the shared adb server or another capture.
_fold_adb() {
    local timeout=$1
    shift
    /usr/bin/perl -e 'alarm shift; exec {$ARGV[0]} @ARGV; exit 127' "$timeout" "$FOLD_ADB" "$@" 2>/dev/null
}

fold_setup_usb() {
    local sdk candidate listed state serial user
    FOLD_ADB=
    FOLD_SERIAL=
    FOLD_USER=
    for candidate in "$(command -v adb 2>/dev/null)" /opt/homebrew/bin/adb /usr/local/bin/adb; do
        if [ -f "$candidate" ] && [ -x "$candidate" ]; then FOLD_ADB=$candidate; break; fi
    done
    if [ -z "$FOLD_ADB" ]; then
        for sdk in "${ANDROID_HOME:-}" "${ANDROID_SDK_ROOT:-}" "$HOME/Library/Android/sdk"; do
            if [ -n "$sdk" ] && [ -x "$sdk/platform-tools/adb" ]; then FOLD_ADB="$sdk/platform-tools/adb"; break; fi
        done
    fi
    if [ -z "$FOLD_ADB" ]; then
        _fold_message 'Install Android Platform-Tools for Mac from developer.android.com/tools/releases/platform-tools, then reopen this tool.'
        return 1
    fi
    if [ ! -x /usr/bin/perl ]; then _fold_message 'The macOS system Perl utility is unavailable.'; return 1; fi
    if ! state=$(_fold_adb 12 -d get-state) || [ "$state" != device ]; then
        _fold_message 'Connect just the unlocked Fold by USB data cable, enable USB debugging, and approve this Mac on the Fold.'
        return 1
    fi
    serial=$(_fold_adb 6 -d get-serialno) || return 1
    if ! [[ $serial =~ ^[A-Za-z0-9_.-]{1,128}$ ]]; then return 1; fi
    user=$(_fold_adb 6 -s "$serial" shell am get-current-user) || return 1
    user=${user%$'\r'}
    if ! [[ $user =~ ^[0-9]{1,6}$ ]]; then return 1; fi
    FOLD_SERIAL=$serial
    FOLD_USER=$user
}

_fold_current_install_path() {
    local line re='^package:(/data/app/[A-Za-z0-9_./=~+-]+/base\.apk)$'
    line=$(_fold_adb 6 -s "$FOLD_SERIAL" shell pm path --user "$FOLD_USER" "$FOLD_PACKAGE") || return 1
    line=${line%$'\r'}
    [[ $line =~ $re ]] || return 1
    printf '%s\n' "${BASH_REMATCH[1]}"
}

fold_install() {
    local apk=$1 peer=$2 consent=$3 installed result path row success=no
    if [ "$consent" != yes ] || [ "$FOLD_INSTALLED" = yes ] || [ "$FOLD_INSTALL_UNCERTAIN" = yes ]; then return 1; fi
    if [ -z "$FOLD_SERIAL" ] || [ -z "$FOLD_USER" ] || [ ! -r "$apk" ]; then return 1; fi
    peer=$(printf '%s' "$peer" | tr '[:lower:]' '[:upper:]')
    if ! [[ $peer =~ ^([0-9A-F]{2}:){5}[0-9A-F]{2}$ ]]; then return 1; fi
    installed=$(_fold_adb 6 -s "$FOLD_SERIAL" shell pm list packages -u --user "$FOLD_USER" "$FOLD_PACKAGE") || return 1
    if [ -n "$installed" ]; then
        _fold_message 'There is already a copy of Buds On connection check on the Fold, or Android could not verify the package list. The recorder left the phone unchanged.'
        return 1
    fi
    FOLD_INSTALL_UNCERTAIN=yes
    if ! result=$(_fold_adb 65 -s "$FOLD_SERIAL" install --user "$FOLD_USER" -R -g "$apk"); then
        _fold_message 'Android did not confirm this installation. Check the Fold for an install prompt.'
        return 1
    fi
    while IFS= read -r row; do
        if [ "${row%$'\r'}" = Success ]; then success=yes; fi
    done <<< "$result"
    if [ "$success" != yes ]; then return 1; fi
    FOLD_INSTALLED=yes
    FOLD_INSTALL_UNCERTAIN=no
    path=$(_fold_current_install_path) || return 1
    FOLD_PACKAGE_PATH=$path
    FOLD_PEER=$peer
    FOLD_READY=yes
}

_fold_parse_sample() {
    local nonce=$1 text=$2 row match='' observed=0
    if ! [[ $nonce =~ ^[a-f0-9]{32}$ ]]; then printf 'unknown unknown unknown unknown\n'; return; fi
    local state='(connected|disconnected|unknown)' audio='(yes|unconfirmed|unknown)'
    local pattern="^Broadcast completed: result=0, data=\"BO2:$nonce:$state:$state:$audio:$audio\"$"
    while IFS= read -r row; do
        row=${row%$'\r'}
        if [[ $row =~ $pattern ]]; then
            match="${BASH_REMATCH[1]} ${BASH_REMATCH[2]} ${BASH_REMATCH[3]} ${BASH_REMATCH[4]}"
            observed=$((observed + 1))
        fi
    done <<< "$text"
    if [ "$observed" -eq 1 ]; then printf '%s\n' "$match"; else printf 'unknown unknown unknown unknown\n'; fi
}

fold_sample() {
    local nonce reply
    if [ "$FOLD_READY" != yes ]; then printf 'unknown unknown unknown unknown\n'; return; fi
    nonce=$(LC_ALL=C od -An -N16 -tx1 /dev/urandom | tr -d '[:space:]')
    if ! [[ $nonce =~ ^[a-f0-9]{32}$ ]]; then printf 'unknown unknown unknown unknown\n'; return; fi
    if reply=$(_fold_adb 4 -s "$FOLD_SERIAL" shell am broadcast --user "$FOLD_USER" -f 0x10000020 -n "$FOLD_PACKAGE/.Probe" -a "$FOLD_PACKAGE.READ_AUDIO" --es peer "$FOLD_PEER" --es request "$nonce"); then
        _fold_parse_sample "$nonce" "$reply"
    else
        printf 'unknown unknown unknown unknown\n'
    fi
}

fold_cleanup() {
    local current result installed
    if [ "$FOLD_INSTALLED" != yes ]; then [ "$FOLD_INSTALL_UNCERTAIN" != yes ]; return; fi
    current=$(_fold_current_install_path) || return 1
    if [ -z "$FOLD_PACKAGE_PATH" ] || [ "$current" != "$FOLD_PACKAGE_PATH" ]; then return 1; fi
    result=$(_fold_adb 20 -s "$FOLD_SERIAL" shell pm uninstall --user "$FOLD_USER" "$FOLD_PACKAGE") || return 1
    [ "${result%$'\r'}" = Success ] || return 1
    installed=$(_fold_adb 6 -s "$FOLD_SERIAL" shell pm list packages --user "$FOLD_USER" "$FOLD_PACKAGE") || return 1
    [ -z "$installed" ] || return 1
    FOLD_INSTALLED=no
    FOLD_READY=no
    FOLD_PACKAGE_PATH=
    FOLD_SERIAL=
    FOLD_PEER=
}
