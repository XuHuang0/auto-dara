"""Chemical-system search over a local ICSD folder.

Every CIF is read once and indexed by chemical system; the index (.find_cif_index.json.gz) is cached
in the ICSD folder, or in ~/.cache/auto-dara if that folder is read-only.
"""

import gzip
import hashlib
import itertools
import json
import re
from collections import defaultdict
from fractions import Fraction
from functools import reduce
from math import gcd
from pathlib import Path

INDEX_FILENAME = ".find_cif_index.json.gz"
FORMULA_TAGS = ("_chemical_formula_sum", "_chemical_formula_structural")
SPACEGROUP_TAGS = ("_space_group_IT_number", "_symmetry_Int_Tables_number")
_TAG_RE = {
    t: re.compile(r"^\s*" + re.escape(t) + r"\s+(.+?)\s*$", re.MULTILINE) for t in FORMULA_TAGS + SPACEGROUP_TAGS
}
_ELEMENT_RE = re.compile(r"([A-Z][a-z]?)(\d*\.?\d*)")
_ICSD_ID_RE = re.compile(r"icsd_0*(\d+)", re.IGNORECASE)


def _read_record(path):
    text = path.read_text(errors="replace")

    def get(tag):
        m = _TAG_RE[tag].search(text)
        return m.group(1).strip().strip("'\"") if m else None

    formula = next(filter(None, map(get, FORMULA_TAGS)), None)
    sg = next(filter(None, map(get, SPACEGROUP_TAGS)), None)
    try:
        sg = int(float(sg)) if sg else None
    except ValueError:
        sg = None
    return formula, sg


def parse_formula(formula):
    counts = defaultdict(float)
    for el, n in _ELEMENT_RE.findall(formula or ""):
        counts[el] += float(n) if n else 1.0
    return dict(counts)


def reduce_to_integer_ratio(counts):
    if not counts:
        return {}
    fr = {el: Fraction(v).limit_denominator(10000) for el, v in counts.items()}
    denom = reduce(lambda a, b: a * b // gcd(a, b), (f.denominator for f in fr.values()))
    ints = {el: f.numerator * (denom // f.denominator) for el, f in fr.items()}
    g = reduce(gcd, ints.values())
    return {el: v // g for el, v in ints.items()} if g else ints


def format_reduced_formula(reduced):
    from pymatgen.core import Composition

    return Composition(reduced).reduced_formula.replace(" ", "")


def _cif_files(root):
    return [p for p in root.rglob("*.cif") if "found-cifs" not in p.parts]


def build_index(root, files):
    by_chemsys = defaultdict(list)
    for path in files:
        try:
            formula, sg = _read_record(path)
            reduced = reduce_to_integer_ratio(parse_formula(formula))
        except Exception:
            continue
        if not reduced:
            continue
        m = _ICSD_ID_RE.search(path.stem)
        by_chemsys["-".join(sorted(reduced))].append(
            {
                "path": str(path.relative_to(root)),
                "formula_sum": formula,
                "reduced": reduced,
                "sg": sg,
                "icsd_id": m.group(1).zfill(6) if m else path.stem,
            }
        )
    return {"file_count": len(files), "entries_by_chemsys": dict(by_chemsys)}


def _index_locations(root):
    cache = Path.home() / ".cache/auto-dara" / f"icsd_index_{hashlib.md5(str(root).encode()).hexdigest()[:10]}.json.gz"
    return [root / INDEX_FILENAME, cache]


def load_index(root):
    root = Path(root)
    files = _cif_files(root)
    for loc in _index_locations(root):
        if loc.exists():
            try:
                with gzip.open(loc, "rt") as f:
                    idx = json.load(f)
                if idx.get("file_count") == len(files):
                    return idx
            except Exception:
                pass
    print(f"  indexing {len(files)} ICSD CIFs (first time only, takes a few minutes)...")
    idx = build_index(root, files)
    for loc in _index_locations(root):
        try:
            loc.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(loc, "wt") as f:
                json.dump(idx, f)
            break
        except OSError:
            continue
    return idx


def entries_for_system(root, elements):
    idx = load_index(root)["entries_by_chemsys"]
    out = []
    for r in range(1, len(elements) + 1):
        for sub in itertools.combinations(sorted(elements), r):
            out += idx.get("-".join(sub), [])
    return out
