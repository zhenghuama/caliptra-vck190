#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run ON the VCK190 after setup_fpga.sh. This test changes Caliptra hardware state.
set -uo pipefail
model=$(tr -d '\0' </proc/device-tree/model 2>/dev/null || true)
compatible=$(tr '\0' '\n' </proc/device-tree/compatible 2>/dev/null || true)
# The tested VCK190 device tree reports the generic model "Xilinx Versal".
# Require Versal plus the Caliptra UIO identity below; ZynqMP boards are rejected.
if [[ "$(uname -m)" != aarch64 ]] || ! grep -Fqx 'xlnx,versal' <<<"$compatible"; then
    printf 'Expected an ARM64 Versal host; detected: %s\n' "$model" >&2
    exit 2
fi
[[ ! -f "$HOME/.cargo/env" ]] || source "$HOME/.cargo/env"
src=${CALIPTRA_SRC:-"$HOME/caliptra-sw"}
logdir=${CALIPTRA_LOG_DIR:-"$HOME/caliptra-vck190-logs"}
uio=${CPTRA_UIO_NUM:-0}
[[ "$uio" =~ ^[0-9]+$ ]] || { echo 'CPTRA_UIO_NUM must be numeric.' >&2; exit 2; }
cd -- "$src" || exit 2
if [[ "$(cat "/sys/class/uio/uio$uio/name" 2>/dev/null)" != caliptra-fpga-uio-dev ]]; then
    echo 'From the Caliptra checkout, run sudo ./hw/fpga/setup_fpga.sh first.' >&2
    exit 2
fi
[[ -r "/dev/uio$uio" && -w "/dev/uio$uio" ]] || { echo 'UIO device is not accessible.' >&2; exit 2; }
for cmd in cargo timeout tee flock; do
    command -v "$cmd" >/dev/null || { printf 'Missing command: %s\n' "$cmd" >&2; exit 2; }
done
# Serializes this launcher for the SAME login account, including different logdirs.
# Separate Unix accounts still need to coordinate exclusive use of the board.
lockdir=${XDG_CACHE_HOME:-"$HOME/.cache"}/caliptra-vck190
mkdir -p -- "$logdir" "$lockdir" || exit 2
if [[ -n "${CALIPTRA_LOCK_FD:-}" ]]; then
    [[ "$CALIPTRA_LOCK_FD" =~ ^[0-9]+$ ]] || { echo 'Invalid inherited lock descriptor.' >&2; exit 2; }
    exec 9>&"$CALIPTRA_LOCK_FD" || exit 2
    [[ "$(readlink /proc/$$/fd/9)" == "$lockdir/uio$uio.lock" ]] || { echo 'Unexpected inherited lock file.' >&2; exit 2; }
else
    exec 9>"$lockdir/uio$uio.lock"
fi
flock -n 9 || { echo 'Another smoke launcher holds the board lock.' >&2; exit 2; }
export CPTRA_UIO_NUM="$uio" CARGO_BUILD_JOBS=2 CARGO_INCREMENTAL=0
export CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0
export CARGO_NET_GIT_FETCH_WITH_CLI=true
# The tested board has a populated Cargo cache. Set false for a first online run.
export CARGO_NET_OFFLINE=${CARGO_NET_OFFLINE:-true}
out="$logdir/smoke-$(date -u +%Y%m%dT%H%M%SZ)-$$"
printf '%s\n' "$out" >"$logdir/latest-smoke-prefix"
timeout --signal=TERM --kill-after=15s 30m cargo test --locked \
    --features=fpga_realtime,itrng,slow_tests -p caliptra-test \
    --test caliptra_integration_tests smoke_test::smoke_test \
    -- --exact --nocapture 2>&1 | tee "$out.log"
statuses=("${PIPESTATUS[@]}")
result=${statuses[0]}
if (( result == 0 && statuses[1] != 0 )); then result=${statuses[1]}; fi
printf '%s\n' "$result" >"$out.exit"
exit "$result"
