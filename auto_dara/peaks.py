"""Disk cache for dara's observed-peak detection, which it otherwise repeats after every refinement."""

import hashlib
import os
from pathlib import Path

CACHE = Path(os.environ.get("AUTO_DARA_PEAK_CACHE") or Path.home() / ".cache/auto-dara/peaks")


def install():
    import dara.peak_detection as pd_mod
    import pandas as pd

    if getattr(pd_mod.detect_peaks, "_cached", False):
        return
    original = pd_mod.detect_peaks

    def detect_peaks(pattern, wavelength="Cu", instrument_profile="Aeris-fds-Pixcel1d-Medipix3", **kw):
        if not isinstance(pattern, (str, Path)):
            return original(pattern, wavelength=wavelength, instrument_profile=instrument_profile, **kw)
        profile = Path(str(instrument_profile))
        extra = profile.read_bytes() if profile.is_file() else b""
        key = hashlib.sha1(
            Path(pattern).read_bytes()
            + extra
            + repr(
                (wavelength, str(instrument_profile), sorted((k, v) for k, v in kw.items() if k != "show_progress"))
            ).encode()
        ).hexdigest()
        path = CACHE / f"{key}.pkl"
        if path.exists():
            try:
                return pd.read_pickle(path)
            except Exception:
                pass
        df = original(pattern, wavelength=wavelength, instrument_profile=instrument_profile, **kw)
        CACHE.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        df.to_pickle(tmp)
        tmp.replace(path)
        return df

    detect_peaks._cached = True
    pd_mod.detect_peaks = detect_peaks


def warm(pattern, s):
    import tempfile

    from dara.xrd import convert_pattern_to_xy

    install()
    import dara.peak_detection as pd_mod

    with tempfile.TemporaryDirectory() as tmp:
        xy = Path(pattern) if Path(pattern).suffix.lower() == ".xy" else convert_pattern_to_xy(Path(pattern), Path(tmp))
        return pd_mod.detect_peaks(str(xy), wavelength=s.wavelength, instrument_profile=s.instrument)
