# Recorded validation

Validation date: 2026-10-15 UTC (2026-10-14 in the lab's local time).

## Public repository verification

The newly packaged `scripts/run-fpga-smoke.sh` was run on the existing VCK190
installation against its pinned Caliptra source and existing FPGA image:

```text
test smoke_test::smoke_test ... ok
test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured;
8 filtered out; finished in 116.71s
exit status: 0
```

Four FPGA identity checks reported revision `61a20816`, and four Caliptra runtime
boots appeared in the log. Native host-test compilation took 25.98 seconds
before the timed test. No FPGA image replacement or system reboot was performed.
The boot-image hash still matched the corrected artifact. The post-test kernel
log contained no lockup, RCU stall, SD removal, I/O, or ext4 errors, and there
were no failed systemd services.
The raw log remains with the lab maintainer; its SHA-256 is
`2b6e5e053d12219c20ddf9ae07ce6e189221e80a0edf7a2802ba3c1197c1741b`.
The tested launcher's SHA-256 is
`831f2f350fca5a6d2e8cb6466e47fa994f0ce862a27a219224cef91cc889ce05`.

`scripts/prepare-source.sh` completed in a fresh directory on the workstation.
All 18 nested submodule revisions matched `manifests/submodule-revisions.txt`.
The upstream submodule stayed clean, and the four patched FPGA source files
were byte-identical to the source used for the tested image. Both PetaLinux
patches applied in sequence to the pinned source and reproduced the tested
Linux and U-Boot SD/MMC configuration files. Shell/Python syntax and internal
documentation links were checked.

## Original image bring-up

- Physical VCK190 Caliptra smoke test: 1 passed, 0 failed, exit 0.
- Four FPGA identity checks and four successful runtime boots, covering both
  PQC verification choices and both certificate algorithm choices.
- Initial test time: 844.29 seconds, including firmware builds.
- Ubuntu: 22.04.2, kernel `5.15.0-1020-xilinx-zynqmp`, CPUs 0–1 online.
- Native ARM64 Rust/Cargo 1.96.1; RISC-V firmware target installed.
- UIO module built against that Ubuntu kernel; device name
  `caliptra-fpga-uio-dev`.
- Corrected boot completed through a software reboot and SSH returned with a
  1 Gbps/full-duplex link. Both Ethernet PHY drivers attached.
- No post-test lockup, SD I/O/ext4 error, or failed systemd service was found.
- Boot-image partition comparison showed only the embedded Linux DTB changed
  between the original and corrected boot artifacts.
- An offline build/test-list check passed after stopping the dependency proxy;
  that check was not a second physical test.

## Limits

This is targeted bring-up and smoke-test validation, not the full Caliptra
regression or board qualification. CDC/JTAG review, PCIe/ITS support, sustained
power/thermal testing, cold-boot reliability, and RTC retention remain outside
the validated scope. Unused USB SuperSpeed and QSPI device-description warnings
remain. U-Boot uses its default environment.

The public parameterized launcher retains the original Cargo invocation and
adds host/UIO checks, log-directory configuration, and a same-account lock.
Its physical test used the existing board source/cache and existing FPGA image;
it does not validate a complete image rebuild from a fresh machine.

Passwords, machine identities, raw serial logs, and full source/build archives
are not included in this public package. The maintainer retains the original
logs, revision manifest, and boot partition comparison.
