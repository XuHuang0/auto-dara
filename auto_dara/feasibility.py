"""LLM chemical feasibility filter: drops candidate phases that cannot form under the synthesis conditions."""

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

LLM_PROMPT = """
ACT AS: Senior materials scientist identifying phases in a powder XRD pattern measured by {characterization_method}.

YOUR ROLE: Score candidate phases so that ones that cannot be in the sample can be dropped before Rietveld refinement.
Dropping a phase that is really present is much worse than keeping one that is absent: a dropped phase can never be
found. When unsure, score 0.5 or higher.

SAMPLE HISTORY:
{history}
PRECURSORS: {precursors}
TARGET: {target}

FOR EACH FORMULA, CONSIDER:
1. Redox: does the synthesis method, atmosphere and temperature support these oxidation states? (e.g. metals,
   suboxides and carbides do not survive firing in air; high oxidation states do not survive reducing conditions)
2. Role: could it be a precursor, the target, a decomposition product, an intermediate, a side product, or an
   unreacted remnant?
3. Measurement: the pattern was taken after cooling, so also consider phases formed on cooling or by air exposure
   (hydroxides, carbonates). Polymorphs stable only at high temperature are unlikely unless they quench.
Formulas with fractional subscripts come from partial-occupancy or defect refinements; judge them as the nearby
stoichiometric compound.

FORMAT: one table row per formula, copying each formula exactly as given: | Formula | Score | Reason |
Score from 0.0 (impossible under these conditions) to 1.0. Reason in 10 words or fewer.
"""

NO_SYNTHESIS = (
    "No synthesis was performed: the sample is the precursor(s) as received. Only the precursors, their "
    "polymorphs, and their common impurities or air-exposure products are plausible; reaction products "
    "are not.\n"
)


def _history(s):
    if s.method.strip().lower() in ("", "none", "no synthesis"):
        return NO_SYNTHESIS
    return f"Method: {s.method}\nAtmosphere: {s.atmosphere}\nTemperature/time: {s.temperature or 'unspecified'}\n"


def formula_from_cif_name(name):
    return Path(name).name.split("_")[0]


def nominal_formula(formula):
    from pymatgen.core import Composition

    try:
        amounts = Composition(formula).get_el_amt_dict()
    except Exception:
        return formula
    if all(float(v).is_integer() and v <= 20 for v in amounts.values()):
        return formula
    low = min(amounts.values())
    return "".join(
        el + ("" if round(v / low, 2) == 1 else f"{v / low:.2f}".rstrip("0").rstrip(".")) for el, v in amounts.items()
    )


def _parse(text):
    out = {}
    for line in text.split("\n"):
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) < 2 or parts[0].startswith("---") or parts[0].lower() == "formula":
            continue
        formula = parts[0].replace("*", "").replace("`", "").strip()
        try:
            score = min(1.0, max(0.0, float(parts[1])))
        except ValueError:
            continue
        out[formula] = (score, " ".join(parts[-1].split()[:10]) if len(parts) >= 3 else "")
    return out


@dataclass
class FeasibilityResult:
    kept: list = field(default_factory=list)
    discarded: list = field(default_factory=list)
    verdicts: dict = field(default_factory=dict)

    def report(self, s):
        lines = [
            "# Chemical feasibility",
            "",
            f"- Precursors: {s.precursors or s.chemsys()}",
            f"- Target: {s.target or 'unspecified'}",
            f"- Method: {s.method or 'none'}; {s.atmosphere}; {s.temperature or 'unspecified'}",
            f"- Kept {len(self.kept)}, discarded {len(self.discarded)}",
            "",
            "| Formula | Score | Status | Reason |",
            "| :--- | :--- | :--- | :--- |",
        ]
        for f, (score, status, reason) in sorted(self.verdicts.items(), key=lambda kv: kv[1][0]):
            lines.append(f"| {f} | {score} | {status} | {reason} |")
        return "\n".join(lines)


def filter_feasible(cif_paths, s, batch_size=20) -> FeasibilityResult:
    from google import genai

    logging.getLogger("google_genai").setLevel(logging.ERROR)
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("no GEMINI_API_KEY in the environment or a .env file")

    client = genai.Client(api_key=key)
    prompt = LLM_PROMPT.format(
        characterization_method=s.characterization,
        history=_history(s),
        precursors=s.precursors or f"unspecified; the sample contains {s.chemsys()}",
        target=s.target or "unspecified",
    )

    nominal = {p: nominal_formula(formula_from_cif_name(p)) for p in cif_paths}
    formulas = sorted(set(nominal.values()))
    cache = {}
    for i in range(0, len(formulas), batch_size):
        batch = formulas[i : i + batch_size]
        try:
            resp = client.models.generate_content(
                model=s.llm_model,
                contents=f"Assess these formulas: {batch}",
                config={"system_instruction": prompt, "temperature": 0},
            )
            parsed = _parse(resp.text or "")
            for f in batch:
                score, reason = parsed.get(f, (1.0, "missing from response; kept"))
                cache[f] = (score, "KEPT" if score >= s.llm_keep_threshold else "DISCARDED", reason)
        except Exception as exc:
            print(f"  LLM error ({type(exc).__name__}); keeping {len(batch)} formula(s)")
            for f in batch:
                cache[f] = (1.0, "KEPT", f"API error: {type(exc).__name__}")
        time.sleep(0.5)

    result = FeasibilityResult()
    for p in cif_paths:
        v = cache[nominal[p]]
        raw = formula_from_cif_name(p)
        result.verdicts[raw if raw == nominal[p] else f"{raw} (~{nominal[p]})"] = v
        (result.kept if v[1] == "KEPT" else result.discarded).append(p)
    return result
