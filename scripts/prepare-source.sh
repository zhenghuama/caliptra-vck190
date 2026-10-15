#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Creates a NEW checkout only; never changes an existing checkout or the board.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$root/versions.env"
dest=${1:-"$root/work/caliptra-sw"}
if [[ -e "$dest" || -L "$dest" ]]; then
    printf 'Refusing existing destination: %s\nChoose a new directory.\n' "$dest" >&2
    exit 2
fi
mkdir -p -- "$(dirname -- "$dest")"
git -C "$root" submodule update --init -- upstream/caliptra-sw
upstream="$root/upstream/caliptra-sw"
if [[ "$(git -C "$upstream" rev-parse HEAD)" != "$CALIPTRA_REV" ]]; then
    echo 'Submodule revision and versions.env disagree; refusing to prepare.' >&2
    exit 2
fi
# Copy the pinned Git repository into an independent, ignored work checkout.
# Keep the upstream submodule itself clean; patch only this working copy.
git clone --no-hardlinks --no-checkout "$upstream" "$dest"
git -C "$dest" remote set-url origin "$CALIPTRA_UPSTREAM"
git -C "$dest" checkout --detach "$CALIPTRA_REV"
git -C "$dest" apply --check "$root/patches/caliptra-sw-vck190.patch"
git -C "$dest" apply "$root/patches/caliptra-sw-vck190.patch"
git -C "$dest" submodule update --init --recursive
printf '\nPrepared %s at %s plus the recorded FPGA patch.\n' "$dest" "$CALIPTRA_REV"
printf 'The four modified FPGA files are intentional. No build or device access ran.\n'
