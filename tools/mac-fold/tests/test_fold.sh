#!/bin/bash
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
. "$here/fold.sh"
temp=$(mktemp -d)
trap 'rm -rf "$temp"' EXIT
export FOLD_FIXTURE="$temp"
write_fake() { cat > "$temp/adb"; chmod +x "$temp/adb"; }
write_fake <<'ADB'
#!/bin/bash
set -eu
if [ "$1" = '-d' ]; then
    case "$2" in
        get-state) echo device ;;
        get-serialno) echo PRIVATE_TEST_SERIAL ;;
        *) exit 2 ;;
    esac
    exit
fi
[ "$1" = -s ] && [ "$2" = PRIVATE_TEST_SERIAL ] || exit 3
shift 2
case "$1 $2" in
    'shell am')
        case "$3" in
            'get-current-user') echo 0 ;;
            'broadcast')
                nonce=${!#}
                [[ " $* " == *" dev.budson.overlap.probe.READ_AUDIO "* ]] || exit 9
                echo 'Private Android output should never be printed!'
                echo "Broadcast completed: result=0, data=\"BO2:$nonce:connected:disconnected:yes:unknown\""
                ;;
            *) exit 4 ;;
        esac ;;
    'shell pm')
        case "$3" in
            list) if [ -e "$FOLD_FIXTURE/installed" ]; then echo package:dev.budson.overlap.probe; fi ;;
            path) if [ -e "$FOLD_FIXTURE/installed" ]; then cat "$FOLD_FIXTURE/path"; fi ;;
            uninstall) rm "$FOLD_FIXTURE/installed"; echo Success ;;
            *) exit 4 ;;
        esac ;;
    'install --user')
        [ "$3" = 0 ] && [ "$4" = '-R' ] && [ "$5" = '-g' ] || exit 8
        touch "$FOLD_FIXTURE/installed"; echo 'Performing Streamed Install'; echo Success ;;
    *) exit 5 ;;
esac
ADB
export PATH="$temp:$PATH"
printf '%s\n' 'package:/data/app/~~private/test/base.apk' > "$temp/path"
apk="$temp/test apk"; touch "$apk"
peer='AA:BB:CC:DD:EE:FF'
fold_setup_usb > "$temp/log" 2>&1
! fold_install "$apk" "$peer" no
[ ! -e "$temp/installed" ]
touch "$temp/installed"
! fold_install "$apk" "$peer" yes >> "$temp/log" 2>&1
[ -e "$temp/installed" ]
rm "$temp/installed"
fold_install "$apk" "$peer" yes >> "$temp/log" 2>&1
[ "$FOLD_READY" = yes ]
[ "$(fold_sample)" = 'connected disconnected yes unknown' ]
nonce=01111111111111111111111111111111
valid="Broadcast completed: result=0, data=\"BO2:$nonce:connected:connected:unconfirmed:yes\""
[ "$(_fold_parse_sample "$nonce" "$valid")" = 'connected connected unconfirmed yes' ]
[ "$(_fold_parse_sample "$nonce" "$valid"$'\n'"$valid")" = 'unknown unknown unknown unknown' ]
[ "$(_fold_parse_sample '11111111111111111111111111111111' "$valid")" = 'unknown unknown unknown unknown' ]
[ "$(_fold_parse_sample 'bad' "$valid")" = 'unknown unknown unknown unknown' ]
sed -e 's,private,changed,' "$temp/path" > "$temp/changed"; mv "$temp/path" "$temp/original"; mv "$temp/changed" "$temp/path"
! fold_cleanup
[ -e "$temp/installed" ]
mv "$temp/original" "$temp/path"
fold_cleanup
[ ! -e "$temp/installed" ]
if grep -Eq 'AA:BB|PRIVATE_TEST_SERIAL|Private Android|/data/app' "$temp/log"; then exit 11; fi
echo 'Fold sample, USB, ownership and redaction tests passed.'
