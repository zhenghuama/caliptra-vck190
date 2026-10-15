# Working with a board that has no Internet access

```text
GitHub <-- Git over the Internet --> casa
                                     |
                              SSH / SCP over
                          the direct Ethernet link
                                     |
                                  VCK190
```

The public repository was pushed from **casa**. The VCK190 does not connect to
GitHub in the normal workflow. Run the clone, pull, push, and source-bootstrap
commands on casa or another Internet-connected development workstation.

## Recommended daily workflow

Use casa as the development, deployment, and results host. Keep the VCK190
offline on its private Ethernet link. No NAT, network bridge, Internet sharing,
or changes to the workstation's authenticated external network are needed.

1. On casa, use `git pull --ff-only` in the infrastructure checkout and edit on
   a development branch. Fetch Caliptra and its nested submodules there using
   `scripts/prepare-source.sh` with a new destination when preparing a new version.
2. Transfer the required scripts or prepared source to the VCK190 with `scp` or
   `rsync` over its existing SSH link. Stage a new source version in a new board
   directory, preserving the known-working `~/caliptra-sw` installation.
3. SSH into the board and build/run the native ARM test there. Do not transfer
   workstation `target/` build products as though they were board binaries.
4. Copy logs and any board-side edits back to casa, review them, then commit and
   push from casa. Transfer new/untracked source files explicitly if using a
   patch for tracked edits; `git diff` alone does not include them.

For example, updating only the launcher from casa:

```bash
cd ~/caliptra-vck190
git pull --ff-only
scp scripts/run-fpga-smoke.sh ubuntu@192.168.77.2:~/run-caliptra-smoke.sh
ssh ubuntu@192.168.77.2
```

Then on the VCK190, after verifying the UIO setup described in the user guide:

```bash
CALIPTRA_SRC="$HOME/caliptra-sw" bash ~/run-caliptra-smoke.sh
```

The board already has a source snapshot including nested submodule working
files, its Rust toolchain, and cached Cargo dependencies. That is how the tested
smoke run operates with `CARGO_NET_OFFLINE=true`. Source transfer alone does not
provide new Cargo packages, Rust toolchains, or Ubuntu packages. For future
updates introducing uncached dependencies, prepare an offline dependency package
on casa and transfer it alongside the source. `cargo vendor --locked` can
collect crates.io and Git dependencies; merge its emitted source-replacement
configuration with the existing `.cargo/config.toml`, preserving Caliptra's
RISC-V flags and aliases. Separate Cargo workspaces may need explicit `--sync`
manifests. See [Cargo's vendor documentation](https://doc.rust-lang.org/cargo/commands/cargo-vendor.html).

Vendoring does not package the Rust toolchain, Ubuntu packages, external build
tools, or arbitrary downloads made by build scripts. Provision any such changes
separately for the board's ARM64 Ubuntu environment and RISC-V firmware target;
do not copy casa's x86 executables as board tools. Keep dependencies pinned and
verify the complete build/test with Cargo locked and offline before accepting
an update. The existing cache-based flow is tested; a portable vendored
dependency package has not yet been implemented or validated. The temporary
proxy in the setup guide is an optional provisioning alternative, not a
requirement of the selected casa-centric workflow.

## Timing and measurements run on the VCK190

Casa may launch an SSH command, but the actual test process and measurement
code run on the VCK190's Arm processing system and exercise Caliptra in the PL.
Do not use a stopwatch around `ssh`, deployment, or log copying as a board
performance measurement.

Use this sequence for repeatable experiments:

1. On casa, prepare a versioned source/dependency package and record the
   infrastructure commit, Caliptra commit, submodule revisions, patches, and
   relevant FPGA image hash. Transfer it into a new staging directory on the
   board while keeping the known-working installation available.
2. On the board, verify the package, build native test binaries, and perform
   any required warm-up. Keep compilation and warm-up separate from the timed
   operation unless measuring startup is the explicit experiment.
3. Start and stop measurement inside the board-side test. Use a monotonic clock
   for Arm-side elapsed time. For a Caliptra cycle-count experiment, use an
   appropriate validated device-side counter and record the configured clock;
   host wall time and Caliptra cycle counts answer different questions.
4. Write measurements and logs locally on the board, including exit status,
   iterations, units, exact timed boundary, source/image versions, kernel,
   compiler, and relevant CPU/thermal conditions. Avoid source transfers or
   unrelated tests during the timed interval. Serialize use of the shared board.
5. After the run ends, copy results back to casa for analysis and storage. Promote
   a staged version to the working setup only after its checks pass; keep the
   preceding version available for rollback.

The smoke test is a functional check. Its reported duration can include firmware
building and several hardware boot/test combinations; it is not a standalone
Caliptra performance benchmark. The 116.71-second verification was measured by
the test running on the VCK190, with host-test compilation reported separately.
Benchmark instrumentation and automated versioned deployment are future work;
the current repo provides source preparation, the board-side smoke launcher,
and the manual transfer workflow.

## Optional: keep the infrastructure Git history on the offline board

Git bundles carry commits and refs in a file that can be transferred over SCP.
They do **not** include submodule repositories or uncommitted changes. See
[the official Git bundle documentation](https://git-scm.com/docs/git-bundle).

On casa, create a bundle of the committed infrastructure `main` branch:

```bash
cd ~/caliptra-vck190
mkdir -p artifacts
git bundle create artifacts/caliptra-vck190.bundle main
scp artifacts/caliptra-vck190.bundle ubuntu@192.168.77.2:~/
```

On the board, for the first clone into a directory that does not already exist:

```bash
git clone -b main ~/caliptra-vck190.bundle ~/caliptra-vck190
```

For subsequent updates, recreate and transfer the bundle from casa, then run
on the board:

```bash
cd ~/caliptra-vck190
git fetch ~/caliptra-vck190.bundle main
git merge --ff-only FETCH_HEAD
```

This updates infrastructure scripts/docs without Internet access. It does not
populate `upstream/caliptra-sw` or its nested submodules. For the current board,
continue using the existing `~/caliptra-sw` with `CALIPTRA_SRC`. For a new source
snapshot, transfer the prepared working files from casa, including every nested
submodule's files; omit `.git` entries and `target/` products. Record the source
revision and applied patches with the snapshot. A plain `git archive` of the
parent repo does not recursively include submodule contents.

To return committed infrastructure edits from the board, make a named branch
and commit there. On casa, fetch that board branch directly over the existing
SSH link and review it on a local branch:

```bash
# Example: the board branch is named board-change.
git fetch ubuntu@192.168.77.2:/home/ubuntu/caliptra-vck190 board-change
git switch -c review-board-change FETCH_HEAD
# Review the diff, then publish the branch from casa for a pull request.
git push -u origin review-board-change
```

GitHub credentials stay on the development workstation. The current board's
Caliptra snapshot lacks nested submodule Git metadata, so use it for execution;
maintain upstream/submodule development checkouts on casa. Optional private
repositories follow the same download-on-casa and authorized-transfer process.
