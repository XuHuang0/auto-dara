# auto-dara

Phase identification and Rietveld refinement of ex situ powder XRD patterns with
[dara](https://github.com/CederGroupHub/dara). You give it a pattern and the sample's chemistry; it finds
candidate structures, filters them, runs dara's phase search, ranks the solutions by figure of merit, and
saves everything.

## Install

Use **Python 3.10**. Newer Python versions often pull in package versions dara doesn't work with yet.

```bash
git clone https://github.com/lauren-walters/auto-dara.git
cd auto-dara
conda create -n auto-dara python=3.10 -y
conda activate auto-dara
pip install -e .
auto-dara --help
```

`pyproject.toml` pins `numpy<2` and `scipy<1.18`. With newer versions dara's peak matcher crashes.

## Configure

Settings live in a `.env` file (copy `.env.example`) in this folder (or in the folder you run `auto-dara` from):

```bash
GEMINI_API_KEY=your-key-here
ICSD_PATH=/path/to/ICSD_2024/ICSD_2024_experimental_inorganic
AUTO_DARA_RESULTS=/path/to/where/results/go
```

All three are optional:

| setting | what it does | if missing |
| --- | --- | --- |
| `GEMINI_API_KEY` | LLM chemical feasibility filter | filter skipped (or pass `--no-llm`), everything else runs |
| `ICSD_PATH` | your local ICSD: a folder of `.cif` files, any layout | COD only |
| `AUTO_DARA_RESULTS` | default output folder | `./results` in whatever folder you run from |

You can also set these per run: `--icsd PATH` for the ICSD and `-o FOLDER` for the output. Exported shell
variables work too and take precedence over `.env`.

The first search against a new ICSD folder indexes every CIF by chemical system, which takes a few minutes.
After that, lookups take about a second. The index is saved in the ICSD folder as `.find_cif_index.json.gz`,
or in `~/.cache/auto-dara/` if that folder is read-only. Use only the experimental ICSD; theoretical structures
will get fitted to real samples.

COD needs no setup. Structures are downloaded once and cached in `~/.cache/auto-dara/cod`. If COD is down
the run carries on with ICSD only.

## Automatic search

```bash
auto-dara search scan.xrdml -p "La2O3, Fe2O3" -t LaFeO3 --temp "1100 C for 12 h" -o results
```

- Several patterns at once: list them, or give a folder. They share one candidate pool, so they should be
  the same chemical system.
- `-p` precursors or `-s` chemical system (`-s La-Fe-O`); at least one is needed.
- `-e "C, H"` adds elements, e.g. for carbonates or hydroxides from air exposure.
- `-m` synthesis method, `--temp` temperature and time, `--atmosphere` (default air). The LLM filter uses these
  to judge which oxidation states can survive, so give them whenever you can. The default method is solid-state
  synthesis in a box furnace. `-m none` means no synthesis: you're measuring the precursors themselves.
- `-i` instrument profile. **This must match your diffractometer.** The default is
  `Aeris-fds-Pixcel1d-Medipix3`; `auto-dara instruments` lists the others.
- `--no-llm` skips the LLM filter. Use it if you have no Gemini API key; everything else works the same.
- `--skip-filter` reruns only the phase search, on the scan's existing `cifs_considered/` folder. Drop your own
  CIFs into that folder (or delete some), then rerun with the same `-o`. Precursors and other settings are
  remembered from the first run.

Run time grows with the number of candidates: about 30 take 15 seconds to a few minutes, hundreds (large
chemical systems, or `--no-llm`) much longer. If a small search is unexpectedly slow, check the instrument
profile. `auto-dara candidates ...` builds and filters the candidate pool without searching.

New to this? Work through `tutorial/README.md` first.

## Manual refinement

Refine a pattern with exactly the phases you choose. With no phases, auto-dara starts from the scan's
`cifs_best/`, the structures of the best search solution:

```bash
auto-dara manual scan.xrdml -o results                              # the best solution's phases
auto-dara manual scan.xrdml --add Sr2Nb2O7_36 -o results          # best solution plus another phase
auto-dara manual scan.xrdml LaFeO3_62 Fe2O3_167 -o results         # exactly these phases
```

Phases can be paths to `.cif` files, or names of CIFs from a previous search in the same `-o` folder. A partial
name is fine as long as it matches one file. Each manual refinement saves `<scan>_manual.*` and replaces the
previous one; its FOM is printed and added to `results.csv`. Settings (instrument, precursors) carry over from
the earlier search in that folder.

## Refinement parameters

`auto-dara params` prints the defaults with explanations:

| parameter | search | manual | what it controls |
| --- | --- | --- | --- |
| `lattice_range` | `0.01` | `0.03` | how far lattice parameters may move from the CIF (fraction) |
| `k1` | `0_0^0.01` | `0_0^0.005` | strain-related peak broadening |
| `k2` | `fixed` | `0_0^0.0001` | strain-related peak broadening |
| `b1` | `0_0^0.005` | `0_0^0.005` | crystallite-size broadening |
| `gewicht` | `0_0` | `SPHAR0` | preferred orientation (`0_0`/`SPHAR0` none; `SPHAR2`, `SPHAR4` more freedom) |
| `rp` | `4` | `4` | BGMN peak-shape function |
| `eps1` | `0` | `0` | zero-point shift |
| `eps2` | `0_-0.05^0.05` | `0_-0.1^0.1` | sample displacement |

The search keeps dara's own defaults: its test for accepting a phase is tuned for them, and looser values let
the main phase absorb minor ones. Manual refinement uses slightly looser values for a better final fit.

Ranges are BGMN syntax, `start_min^max`; `fixed` holds a parameter at zero. Change them with `-P` (phase
parameters) and `-R` (`eps1`, `eps2`) on `search` or `manual`; they change whichever set that command uses:

```bash
auto-dara manual scan.xrdml LaFeO3_62 Fe2O3_167 -o results -P k1=0_0^0.01 -P k2=fixed
auto-dara manual scan.xrdml LaFeO3_62 Fe2O3_167 -o results -P Fe2O3_167:lattice_range=0.05 -R eps2=0_-0.05^0.05
```

A phase prefix (`Fe2O3_167:`) changes that phase only, in manual refinement. Loosen with care: wide ranges let
a wrong phase stretch and broaden until it fits anything.

## Instrument profiles

`-i` sets the instrument profile, which must match your diffractometer: a wrong one gives worse fits and much
slower searches. The default is `Aeris-fds-Pixcel1d-Medipix3`. `.xrdml` files name their instrument in the header,
and auto-dara warns when an Aeris scan is refined with another profile.

These are dara's built-in profiles (`auto-dara instruments` lists them). Each name gives the instrument model and
its optics (`fds` fixed divergence slit, `ads` automatic divergence slit, then the slit size and detector). Pick
the one matching your machine's model and slit setup; if you're unsure, ask whoever runs the instrument.

| instrument | profiles |
| --- | --- |
| PANalytical Aeris | `Aeris-fds-Pixcel1d-Medipix3` |
| PANalytical X'Pert / Empyrean | `xpert-pixcel-0500`, `xpert-xcel-ads-10mm`, `xpert-xcel-ads-10mm-Ge`, `xpert-xcel-fds-0125`, `xpert-xcel-fds-0250`, `xpert-xcel-fds-1000`, `xpert-xcel-htk-ads-10`, `xpert-xcel-htk-fds-0125`, `PW3040-FDS-ADS-Xcelerator` |
| PANalytical Cubix | `cubix-ads-10mm`, `cubix-ads-15mm` |
| Philips PW1800 | `pw1800-ads-10mm`, `pw1800-fds` |
| Bruker D8 | `d8-fds-02-LynxEyeXE`, `d8-lynxeye-ads-1mm`, `d8-lynxeye-fds-02`, `d8-lynxeye-fds-05mm`, `d8-lynxeye-fds-06mm`, `d8-solxe-fds-0600`, `d8-solxe-vds-12mm`, `D8_6Div_4SS`, `LBL-d8-LynxEyeXE`, `RMS-D8-ADS-15-Glass-LynxEyeXE`, `RMS-D8-ADS-15-LynxEyeXE`, `RMS-D8-Capillary-500um-LynxEyeXE`, `RMS-D8-FDS-03-LynxEyeXE` |
| Bruker D2 | `d2-ssd160-fds-1` |
| Bruker X8 Apex2 | `x8-apex2-fds-10` |
| Siemens D5000 | `siemens-d5000-fds1mm`, `siemens-d5000-fds1mm-2`, `siemens-d5000-fds2mm` |
| Rigaku MiniFlex | `Rigaku-Miniflex`, `Rigaku-Miniflex-600-DTEXultra2-fds`, `Rigaku-Miniflex-gen5-Dtex-var`, `Rigaku-Miniflex-gen5-Dtex-varfix` |
| Rigaku SmartLab / Ultima | `Rigaku-SmartLab-CBO-BB-FDS05deg`, `rigaku-ultima` |
| Anton Paar XRDynamic 500 | `ucb-xrdynamic500-anton-paar` |
| Synchrotron | `synchrotron` |

## Batch runs

To run many patterns in one go, list them in a CSV (or JSON) file, one row per job:

```bash
auto-dara jobs.csv              # same as: auto-dara batch jobs.csv
```

| column | meaning |
| --- | --- |
| `pattern` | path to the scan, relative to the job file (required) |
| `output` | results folder for this row (default: `-o`, `AUTO_DARA_RESULTS`, or `./results`) |
| `precursors`, `system`, `extra_elements`, `target`, `method`, `temperature`, `atmosphere` | as on the command line |
| `phase_params`, `refinement_params` | same as `-P` / `-R`, space-separated, e.g. `k1=0_0^0.01 ZnO_186:k2=fixed` |
| `skip_filter`, `use_llm` | `true` / `false`, same as `--skip-filter` / `--no-llm` |
| `instrument`, `wavelength`, `max_phases`, `max_e_hull`, ... | any other setting, by its name in `auto_dara/config.py` |
| `phases` | fill this in to make the row a manual refinement: CIF names or paths (space-separated), or `best` for `cifs_best/` |
| `add` | phases to add on top, like `--add` |

Empty cells use the defaults. Searches run first, then manual refinements, so a manual row can use CIFs from a
search row in the same file. Search rows with identical settings and output folder share one candidate pool.
Jobs run one after another (each search already uses every CPU core). A failed job is reported and the rest
carry on. See `tutorial/tutorial4.csv` for an example.

## Where your results are

Everything goes in the output folder (`-o`, else `AUTO_DARA_RESULTS`, else `./results` in the folder you ran
from). Each scan gets its own self-contained folder, named after the scan file:

```
results/
  summary.csv                   every solution for every scan in this folder, one row each
  <scan>/
    <scan>_rank0.html           best solution (highest FOM): interactive plot, open in a browser
    <scan>_rank0.png            the same plot as an image
    <scan>_rank0.pkl            the full dara refinement result, for Python
    <scan>_rank1.*, _rank2.*    next-best solutions, if dara found any
    <scan>_manual.*             your latest manual refinement, same three files
    cifs_best/                  the structures in the best solution: start manual refinement here
    cifs_considered/            every structure that went into the phase search
    filter_report.md            what each filter removed and why, including the LLM's reasons
    results.csv                 this scan's solutions: FOM, Rwp, phases and weight fractions
    settings.json               exactly what was run
```

To work with a result in Python:

```python
import joblib
result = joblib.load("results/<scan>/<scan>_rank0.pkl")
result.get_phase_weights()        # {"LaFeO3_62_icsd_...": 1.0}
result.lst_data.rwp               # Rwp
result.visualize().show()         # the plot
```

`rank0` has the highest FOM; like dara, solutions are numbered from 0. **Judge solutions by FOM, not Rwp.** On a
high background, Rwp mostly measures the background fit. FOM multiplies six 0–1 scores (fit quality, missing
peaks, extra peaks, intensity mismatch, element presence, lattice drift), so a single bad score drags the whole
solution down. Element presence is 0 unless every non-C/H/N/O precursor element appears in some phase above
1 wt%.

## Filters, in order

1. Every entry in the chemical system and all its subsystems (La-Fe-O also searches La-O, Fe-O, La, Fe, ...):
   your whole local ICSD plus COD (dara's curated index).
2. Drop gases, phases made only of C/H/O, and hydrides (H without O).
3. Drop phases above `--max-ehull` (default 0.1 eV/atom), where dara knows an E_hull from the Materials
   Project. Phases with no known E_hull are kept.
4. Keep one entry per formula and space group (ICSD before COD).
5. Structural uniqueness: collapse partial-occupancy variants of the same structure.
6. LLM chemical feasibility (Gemini) given the precursors, target, synthesis method, temperature and
   atmosphere. It is told to keep a phase when unsure, since a dropped phase can never be found. `--no-llm`
   skips it.

Your own CIFs (`--cifs DIR`) skip steps 1–4. `--skip-filter` skips all of them and reuses `cifs_considered/`.

## If nothing fits

1. Open the pattern and check that it's the sample you think it is.
2. Add elements with `-e`; the phase present may not be reachable from the precursors.
3. Check `filter_report.md` for something plausible that was removed. Put its CIF into `cifs_considered/` and
   rerun with `--skip-filter`, or try it with `manual`.

## Citing

auto-dara runs on [dara](https://github.com/CederGroupHub/dara), which drives the
[BGMN](http://www.bgmn.de) Rietveld program. If you use auto-dara in published work, please cite both:

```bibtex
@article{Fei2026,
  title     = {Dara: Automated Multiple-Hypothesis Phase Identification and Refinement from Powder X-ray Diffraction},
  author    = {Fei, Yuxing and McDermott, Matthew J. and Rom, Christopher L. and Wang, Shilong and Ceder, Gerbrand},
  journal   = {Chemistry of Materials},
  volume    = {38},
  number    = {3},
  pages     = {1364--1376},
  year      = {2026},
  month     = jan,
  publisher = {American Chemical Society (ACS)},
  issn      = {1520-5002},
  doi       = {10.1021/acs.chemmater.5c02820},
  url       = {http://dx.doi.org/10.1021/acs.chemmater.5c02820}
}

@article{BGMN,
  title     = {Handling of Unusual Instrumental Profiles by the BGMN Rietveld Program},
  author    = {Bergmann, J. and Friedel, P. and Kleeberg, R.},
  journal   = {Mater. Sci. Forum},
  volume    = {321--324},
  pages     = {192--197},
  year      = {2000},
  publisher = {Trans Tech Publications, Ltd.},
  issn      = {1662-9752},
  doi       = {10.4028/www.scientific.net/msf.321-324.192}
}
```

## License

MIT, see `LICENSE`.
