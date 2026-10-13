"""Structure-based CIF deduplication: collapses partial-occupancy variants of the same structure."""

import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


def _make_comparator(occ_tol):
    from pymatgen.analysis.structure_matcher import AbstractComparator

    class OccupancyAgnosticComparator(AbstractComparator):
        def __init__(self, occ_tol=None):
            self.occ_tol = occ_tol

        def are_equal(self, sp1, sp2):
            if {e.symbol for e in sp1.elements} != {e.symbol for e in sp2.elements}:
                return False
            if self.occ_tol is None:
                return True
            return all(abs(sp1.get(el, 0.0) - sp2.get(el, 0.0)) <= self.occ_tol for el in sp1.elements)

        def get_hash(self, composition):
            return frozenset(e.symbol for e in composition.elements)

    return OccupancyAgnosticComparator(occ_tol=occ_tol)


def _clean(struct, symprec):
    from pymatgen.core import Element, Structure
    from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

    struct = struct.copy()
    struct.remove_oxidation_states()
    species, coords = [], []
    for site in struct:
        occ = {}
        for sp, amt in site.species.items():
            try:
                occ[Element(sp.symbol)] = amt
            except Exception:
                occ[sp] = round(amt, 2)
        species.append(occ)
        coords.append(site.frac_coords)
    clean = Structure(struct.lattice, species, coords).get_reduced_structure()
    try:
        clean = SpacegroupAnalyzer(clean, symprec=symprec).get_refined_structure()
        clean = SpacegroupAnalyzer(clean, symprec=symprec).get_primitive_standard_structure()
    except Exception:
        pass
    return clean


def _spacegroup(struct, symprec):
    from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

    try:
        return SpacegroupAnalyzer(struct, symprec=symprec).get_space_group_number()
    except Exception:
        return -1


def _skeleton(struct, dummy_ids):
    from pymatgen.core import DummySpecies, Structure

    species = []
    for site in struct:
        tag = "|".join(sorted(sp.symbol for sp in site.species))
        dummy_ids.setdefault(tag, len(dummy_ids))
        species.append({DummySpecies(f"Q{dummy_ids[tag]}"): 1.0})
    return Structure(struct.lattice, species, [s.frac_coords for s in struct])


def _make_matcher(**kwargs):
    from pymatgen.analysis.structure_matcher import StructureMatcher

    class PrereducedMatcher(StructureMatcher):
        """Expects structures already reduced by `_reduce`. pymatgen's own reduction cache keys on the element
        set, so every same-system lookup falls back to an O(N^2) site-by-site equality check."""

        @classmethod
        def _get_reduced_structure(cls, struct, primitive_cell=True, niggli=True):
            return struct.copy()

    return PrereducedMatcher(**kwargs)


def _reduce(struct, primitive_cell=True):
    # Same reduction StructureMatcher applies before matching (niggli, then primitive cell).
    reduced = struct.get_reduced_structure(reduction_algo="niggli")
    return reduced.get_primitive_structure() if primitive_cell else reduced


def _distortion(struct, symprec=0.2):
    from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

    try:
        refined = SpacegroupAnalyzer(struct, symprec=symprec).get_refined_structure()
        matcher = _make_matcher(primitive_cell=False, scale=False)
        rms = matcher.get_rms_dist(_reduce(struct, primitive_cell=False), _reduce(refined, primitive_cell=False))
        return 999 if rms is None else rms[0]
    except Exception:
        return 999


def _occupancy_deficit(struct):
    return sum(max(0.0, 1.0 - sum(site.species.values())) for site in struct)


@dataclass
class UniquenessResult:
    kept: list = field(default_factory=list)
    discarded: list = field(default_factory=list)
    log: list = field(default_factory=list)

    def report(self):
        return "\n".join([f"Unique kept: {len(self.kept)}", f"Duplicates: {len(self.discarded)}", ""] + self.log)


def filter_unique(
    cif_paths, ltol=0.05, stol=0.15, angle_tol=2, symprec=0.01, occ_tol: float | None = None, prefer=lambda p: 0,
    max_sites=1000,
) -> UniquenessResult:
    from pymatgen.core import Structure

    matcher = _make_matcher(
        ltol=ltol, stol=stol, angle_tol=angle_tol, primitive_cell=True, scale=True, comparator=_make_comparator(occ_tol)
    )
    result = UniquenessResult()
    dummy_ids = {}
    groups = defaultdict(list)

    warnings.filterwarnings("ignore", module="pymatgen")
    for path in sorted(map(Path, cif_paths)):
        try:
            raw = Structure.from_file(str(path), primitive=False, sort=False)
            if max_sites is not None and len(raw) > max_sites:
                result.kept.append(path)
                result.log.append(f"[!] kept {path.name} ({len(raw)} sites, too large to compare)")
                continue
            clean = _clean(raw, symprec)
            key = (
                clean.composition.reduced_formula
                if occ_tol is not None
                else "-".join(sorted({sp.symbol for s in clean for sp in s.species}))
            )
            groups[key].append(
                {
                    "path": path,
                    "match": _reduce(clean if occ_tol is not None else _skeleton(clean, dummy_ids)),
                    "sg": _spacegroup(clean, symprec),
                    "rank": (prefer(path), _occupancy_deficit(clean), _distortion(raw, symprec), clean.volume),
                }
            )
        except Exception as exc:
            result.kept.append(path)
            result.log.append(f"[!] kept {path.name} (unreadable: {type(exc).__name__}: {exc})")

    for items in groups.values():
        items.sort(key=lambda it: it["rank"])
        reps = []
        for item in items:
            dup = next(
                (
                    r
                    for r in reps
                    if r["sg"] == item["sg"] and matcher.get_rms_dist(item["match"], r["match"]) is not None
                ),
                None,
            )
            if dup is None:
                reps.append(item)
                result.kept.append(item["path"])
                result.log.append(f"[+] {item['path'].name} (SG {item['sg']})")
            else:
                result.discarded.append(item["path"])
                result.log.append(f"[x] {item['path'].name} duplicates {dup['path'].name}")
    return result
