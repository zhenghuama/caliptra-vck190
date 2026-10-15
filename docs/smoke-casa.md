# One-command smoke test from casa

Run from the infrastructure checkout on casa:

```bash
make smoke-casa
```

For a fresh clone, first run `./scripts/prepare-source.sh` once on casa. The
target uses that prepared `work/caliptra-sw` checkout, including tracked edits
and non-ignored new files. It does not automatically pull/reset your source.

Normal SSH password authentication is supported. You enter the board password
once per invocation; the command reuses that SSH connection for transfer,
execution, and result collection. After a board reboot, UIO/CPU-idle setup may
also need a sudo password prompt, handled from the same casa terminal.
No credentials are stored by these scripts. The board's SSH host key must
already be known from its initial SSH setup.

## What the target does

1. Checks that the SSH target is ARM64 Versal, rejecting the ZynqMP/ZU3 board.
2. Snapshots the selected Caliptra source and initialized nested submodules on
   casa. Records commits, file hashes, dirty state, and the exact launcher files.
3. Starts a persistent board worker and acquires the same UIO lock used by the
   standalone smoke launcher. A busy board is rejected before source syncing.
4. Syncs into its dedicated board source mirror and verifies every source hash.
   Only this owned mirror is synchronized with deletion enabled. The original
   `~/caliptra-sw`, existing boot image, and original launcher remain available.
5. Runs the usual board setup if needed, then builds/tests on the board with
   locked, offline Cargo dependencies. No board Internet access is required.
6. Collects test output, exit status, source provenance, timing, and available
   health/kernel information back to casa. An unavailable optional sensor is
   reported as unavailable. Zero tests is treated as a failure.

The command requires Python 3.8+, Git, OpenSSH, rsync, and make on casa. The
board needs Python 3, rsync, its existing Rust/RISC-V toolchain, cached Cargo
dependencies, matching kernel headers, and the working Caliptra FPGA image.
At least 3 GiB of free board storage is required before a run. Adding new
dependencies still requires an offline dependency handoff; the target does
not install tools, provide Internet access, or reflash/reboot the board.
Changes to RTL or the FPGA design still require a separate FPGA image build and
deployment. Synchronizing an RTL file does not change the design already loaded
in the PL; this target runs software/firmware against the current FPGA image.

The first run in the dedicated build directory can take substantially longer.
Later runs reuse the board's persistent native build cache. A failed source
sync does not start the test; the preparation reservation expires after ten
minutes if casa disconnects before completing it.

## Locations and configuration

On casa:

- `artifacts/smoke-casa/<run-id>/`: exact source snapshot, manifest, patches,
  and launcher copies. These can contain private project sources.
- `logs/smoke-casa/<run-id>/`: returned `status.json`, `console.log`, test logs,
  source manifest, health records, and kernel log when readable.

Both trees are ignored by Git. Snapshots/results are retained for review;
remove obsolete run directories when they are no longer needed.

On the VCK190, the managed directory is
`~/.local/share/caliptra-vck190-casa/`. It contains the source mirror in
`work/caliptra-sw`, build cache in `target`, and records in `runs/<run-id>`.
Do not edit its mirror directly; edit on casa. The next run synchronizes it
from the casa snapshot. All users of the shared board should coordinate through
the same board account and this launcher; unrelated manual tools do not
automatically participate in its lock.

Overrides:

```bash
make smoke-casa BOARD_HOST=ubuntu@192.168.77.2 CALIPTRA_SRC=/absolute/path/to/caliptra-sw
```

`CALIPTRA_SRC` must be a real Git checkout with initialized submodules. A board
snapshot containing submodule files without their Git metadata is not a suitable
source for the casa snapshot step. The default prepared checkout meets this
requirement.

## Timing and interrupted connections

`status.json` reports `launcher_wall_seconds`, measured with a monotonic clock
on the VCK190. It starts after syncing, verification, and board setup, and includes
native compilation and the smoke invocation. `test_reported_seconds` is the
Rust test harness duration; firmware compilation within the test can contribute
to it. These are functional-test timings, not isolated Caliptra performance
benchmarks. SSH/file-transfer time is excluded from both.

The board writes logs locally and the worker survives an SSH disconnect. If
casa loses its connection, or you interrupt waiting after execution starts,
the test can continue on the board up to the workflow's 60-minute timeout.
This allows for both native and firmware compilation on the first run; the
standalone launcher retains its default 30-minute timeout.
The run ID is printed at startup. Retrieve its status and logs later with:

```bash
make smoke-casa-results RUN=20261015T060933Z-f50cc27c
```

Use your actual run ID. This target only retrieves results; it does not rerun the
test. The Python command returns a completed run's recorded exit status; make
reports failure with its own nonzero status when that command fails. The exact
board status is retained in `status.json`. An incomplete run returns nonzero
and can be collected again later. A failure to retrieve results also returns
nonzero, even if the board test itself may have passed.

The worker records available thermal/CPU information and kernel logs. Access
limitations are recorded; missing telemetry is not interpreted as a clean bill
of health. The target's pass/fail reflects the actual smoke test and execution
checks. Precise benchmark instrumentation should define separate measured
boundaries on the board, as described in [the offline workflow](offline-workflow.md).
