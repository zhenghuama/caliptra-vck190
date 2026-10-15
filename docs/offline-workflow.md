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
provide new Cargo packages, Rust toolchains, or Ubuntu packages. If an update
introduces uncached dependencies, use the temporary dependency proxy described
in [setup](setup.md), or provision those dependencies separately. No permanent
Internet sharing or network gateway change is needed.

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
