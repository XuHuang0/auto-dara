# auto-dara tutorial

Five short exercises. Steps 1–4 each write to their own folder in `results/`, so you
can compare your output with what's described here. Run everything from this `tutorial/` folder with the
`auto-dara` environment active (see the main README for setup):

```bash
conda activate auto-dara
cd tutorial
```

| step | scan | precursors | target |
| --- | --- | --- | --- |
| 1 | `data/tutorial1_La-Fe-O.xrdml` | La2O3, Fe2O3, 1100 °C in air | LaFeO3 |
| 2 | `data/tutorial2_Zn-Al-O_a.xrdml`, `_b.xrdml` | ZnO, Al2O3 | ZnAl2O4 |
| 3 | `data/tutorial3_Sr-Nb-O.xrdml` | SrCO3, Nb2O5, 1025 °C in air | Sr2Nb2O7 |
| 4 | all of the above, from one file | | |
| 5 | choosing an instrument profile | | |

All scans were taken on a PANalytical Aeris, which is auto-dara's default instrument. Without a Gemini API key,
add `--no-llm` to the search commands; everything else works the same.

## 1. One pattern

```bash
auto-dara search data/tutorial1_La-Fe-O.xrdml -p "La2O3, Fe2O3" -t LaFeO3 --temp "1100 C for 12 h" -o results/step1
```

auto-dara will:

1. Find every structure in La-Fe-O and its subsystems (La-O, Fe-O, La, Fe, ...) in the ICSD and COD.
2. Filter them: drop gases and high-energy polymorphs, collapse duplicates, then ask the LLM which phases can
   exist after heating La2O3 and Fe2O3 in air at 1100 °C. About 700 entries become about 30.
3. Find the observed peaks in the scan, then run dara's phase search. This takes under a minute here. Run time
   grows with the number of candidates, so bigger systems or `--no-llm` take longer.
4. Score each solution with a figure of merit (FOM) and save them, best first.

The answer is LaFeO3 (orthorhombic, space group 62): FOM 0.91, Rwp 2.3.

## Where your results are

Everything goes in the folder you gave with `-o`. Without `-o`, results go to `./results` in the folder you ran
from (or wherever `AUTO_DARA_RESULTS` in your `.env` points).

```
results/step1/
  summary.csv                               every solution for every scan in this folder
  tutorial1_La-Fe-O/                        one folder per scan, named after the scan file
    tutorial1_La-Fe-O_rank0.html            <- start here: the best solution, open it in a browser
    tutorial1_La-Fe-O_rank0.png             the same plot as an image
    tutorial1_La-Fe-O_rank0.pkl             the full refinement result, for Python
    cifs_best/                              the structures in the best solution
    cifs_considered/                        every structure the search tried
    filter_report.md                        what each filter removed and why
    results.csv                             FOM, Rwp, phases and weight fractions
    settings.json                           exactly what you asked for
```

Solutions are numbered from 0, like dara's cases: `rank0` is the best by FOM. When dara finds other plausible
answers you also get `rank1`, `rank2`. Here it found one.

- **`tutorial1_La-Fe-O_rank0.html`**: observed pattern, fit, difference curve and each phase's contribution.
  Markers flag peaks the fit misses or invents.
- **`filter_report.md`**: everything removed before the search. The LLM section gives a reason for each formula:
  wüstite, magnetite and Fe metal can't survive 1100 °C in air.
- **`summary.csv`**: open in Excel. One row per solution, with the FOM sub-scores.

To use a result in Python:

```python
import joblib
r = joblib.load("results/step1/tutorial1_La-Fe-O/tutorial1_La-Fe-O_rank0.pkl")
r.get_phase_weights()     # weight fraction of each phase
r.lst_data.rwp            # Rwp
r.visualize().show()      # the interactive plot
```

## 2. Several patterns

Two scans of the same chemistry. List both and they share one candidate pool:

```bash
auto-dara search data/tutorial2_Zn-Al-O_a.xrdml data/tutorial2_Zn-Al-O_b.xrdml -p "ZnO, Al2O3" -t ZnAl2O4 -o results/step2
```

(A folder name works too: every scan in it is searched.) Each scan gets its own folder in `results/step2/`, and
`results/step2/summary.csv` lists both:

| scan | phases | FOM | Rwp |
| --- | --- | --- | --- |
| `_a` | 92% ZnAl2O4 spinel, 8% ZnO | 0.76 | 10.7 |
| `_b` | 90% ZnAl2O4 spinel, 10% ZnO | 0.47 | 18.0 |

The unreacted ZnO is real in both. Scan `_b` scores lower because its fit is worse, not because the answer is
different; open both HTML plots and compare the difference curves.

## 3. Manual refinement

The search gives you a starting point. Manual refinement lets you test it. First search this scan:

```bash
auto-dara search data/tutorial3_Sr-Nb-O.xrdml -p "SrCO3, Nb2O5" -t Sr2Nb2O7 --temp "1025 C" -o results/step3
```

The answer is unreacted SrCO3 and Nb2O5 (about 50/50), FOM 0.56, Rwp 6.9. The target, Sr2Nb2O7, is not in it.

**Refine the best solution.** With no phases, `manual` uses the scan's `cifs_best/`:

```bash
auto-dara manual data/tutorial3_Sr-Nb-O.xrdml -o results/step3
```

Same two phases, better fit: FOM 0.68, Rwp 5.0. Manual refinement allows the lattice and peak widths a little
more freedom than the search does (see `auto-dara params`), so it usually tightens the search's answer.

**Is the target really absent?** Add it and see if the fit improves:

```bash
auto-dara manual data/tutorial3_Sr-Nb-O.xrdml --add Sr2Nb2O7_36 -o results/step3
```

Sr2Nb2O7 refines to 0.9 wt% and the FOM doesn't move (0.68). A phase that is really present takes real weight
and improves the fit. This one does neither, so the reaction didn't happen. `Sr2Nb2O7_36` is the start of a file
name in `cifs_considered/`; if a name matches several files, auto-dara lists them so you can pick one.

**Change refinement parameters.** Maybe the target's lattice is strained? Give it more room:

```bash
auto-dara manual data/tutorial3_Sr-Nb-O.xrdml --add Sr2Nb2O7_36 -P Sr2Nb2O7_36:lattice_range=0.05 -o results/step3
```

Still 0.9 wt%, still FOM 0.68. `-P KEY=VALUE` sets a phase parameter, for every phase or, with a `PHASE:` prefix,
for one; `-R KEY=VALUE` sets whole-pattern ones (`eps1`, `eps2`). `auto-dara params` lists them all with their
defaults and meanings.

**Search again with your own structure.** `data/tutorial3_extra_SrNbO3.cif` is a structure from the
Crystallography Open Database that the filters wouldn't otherwise give you here. Put it in `cifs_considered/`
and rerun only the search:

```bash
cp data/tutorial3_extra_SrNbO3.cif results/step3/tutorial3_Sr-Nb-O/cifs_considered/
auto-dara search data/tutorial3_Sr-Nb-O.xrdml --skip-filter -o results/step3
```

`--skip-filter` reuses `cifs_considered/` as it is (auto-dara renames the new file to its standard
`formula_spacegroup_...` form) and remembers the precursors from the first search. The answer doesn't change:
SrNbO3 isn't in the sample either.

Each manual refinement saves `tutorial3_Sr-Nb-O_manual.*` and replaces the previous one, so finish with the
refinement you want to keep:

```bash
auto-dara manual data/tutorial3_Sr-Nb-O.xrdml -o results/step3
```

## 4. Many jobs from one file

Steps 1–3 as one job file, `tutorial4.csv`:

| pattern | output | precursors | target | method | temperature | atmosphere | phases |
| --- | --- | --- | --- | --- | --- | --- | --- |
| data/tutorial1_La-Fe-O.xrdml | results/step4 | La2O3, Fe2O3 | LaFeO3 | solid-state synthesis in a box furnace | 1100 C for 12 h | air | |
| data/tutorial2_Zn-Al-O_a.xrdml | results/step4 | ZnO, Al2O3 | ZnAl2O4 | solid-state synthesis in a box furnace | | air | |
| data/tutorial2_Zn-Al-O_b.xrdml | results/step4 | ZnO, Al2O3 | ZnAl2O4 | solid-state synthesis in a box furnace | | air | |
| data/tutorial3_Sr-Nb-O.xrdml | results/step4 | SrCO3, Nb2O5 | Sr2Nb2O7 | solid-state synthesis in a box furnace | 1025 C | air | |
| data/tutorial3_Sr-Nb-O.xrdml | results/step4 | | | | | | best |

```bash
auto-dara tutorial4.csv
```

- Rows without `phases` are searches. A row with `phases` is a manual refinement: `best` means `cifs_best/`, or
  list CIF names. Add an `add` column for `--add`.
- Searches run first, so manual rows can use their results.
- The two Zn-Al-O rows have identical settings, so they share one candidate pool.
- Paths are relative to the job file. Empty cells take the defaults. Any setting can be a column (`instrument`,
  `phase_params`, `use_llm`, ...; see the main README).
- At the end auto-dara prints every job, whether it worked, and its folder. `results/step4/` should match
  steps 1–3.

## 5. Instrument profiles

The instrument profile tells dara your diffractometer's peak shapes. **It must match the machine your scan came
from**: a wrong one gives worse fits and much slower searches. `.xrdml` files name their instrument in the
header, and auto-dara warns if an Aeris scan is refined with another profile. You can check a file yourself:

```bash
grep -o "Diffractometer system=[A-Z]*" data/tutorial1_La-Fe-O.xrdml      # -> Diffractometer system=AERIS
```

All the tutorial scans are from an Aeris, the default, so you never needed `-i`. For a different machine, list
the built-in profiles and pass the matching one with `-i`:

```bash
auto-dara instruments
auto-dara search my_scan.xrdml -p "..." -i d8-lynxeye-fds-05mm -o results/my_d8_scan
```

The main README groups the 40 profiles by instrument (Aeris, X'Pert/Empyrean, Bruker D8, Rigaku MiniFlex, ...)
and explains how to read their names. If none matches your machine and optics, ask whoever runs the instrument
which is closest.

## What to try next

- `auto-dara candidates -p "..." -o somewhere` builds the candidate pool without searching, to check
  `filter_report.md` first.
- `-m none` if you measured unreacted precursors: the LLM then keeps only the precursors and their impurities.
- `-e "C, H"` if the sample may contain carbonates or hydroxides from air.
- `--cifs my_cifs/` to add your own structures to a search from the start.
