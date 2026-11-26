#!/bin/bash
set -eu
src=$(cd "$(dirname "$0")/.." && pwd -P)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cp "$src/Start-Mac-Fold.command" "$src/fold.sh" "$tmp/"
export HOME="$tmp/user"
mkdir "$HOME"
cat > "$tmp/MacBudsProbe" <<'NATIVE'
#!/bin/bash
tick() { /usr/bin/perl -MTime::HiRes=time -e 'printf "%d", time()*1000'; }
case "$1" in
    clock) tick ;;
    target) echo '12:34:56:78:90:AB' ;;
    watch)
        read -r peer
        [[ $peer == '12:34:56:78:90:AB' ]] || exit 2
        echo "private-debug-id"
        while :; do echo "$(tick) sample connected buds other"; sleep 0.1; done ;;
esac
NATIVE
chmod +x "$tmp/MacBudsProbe"
for scenario in pass drop unknown no_mac ; do
    (
        source "$tmp/Start-Mac-Fold.command"
        # Exercise the normal launcher orchestration with a disposable home and mocked hardware.
        fold_setup_usb() { return 0; }
        fold_install() { [[ $2 == '12:34:56:78:90:AB' && $3 == yes ]]; }
        fold_cleanup() { touch "$tmp/clean-$scenario"; }
        reveal_report() { cp "$1" "$tmp/report-$scenario"; }
        fold_sample() {
            if [[ -f $work/markers ]] && grep -q 'heard_mac_yes' "$work/markers"; then
                case "$scenario" in
                    drop) echo 'disconnected disconnected unconfirmed unconfirmed'; return ;;
                    unknown) echo 'private malicious payload'; return ;;
                esac
            fi
            echo 'connected connected yes unknown'
        }
        ask() {
            case "$1" in
                'Install the helper'*|'After hanging up:'*) REPLY=yes ;;
                'Can you hear the Mac'*) if [[ $scenario == no_mac ]]; then REPLY=no; else REPLY=yes; fi ;;
                'Enter 1, 2,'*) REPLY=1 ;;
                *) return 1 ;;
            esac
        }
        run_test
    )
    grep -q 'mac connected buds other' "$tmp/report-$scenario"
    [[ -f "$tmp/clean-$scenario" ]]
    if grep -Eqi '12:34:56|private-(debug|id)|malicious' "$tmp/report-$scenario"; then exit 5; fi
    case "$scenario" in
        pass) grep -q 'Mac playback return: auto' "$tmp/report-$scenario" ;;
        drop) grep -q 'both Fold profiles reported disconnected' "$tmp/report-$scenario" ;;
        unknown) grep -q 'readings were inconclusive' "$tmp/report-$scenario" ;;
        no_mac) grep -q 'could not hear Mac music' "$tmp/report-$scenario" ;;
    esac
done
echo 'Mac/Fold timeline, privacy, early-stop, and handoff fixtures passed.'
