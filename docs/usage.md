# User guide

## 1. What runs where

| Component | Location and responsibility |
| --- | --- |
| Linux build workstation | Runs Vivado/PetaLinux, keeps build artifacts, and provides SSH access to the board |
| VCK190 Arm processing system (PS) | Runs Ubuntu, the UIO driver, Rust host tests, and SSH |
| VCK190 programmable logic (PL) | Implements Caliptra RTL, its RISC-V processor, and the FPGA wrapper |
| Caliptra firmware | ROM, FMC, and runtime firmware execute on Caliptra's RISC-V processor |

The Arm test process accesses the PL through `/dev/uio0` and AXI memory-mapped
registers. It loads firmware and exercises the physical Caliptra core. This flow
uses `fpga_realtime`, not a software emulator or `fpga_subsystem`. Vitis AI and AI
Engine workloads are not part of this setup.

| Interface | Address |
| --- | --- |
| FPGA wrapper registers | `0xA4010000` |
| Caliptra public register space | `0xA4100000` |
| ROM backdoor (96 KiB) | `0xB0000000` |

The tested upstream checkout is commit
`61a20816d836d39f2c97c151bce08dc5e7c199cd` plus the FPGA patch in this repo.
The corresponding RTL is `49370266d12cb0c4a8f71b3a0ff7e54ba7d4866e` (v2.1.2).
See `manifests/submodule-revisions.txt` for nested revisions.

The original shared board has its source at `~/caliptra-sw`. That installation
is a build snapshot: nested submodule working files were copied without their
Git metadata. Use a fresh checkout prepared by this repo for source development.

## 2. Access and smoke test

Obtain the workstation SSH hostname/account and board password from the lab
maintainer. They are intentionally not stored in this public repository. The
documented direct-link example uses workstation `192.168.77.1` and board
`192.168.77.2`; these are private LAN examples, not public access endpoints.

From the workstation:

```bash
ssh ubuntu@192.168.77.2
```

On the **VCK190** (after each reboot):

```bash
cd ~/caliptra-sw
sudo ./hw/fpga/setup_fpga.sh
cat /sys/class/uio/uio0/name
# Expected: caliptra-fpga-uio-dev
```

The upstream setup script builds/loads the UIO module for the running kernel,
disables the relevant deep CPU-idle states, and grants access to `/dev/uio0`.
No automatic setup service was installed.

For the existing lab installation, its original, tested launcher is:

```bash
~/caliptra-deploy-20261014/run-fpga-smoke.sh
```

For a clone of this infrastructure repo on the board, use its parameterized
launcher instead:

```bash
CALIPTRA_SRC="$HOME/caliptra-sw" ./scripts/run-fpga-smoke.sh
```

Run that command from this infrastructure repo's root. Logs go to
`~/caliptra-vck190-logs/`; `latest-smoke-prefix` points to the latest `.log` and
`.exit` pair. The original lab launcher uses `~/caliptra-deploy-20261014/`.

Success requires both a zero exit status and an actual test result:

```text
test smoke_test::smoke_test ... ok
test result: ok. 1 passed; 0 failed; ...
```

Zero tests is not a pass. The `slow_tests` feature is required. The launcher
selects exactly this integration test and imposes a 30-minute timeout. The
initial physical run took 844.29 seconds, including firmware compilation;
the earlier native test compilation took about 15 minutes.

The launcher defaults to offline Cargo mode because the original board has
cached dependencies. For a fresh board, provide dependency access and use
`CARGO_NET_OFFLINE=false` on the first run. Install the repository's Rust
toolchain and `riscv32imc-unknown-none-elf` target first.

Coordinate exclusive board use before testing or rebooting. The new launcher's
lock prevents two copies of that launcher under the same Unix account; it cannot
arbitrate other users or other tools. No Vivado installation is needed merely
to SSH into the already configured board and run its test.
