"""Makes sure Apple Silicon Macs can run dara's BGMN binaries, which are built for Intel (x86_64) only."""

import platform
import struct
import subprocess
import sys
from pathlib import Path

INSTALL_CMD = ["/usr/sbin/softwareupdate", "--install-rosetta", "--agree-to-license"]
ARM64 = 0x0100000C


def _bgmn_has_arm64():
    """True if dara's BGMN binary already runs natively; False if it is Intel-only or not downloaded yet."""
    try:
        import dara

        data = (Path(dara.__file__).parent / "bgmn/BGMNwin/bgmn").read_bytes()[:4096]
    except Exception:
        return False
    magic = data[:4]
    if magic == b"\xcf\xfa\xed\xfe":  # thin 64-bit Mach-O
        return struct.unpack("<i", data[4:8])[0] == ARM64
    if magic == b"\xca\xfe\xba\xbe":  # universal binary
        n = struct.unpack(">I", data[4:8])[0]
        return any(struct.unpack(">i", data[8 + 20 * i : 12 + 20 * i])[0] == ARM64 for i in range(min(n, 50)))
    return False


def _rosetta_installed():
    try:
        return subprocess.run(["/usr/bin/arch", "-x86_64", "/usr/bin/true"], capture_output=True).returncode == 0
    except OSError:
        return False


def ensure_rosetta():
    """On Apple Silicon, install Rosetta 2 if it is missing (asking first when run interactively)."""
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        return
    if _bgmn_has_arm64() or _rosetta_installed():
        return
    manual = f"Install it with:\n  sudo {' '.join(INSTALL_CMD)}"
    print("dara's refinement engine (BGMN) is Intel-only and needs Rosetta 2 on Apple Silicon, which isn't installed.")
    if not sys.stdin.isatty():
        raise RuntimeError(f"Rosetta 2 is required. {manual}")
    if input("Install Rosetta 2 now (accepts Apple's Rosetta license)? [Y/n] ").strip().lower() not in ("", "y", "yes"):
        raise RuntimeError(f"Rosetta 2 is required. {manual}")
    if subprocess.run(INSTALL_CMD).returncode != 0 or not _rosetta_installed():
        raise RuntimeError(f"Rosetta 2 install failed. {manual}")
    print("Rosetta 2 installed.\n")
