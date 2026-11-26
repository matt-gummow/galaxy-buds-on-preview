#!/bin/bash
# Apple Silicon macOS. Record OS-reported state while the listener performs one normal handoff.
set -u
umask 077
kit="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "$kit/fold.sh"

status_phone() {
    local line
    line=$(fold_sample) || line=''
    if [[ $line =~ ^(connected|disconnected|unknown)\ (connected|disconnected|unknown)\ (yes|unconfirmed|unknown)\ (yes|unconfirmed|unknown)$ ]]; then
        printf '%s\n' "$line"
    else
        echo 'unknown unknown unknown unknown'
    fi
}

phone_has_profile() {
    case "$1" in connected\ *|*\ connected\ *) return 0 ;; *) return 1 ;; esac
}

both_down() {
    [[ $1 == 'disconnected disconnected '* && $2 == 'disconnected disconnected '* ]]
}

ask() {
    local choice
    printf '%s ' "$1" >&2
    if ! IFS= read -r -t "$2" choice; then return 1; fi
    REPLY=$choice
}

ask_yes_no() {
    while ask "$1 [y/n]" 90; do
        case "$REPLY" in [yY]|[yY][eE][sS]) REPLY=yes; return 0 ;;
                          [nN]|[nN][oO]) REPLY=no; return 0 ;; esac
    done
    return 1
}

mark() {
    local tick
    tick=$("$probe" clock) || return 1
    printf '%s marker %s\n' "$tick" "$1" >> "$work/markers"
}

one_phone_sample() {
    local start end result
    start=$("$probe" clock) || return 1
    result=$(status_phone)
    end=$("$probe" clock) || return 1
    printf '%s phone %s %s\n' "$start" "$end" "$result" >> "$work/phone"
    printf '%s\n' "$result"
}

# The background sampler owns the phone while recording. Wait for a fresh bounded read.
next_phone_after() {
    local threshold=$1 row attempt=0
    while ((attempt < 40)); do
        row=$(awk -v t="$threshold" '$2=="phone" && NF==7 && $1>=t && $3>=$1 && $3-$1<=4000 {print $3,$4,$5,$6,$7; exit}' "$work/phone")
        if [[ -n $row ]]; then printf '%s\n' "$row"; return 0; fi
        sleep 0.2
        attempt=$((attempt + 1))
    done
    printf '%s unknown unknown unknown unknown\n' "$threshold"
}
reveal_report() { /usr/bin/open -R "$1" >/dev/null 2>&1 || :; }

# Timeline contains only data fields with known values, converted to relative milliseconds.
write_report() {
    local summary=$1
    {
        echo 'Galaxy Buds On | synchronized MacBook and Fold test'
        printf 'Outcome: %s\n' "$summary"
        echo 'Mac sample: classic link, default output, default input. "buds" is an exact device match.'
        echo 'Phone: read completion in ms, media profile, call profile, media playing, call audio connected.'
        echo 'Phone reads span an interval. Unknown means unavailable. Unconfirmed audio can include an unavailable service.'
        echo 'Listener responses are timed when entered. This file contains no addresses, device names, call details or audio.'
        LC_ALL=C sort -nk1,1 "$work/mac" "$work/markers" "$work/phone" | awk -v zero="$origin" '
            function conn(x) { return x ~ /^(connected|disconnected|unknown)$/ }
            function route(x) { return x ~ /^(buds|other|unknown)$/ }
            function activity(x) { return x ~ /^(yes|unconfirmed|unknown)$/ }
            $1 !~ /^[0-9]+$/ { next }
            $2=="sample" && NF==5 && conn($3) && route($4) && route($5) { printf "%.0f mac %s %s %s\n",$1-zero,$3,$4,$5 }
            $2=="event" && NF==3 && conn($3) { printf "%.0f mac_link_event %s\n",$1-zero,$3 }
            $2=="phone" && NF==7 && $3 ~ /^[0-9]+$/ && conn($4) && conn($5) && activity($6) && activity($7) {
                printf "%.0f phone %.0f %s %s %s %s\n",$1-zero,$3-zero,$4,$5,$6,$7
            }
            $2=="marker" && NF==3 && $3 ~ /^(baseline|start_mac_music|heard_mac_yes|heard_mac_no|begin_call|heard_call_yes|heard_call_no|return_auto|return_play|return_reconnect|return_none|return_unsure)$/ {
                printf "%.0f listener %s\n",$1-zero,$3
            }'
    } > "$report"
}

finish() {
    trap - EXIT INT TERM HUP
    if [[ -n $phone_pid ]]; then kill "$phone_pid" 2>/dev/null || :; wait "$phone_pid" 2>/dev/null || :; fi
    if [[ -n $mac_pid ]]; then kill "$mac_pid" 2>/dev/null || :; wait "$mac_pid" 2>/dev/null || :; fi
    if [[ $helper_attempted == yes ]]; then
        if ! fold_cleanup; then
            printf '%s\n' 'Check Fold Settings > Apps for Buds On connection check. Remove the copy installed for this test if it is still present.' >&2
        fi
    fi
    if [[ -n $report && -n $origin ]]; then
        if write_report "$outcome"; then
            printf '\nAttach this report here: %s\n' "$report"
            reveal_report "$report"
        else
            echo 'Could not finish writing the report.' >&2
        fi
    fi
    [[ -z $work ]] || rm -rf "$work"
}

run_test() {
    probe="$kit/MacBudsProbe"
    work=''; report=''; origin=''; mac_pid=''; phone_pid=''; helper_attempted=no
    outcome='Partial test; stopped before the final listener response.'
    trap finish EXIT
    trap 'exit 130' INT TERM HUP
    echo 'MacBook + Fold | Galaxy Buds On switch test'
    echo 'Start with the Buds playing audio from your Fold. Disconnect them from the Galaxy Book if it is nearby.'
    echo 'Plug the unlocked Fold into the Mac by USB. Allow USB debugging on the Fold if prompted.'
    while ! fold_setup_usb; do
        ask 'Press Enter to retry USB or Q to quit.' 120 || return 1
        case "$REPLY" in q|Q) return 1 ;; esac
    done
    printf '%s\n' 'Looking for the paired Buds. Allow Bluetooth access on the Mac if prompted.'
    local peer
    peer=$("$probe" target) || {
        echo "Could not identify one paired Galaxy Buds On. Check Mac Bluetooth pairing and the recorder's Bluetooth permission." >&2
        return 1
    }
    [[ $peer =~ ^([A-F0-9]{2}:){5}[A-F0-9]{2}$ ]] || return 1
    echo 'The temporary Fold helper needs Nearby devices to read the Buds connection. The recorder removes its own installation at exit.'
    ask_yes_no 'Install the helper on the connected Fold for this run?' || return 1
    [[ $REPLY == yes ]] || return 0
    helper_attempted=yes
    fold_install "$kit/BudsOverlap.apk" "$peer" yes || return 1
    work=$(mktemp -d "${TMPDIR:-/tmp}/mac-fold-switch.XXXXXXXX") || return 1
    touch "$work/mac" "$work/markers" "$work/phone" || return 1
    local folder="$HOME/Library/Application Support/GalaxyBudsClient/Diagnostics"
    mkdir -p "$folder" || return 1
    report=$(mktemp "$folder/Buds-On-Mac-Fold-XXXXXXXX") || return 1
    mv "$report" "$report.txt" || return 1
    report="$report.txt"
    origin=$("$probe" clock) || return 1
    "$probe" watch <<< "$peer" > "$work/mac" &
    mac_pid=$!
    local initial retry=0 first second heard_call
    until [[ -s "$work/mac" || $retry -ge 15 ]]; do sleep 0.2; retry=$((retry + 1)); done
    if ! kill -0 "$mac_pid" 2>/dev/null || [[ ! -s "$work/mac" ]]; then
        outcome='Preflight: the Mac listener was unavailable.'
        return 1
    fi
    initial=$(one_phone_sample)
    if ! phone_has_profile "$initial"; then
        ask 'Select the Buds on the Fold and play audio, then press Enter.' 90 || return 1
        initial=$(one_phone_sample)
    fi
    if ! phone_has_profile "$initial"; then
        outcome='Preflight: no connected Fold media or call profile was verified. No call needed.'
        echo "$outcome"
        return 0
    fi
    mark baseline
    (while :; do one_phone_sample > /dev/null || break; sleep 0.5; done) &
    phone_pid=$!
    mark start_mac_music
    echo 'Now select the Buds in Mac Control Center > Sound, then play music on the Mac through them.'
    ask_yes_no 'Can you hear the Mac music through the Buds?' || return 1
    mark "heard_mac_$REPLY"
    if [[ $REPLY == no ]]; then
        outcome='Listener could not hear Mac music after selecting the Buds. No call needed.'
        echo "$outcome"; return 0
    fi
    local tuple first_end
    tuple=$(next_phone_after "$("$probe" clock)")
    first_end=${tuple%% *}
    first=${tuple#* }
    tuple=$(next_phone_after "$((first_end + 2000))")
    second=${tuple#* }
    if both_down "$first" "$second"; then
        outcome='After the listener heard Mac music, both Fold profiles reported disconnected on two checks two seconds apart. No call requested.'
        echo "$outcome"; return 0
    fi
    if ! phone_has_profile "$first" && ! phone_has_profile "$second"; then
        outcome='Fold profile readings were inconclusive after Mac audio started. No call requested.'
        echo "$outcome"; return 0
    fi
    mark begin_call
    echo 'Make or take one call on the Fold. Listen through the Buds for about 10 seconds, hang up, and give the Mac 10 seconds to resume. Leave Bluetooth controls alone during that interval.'
    ask_yes_no 'After hanging up: did you hear the call through the Buds?' || return 1
    heard_call=$REPLY
    mark "heard_call_$heard_call"
    echo 'How did Mac music return? 1 automatically, 2 after pressing Play, 3 only after reconnecting, 4 it never returned, 5 unsure.'
    local result=''
    until [[ -n "$result" ]]; do
        ask 'Enter 1, 2, 3, 4, or 5.' 90 || return 1
        case "$REPLY" in 1) result=auto ;; 2) result=play ;; 3) result=reconnect ;; 4) result=none ;; 5) result=unsure ;; esac
    done
    mark "return_$result"
    outcome="Completed. Listener heard Fold call: $heard_call. Mac playback return: $result."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    run_test
    exit $?
fi
