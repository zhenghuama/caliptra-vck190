# Setup from the base SD image and a built Caliptra image

## Images and hardware

The tested base is Canonical's
[`iot-limerick-versal-classic-server-2204-x02-20230315-48.img.xz`](https://people.canonical.com/~platform/images/xilinx/versal-ubuntu-22.04/iot-limerick-versal-classic-server-2204-x02-20230315-48.img.xz).
Its Ubuntu 22.04 kernel/root filesystem remain in use. PetaLinux supplies the
Caliptra boot firmware, PL configuration, and device tree; its root filesystem
and kernel do not replace Ubuntu in this procedure.

Flash the whole Ubuntu disk image to the removable main SD card using an image
writer and verify the write. The tested card is 16 GB. Put it in **J302, the top
main-processor slot**. Leave the system-controller card in **J206 underneath**.
SW1: switch 1 ON; switches 2, 3, 4 OFF. J207 USB-C provides JTAG and UART.
Use the board's specified power supply; the legacy 12 V / 5 A supply used during
bring-up was not qualified for full-board loads.

The tested board assembly is `043-05005-01-105`, requiring the new SD level-shifter
configuration. Do not apply that preset to a different board revision blindly.

## First Ubuntu boot and network

Open the correct PS UART before booting: 115200 baud, 8 data bits, no parity,
1 stop bit, no flow control. On Linux, select the VCK190's persistent
`/dev/serial/by-id/` path ending `if01-port0`, not an assumed `ttyUSB` number.
Interface 03 is the system-controller UART. Identify the board before connecting
when multiple development boards are attached.

Complete Ubuntu's first-login/password flow and verify the clock with `date -u`.
An incorrect clock can break TLS and package downloads. If corrected, synchronize
the RTC with `sudo hwclock --systohc --utc`; RTC retention has not been tested.

The tested arrangement uses a dedicated USB Ethernet adapter on the workstation
and a direct cable to the VCK190. Configure a manual link with no gateway and no
default-route takeover. Example new NetworkManager profiles (replace
`YOUR_USB_ETHERNET_INTERFACE` with the adapter you identified):

```bash
# Workstation: dedicated adapter only; inspect existing profiles before adding.
sudo nmcli connection add type ethernet ifname YOUR_USB_ETHERNET_INTERFACE \
  con-name vck190-direct ipv4.method manual ipv4.addresses 192.168.77.1/24 \
  ipv4.never-default yes ipv6.method link-local ipv6.never-default yes
sudo nmcli connection up vck190-direct

# Board: run through its serial console, on a new/unconfigured installation.
sudo nmcli connection add type ethernet ifname eth0 con-name casa-direct \
  ipv4.method manual ipv4.addresses 192.168.77.2/24 ipv4.never-default yes \
  ipv6.method link-local ipv6.never-default yes
sudo nmcli connection up casa-direct
sudo systemctl enable --now ssh
```

Do not create duplicate profiles on the already configured lab setup. Its
`vck190-direct` and `casa-direct` profiles already persist. No Internet gateway,
NAT, or institutional network changes are required for this direct SSH link.

## Dependencies on the Arm board

Keep the tested Ubuntu kernel. Its UIO module must be built against its own
matching headers; the PetaLinux 6.6 module cannot be loaded into Ubuntu's 5.15
kernel. With package access available:

```bash
sudo apt update
sudo apt install make gcc g++ pkg-config cmake git curl ca-certificates \
  linux-headers-$(uname -r)
```

Install Rust using [rustup](https://rustup.rs/), then use the toolchain selected
by the pinned source's `rust-toolchain.toml` and add
`riscv32imc-unknown-none-elf`, `rustfmt`, and `clippy`. The tested ARM64
installation resolved to Rust 1.96.1. Do not perform a general OS/kernel upgrade
as part of this setup.

If the board only has the direct link, `scripts/dependency-proxy.py` is the
temporary dependency proxy used during bring-up. Run it on the workstation,
then in a second workstation terminal open:

```bash
ssh -o ExitOnForwardFailure=yes \
  -R 127.0.0.1:18080:127.0.0.1:18080 ubuntu@192.168.77.2
```

In that board shell, set `http_proxy` and `https_proxy` to
`http://127.0.0.1:18080`. For apt, pass
`-o Acquire::http::Proxy=http://127.0.0.1:18080` and
`-o Acquire::https::Proxy=http://127.0.0.1:18080` explicitly to `sudo apt`.
The proxy listens on workstation loopback and allows the listed dependency
destinations only. It is not a general Internet gateway. Stop the proxy and SSH
tunnel after downloads, and unset the proxy variables. A new destination may
need a reviewed allowlist addition.

Use `scripts/prepare-source.sh "$HOME/caliptra-sw"` on a new board to retrieve
the pinned source, initialize nested submodules, and apply the recorded FPGA
changes. It refuses to overwrite an existing directory. The existing lab board
already has its prepared source and cached dependencies.

## Caliptra boot file and device-tree correction

Back up the contents of `/boot/firmware` before changing it. The custom file is
`/boot/firmware/boot1900.bin`. Preserve stock `boot1901.bin`, `boot.bin`,
`boot.scr.uimg`, and `image.fit`. A boot file is not a whole-disk image; do not
write it directly over the SD card.

The original built image needed an additional correction in
`board/board-fix.dtsi`: explicit TI DP83867 PHY nodes/handles for Ethernet and
disabling an unused GIC ITS. PCIe is disabled in this design. ITS disabling is a
workaround, not a root-cause fix; revisit it before enabling PCIe/MSI.

| Recorded artifact | SHA-256 |
| --- | --- |
| Original built boot file | `68200ff68879d0a8371de6464371c13a7b98961868164d6248e70b6399eb31c3` |
| Corrected, tested boot file | `0de8ea18419627c486e188b4b8bf3ed3babe4eeb5d75fac8a592707c9c330acb` |

Obtain the corrected file from the maintainer through the lab artifact handoff.
It is not included in Git. Verify its hash, copy it to `boot1900.bin`, sync, and
reboot with the correct UART already recording. A software reboot successfully
loaded the corrected image during validation; a physical power cycle was not
needed. The previous stock-image boot selector initially remained at 1901 across
a reboot and required a targeted, verified selector correction. If the PL is
still stock, inspect the boot selection rather than repeatedly rebooting or
blindly writing hardware registers. Automatic fallback does not recover every
late Linux failure; retain physical SD recovery access for new deployments.

After reboot, verify SSH, the Ubuntu kernel, Ethernet, and kernel logs. Then run
the upstream `setup_fpga.sh` and the exact smoke test from [the user guide](usage.md).
Expected FPGA wrapper magic is `0x52545043`; the tested version is `0x61a20816`.

## Rebuilding the FPGA and boot image later

Use Vivado 2024.2 (tested patch level 2024.2.2) with XCVC1902 device support and
the `xilinx.com:vck190_newl:part0:1.2` board definition, plus PetaLinux 2024.2.
Board definitions do not substitute for device support or the required Vivado
license entitlement. Use separate clean tool environments; the experimental
2025.2 packaging helpers are not part of this tested workflow.

Prepare the source, change into its `hw/fpga` directory, and choose a NEW output
directory: the upstream Tcl script deletes/recreates `OUTPUT_DIR`.

```bash
vivado -mode batch -source fpga_configuration.tcl -tclargs \
  BUILD=TRUE BOARD=VCK190 VCK190_NEW_SD_LEVEL_SHIFTER=TRUE \
  ITRNG=TRUE SEGMENTED=FALSE RTL_VERSION=latest \
  JOBS=4 THREADS=2 OUTPUT_DIR=caliptra_build
```

Copy `create_boot_bin.sh`, `update_boot_bin.sh`, `io_module/`, and
`petalinux_project/` to an isolated software build directory. The PetaLinux
project needs its old absolute Kconfig paths regenerated/rebased to that
directory. Disable automatic TFTP copying and set BitBake/build parallelism to
2 if sharing a limited-memory workstation.

In that isolated directory, apply `patches/petalinux-new-sd-level-shifter.patch`
and then `patches/petalinux-deterministic-mmc-alias.patch` using `git apply`.
They adjust both Linux and U-Boot device trees. Source PetaLinux 2024.2, **unset
`BUILD_SS`**, and run `./create_boot_bin.sh /absolute/path/to/caliptra_fpga.xsa`.
Setting `BUILD_SS=FALSE` still selects the subsystem module in the upstream
script; unset it for this core design.

The build imports the XSA and packages a boot image. Preserve its Ubuntu UART
(`arm,sbsa-uart`) and Versal GPIO adaptations. Integrate `board-fix.dtsi` in the
Linux device-tree source after checking for duplicate PHY nodes, rebuild the
DTB, and repackage with the matching PDI/PLM/PSM/BL31/U-Boot. The tested artifact
was corrected after the original build; that original project does not already
contain this final fix. The saved `board/bootgen.bif.example` illustrates the
tested packaging structure with portable placeholder paths.

Audit the actual generated DTB and packaged payloads before deploying. A clean
end-to-end rebuild from this newly packaged repo is still unverified; the
published patches and notes preserve the working configuration and observed
fixes, not a claim of bit-identical reproducibility.
