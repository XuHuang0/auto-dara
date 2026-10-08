"""Figure of merit: six 0-1 sub-scores multiplied together, so one bad score sinks a solution."""

import warnings
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np


def total_peaks(pattern, s):
    try:
        from .peaks import warm

        return len(warm(pattern, s))
    except Exception as exc:
        print(f"  warning: peak detection failed ({exc})")
        return None


def _gof(rwp, rexp, cutoff):
    gof = rwp / rexp if rexp else float("inf")
    return float(np.clip(1 - (gof - 1) / (cutoff - 1), 0, 1))


def _fraction(arr, total):
    n = 0 if arr is None else len(np.asarray(arr).reshape(-1, 2))
    return float(np.clip((total - n) / total, 0, 1)) if total else 0.0


def _element_presence(weights, required, threshold):
    from pymatgen.core import Composition

    present = set()
    for name, w in weights.items():
        if w > threshold:
            try:
                present.update(e.symbol for e in Composition(name.split("_")[0]).elements)
            except Exception:
                pass
    return 1.0 if set(required) <= present else 0.0


def _lattice_drift(phase_result, cif):
    from dara.utils import load_symmetrized_structure

    init, init_spg = load_symmetrized_structure(Path(cif))
    with NamedTemporaryFile(suffix=".cif", delete=False) as tmp:
        refined_cif = Path(tmp.name)
    try:
        phase_result.get_structure().to(filename=str(refined_cif))
        ref, ref_spg = load_symmetrized_structure(refined_cif)
    finally:
        refined_cif.unlink(missing_ok=True)
    drifts = [(ref.lattice.volume - init.lattice.volume) / init.lattice.volume]
    if init_spg.get_space_group_number() == ref_spg.get_space_group_number():
        drifts += [(getattr(ref.lattice, a) - getattr(init.lattice, a)) / getattr(init.lattice, a) for a in "abc"]
    return max(abs(d) for d in drifts)


def _lattice(result, cifs, catastrophe):
    drifts = []
    for name, pr in result.lst_data.phases_results.items():
        if name in cifs:
            try:
                drifts.append(_lattice_drift(pr, cifs[name]))
            except Exception:
                pass
    return 1.0 if not drifts or max(drifts) < catastrophe else 0.0


def score(result, cifs: dict, required, n_peaks, s) -> dict:
    """Returns {'fom': float|None, sub-score: value, ...}. Never raises."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ld = result.lst_data
            m = getattr(result, "refinement_metrics", None)
            parts = {
                "gof": _gof(ld.rwp, ld.rexp, s.fom_gof_cutoff),
                "missing_peaks": _fraction(m.missing_peaks if m else None, n_peaks),
                "extra_peaks": _fraction(m.extra_peaks if m else None, n_peaks),
                "intensity_mismatch": _fraction(m.intensity_mismatch_peaks if m else None, n_peaks),
                "element_presence": _element_presence(
                    result.get_phase_weights(normalize=True), required, s.fom_weight_threshold
                ),
                "lattice": _lattice(result, cifs, s.fom_lattice_catastrophe),
            }
        parts["fom"] = float(np.prod(list(parts.values()))) if n_peaks else None
        return parts
    except Exception as exc:
        print(f"  warning: FOM failed ({type(exc).__name__}: {exc})")
        return {"fom": None}
