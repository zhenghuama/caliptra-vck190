# Caliptra on VCK190

Infrastructure and recorded fixes for running Caliptra firmware tests against
Caliptra RTL on an AMD VCK190. The verified system combines an Ubuntu 22.04 SD
installation with a Caliptra boot image built with Vivado 2024.2.2 and PetaLinux
2024.2. Ubuntu runs on the Arm processing system; Caliptra hardware runs in the
programmable logic.

The targeted physical FPGA smoke test passed on 2026-10-15 UTC: **1 passed,
0 failed, exit 0**. See [validation and limitations](docs/validation.md).

## Start here

- [Access the board, understand the architecture, and run the test](docs/usage.md)
- [Set up a board from the Ubuntu and Caliptra images](docs/setup.md)
- [Publish, collaborate, and add optional private repositories](docs/collaboration.md)

This repository contains setup instructions, a source bootstrap, the smoke-test
launcher, FPGA patches, and device-tree corrections. It does not contain AMD
tools, license files, passwords, full disk images, or generated FPGA artifacts.

## Source layout

`upstream/caliptra-sw` is a Git submodule pointing to the official
`chipsalliance/caliptra-sw` repository at the tested commit, also recorded in
`versions.env`. That upstream project has its own nested Caliptra submodules.
`scripts/prepare-source.sh` initializes the top-level submodule, creates an
independent ignored working checkout in `work/caliptra-sw`, initializes its
submodules at their recorded commits, and applies the FPGA patch. The four
modified FPGA files are intentional; the patch in this infrastructure repository
is the tracked source of those changes. The upstream submodule stays clean.

```bash
./scripts/prepare-source.sh
```

The script refuses an existing destination. It does not change a working board,
flash anything, or start an FPGA build. It needs Internet access to GitHub.

Private projects can later be added as optional submodules. The public bring-up
flow should continue to work without access to those projects.

## Reproduction scope

The existing hardware image and newly packaged launcher passed the physical
test: 1 passed, 0 failed in 116.71 seconds, exit 0. The source bootstrap also ran
successfully from a fresh working directory; all 18 nested submodule revisions
match the recorded setup. A clean FPGA/PetaLinux rebuild using this repository
has not yet been performed. The build notes retain
the required changes, including the post-build device-tree correction; this is
not yet a one-command image build system.

Licensed under Apache-2.0; upstream dependencies retain their own licenses.
