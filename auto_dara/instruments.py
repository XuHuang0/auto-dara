"""dara's built-in instrument profiles."""

from pathlib import Path


def list_profiles():
    import dara

    return sorted(p.stem for p in (Path(dara.__file__).parent / "data/BGMN-Templates/Devices").glob("*.geq"))
