"""Publication-style refinement plots from a saved .pkl."""

import re
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
import plotly.graph_objects as go

COLORS = [
    "#1f77b4",
    "#aec7e8",
    "#ff7f0e",
    "#2ca02c",
    "#98df8a",
    "#d62728",
    "#9467bd",
    "#c5b0d5",
    "#8c564b",
    "#e377c2",
    "#f7b6d2",
    "#7f7f7f",
    "#bcbd22",
    "#dbdb8d",
    "#17becf",
    "#9edae5",
]
WIDTH, HEIGHT, SCALE = 1200, 600, 5
MARGIN = dict(l=150, r=20, t=20, b=100)
PLOT_W = WIDTH - MARGIN["l"] - MARGIN["r"]
PLOT_H = HEIGHT - MARGIN["t"] - MARGIN["b"]
FONT, SMALL = 30, 20
LINE_PX = 30
PAD_PX = 10


def _formula(text):
    return re.sub(r"(?<=[A-Za-z)\]])(\d+(?:\.\d+)?)", r"<sub>\1</sub>", text)


def phase_labels(names):
    """MgGeO3_61_icsd_035533 -> MgGeO<sub>3</sub>."""
    parts = [n.split("_", 2) + [""] * (3 - len(n.split("_", 2))) for n in names]
    by_formula = Counter(p[0] for p in parts)
    by_sg = Counter((p[0], p[1]) for p in parts)
    labels = []
    for formula, sg, rest in parts:
        custom = rest[len("custom_") :].replace("_", " ") if rest.startswith("custom_") else ""
        label = _formula(formula)
        if by_formula[formula] > 1:
            extra = [f"SG {sg}"] + ([rest.replace("_", " ")] if by_sg[(formula, sg)] > 1 and not custom else [])
            label += ", " + ", ".join(e for e in extra if e.strip())
        if custom:
            label += f" ({custom})"
        labels.append(label)
    return labels


def _text_px(label, size):
    subs = "".join(re.findall(r"<sub>(.*?)</sub>", label))
    plain = re.sub(r"<sub>.*?</sub>|<[^>]+>", "", label)
    return (len(plain) + 0.7 * len(subs)) * 0.52 * size


def _nice_step(span, target=5):
    raw = span / target
    mag = 10 ** np.floor(np.log10(raw))
    return mag * min((m for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), default=10)


def pretty_figure(result, xlim=None):
    d = result.plot_data
    x = np.asarray(d.x)
    obs, calc, bkg = np.asarray(d.y_obs), np.asarray(d.y_calc), np.asarray(d.y_bkg)
    x0, x1 = xlim if xlim else (np.round(x.min()), np.round(x.max()))
    shown = (x >= x0) & (x <= x1)
    if not shown.any():
        raise ValueError(f"no data between {x0} and {x1} degrees")
    top_curve = np.maximum(obs, calc)
    tallest = top_curve[shown].max()
    diff = obs - calc

    weights = result.get_phase_weights()
    names = list(d.structs)
    labels = phase_labels(names)
    if len(names) > 1:
        labels = [f"{lab} ({weights[n] * 100:.2f} %)" for lab, n in zip(labels, names, strict=True)]
    legend_entries = ["Observed", "Calculated", *labels]
    rwp_text = f"R<sub>wp</sub> = {result.lst_data.rwp:.2f}%"

    legend_w = 50 + max(_text_px(t, SMALL) for t in legend_entries)
    legend_h = LINE_PX * len(legend_entries) + PAD_PX
    rwp_w, rwp_h = _text_px(rwp_text, SMALL) + 20, LINE_PX
    label_w, label_h = _text_px("Difference", SMALL) + 20, LINE_PX

    def band_max(side, width_px, y=top_curve):
        frac = (width_px + 0.02 * PLOT_W) / PLOT_W
        lo, hi = (x0, x0 + frac * (x1 - x0)) if side == "left" else (x1 - frac * (x1 - x0), x1)
        sel = (x >= lo) & (x <= hi)
        return y[sel], sel

    span = tallest * 1.3
    for _ in range(10):
        per_px = span / PLOT_H
        pad = PAD_PX * per_px
        best = None
        for legend_side, rwp_side in (("right", "left"), ("left", "right")):
            need = [tallest]
            for side, w, h in ((legend_side, legend_w, legend_h), (rwp_side, rwp_w, rwp_h)):
                ys, _ = band_max(side, w)
                if ys.size:
                    need.append(ys.max() + h * per_px + pad)
            if best is None or max(need) < best[0]:
                best = (max(need), legend_side, rwp_side)
        box_top, legend_side, rwp_side = best
        ytop = box_top + 2 * pad
        shifted = diff - diff[shown].max() - 2 * pad
        ys, sel = band_max("right", label_w, shifted)
        label_y = (ys.min() if ys.size else shifted[shown].min()) - pad / 2
        ybottom = min(shifted[shown].min(), label_y - label_h * per_px) - pad
        new_span = ytop - ybottom
        if abs(new_span - span) < 1e-3 * span:
            break
        span = new_span

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x,
            y=obs,
            mode="markers",
            name="Observed",
            marker=dict(color="black", size=4, symbol="cross-thin-open"),
        )
    )
    fig.add_trace(go.Scatter(x=x, y=calc, mode="lines", name="Calculated", line=dict(color="RebeccaPurple", width=3)))
    fig.add_trace(
        go.Scatter(
            x=x,
            y=shifted,
            mode="lines",
            showlegend=False,
            opacity=0.7,
            line=dict(color="#808080", width=2),
        )
    )
    for i, (name, label) in enumerate(zip(names, labels, strict=True)):
        color = COLORS[i % len(COLORS)]
        fig.add_trace(go.Scatter(x=x, y=bkg, mode="lines", line=dict(color=color, width=0), showlegend=False))
        fig.add_trace(
            go.Scatter(
                x=x,
                y=np.asarray(d.structs[name]) + bkg,
                mode="lines",
                fill="tonexty",
                name=label,
                line=dict(color=color, width=1.5),
            )
        )

    def paper_y(y):
        return (y - ybottom) / (ytop - ybottom)

    def paper_x(side):
        return 0.01 if side == "left" else 0.99

    fig.add_annotation(
        text=rwp_text,
        xref="paper",
        yref="paper",
        x=paper_x(rwp_side),
        y=paper_y(box_top),
        xanchor=rwp_side,
        yanchor="top",
        showarrow=False,
        font=dict(size=SMALL),
    )
    fig.add_annotation(
        text="<i>Difference</i>",
        xref="paper",
        yref="paper",
        x=0.99,
        y=paper_y(label_y),
        xanchor="right",
        yanchor="top",
        showarrow=False,
        font=dict(color="grey", size=SMALL),
    )

    ystep = _nice_step(tallest)
    xstep = 10 if x1 - x0 > 40 else 5
    axis = dict(
        showline=True,
        linewidth=1,
        linecolor="black",
        mirror=True,
        ticks="outside",
        tickwidth=1,
        tickcolor="black",
        ticklen=10,
        showgrid=False,
        zeroline=False,
    )
    fig.update_layout(
        width=WIDTH,
        height=HEIGHT,
        margin=MARGIN,
        plot_bgcolor="white",
        paper_bgcolor="white",
        hovermode=False,
        font=dict(family="Arial, sans-serif", color="RebeccaPurple", size=FONT),
        xaxis=dict(axis, title="2θ (°)", range=[x0, x1], dtick=xstep),
        yaxis=dict(
            axis,
            title="Intensity (counts)",
            range=[ybottom, ytop],
            tickvals=np.arange(0, ytop, ystep),
            tickformat="d",
        ),
        legend=dict(
            font=dict(size=SMALL),
            bgcolor="rgba(0,0,0,0)",
            traceorder="normal",
            yanchor="top",
            y=paper_y(box_top),
            xanchor=legend_side,
            x=paper_x(legend_side),
        ),
    )
    return fig


def save_pretty(pkl: Path, out_dir: Path | None = None, xlim=None) -> list[Path]:
    """Write <pkl stem>_pretty.pdf and .png."""
    pkl = Path(pkl)
    result = joblib.load(pkl)
    fig = pretty_figure(result, xlim)
    out_dir = Path(out_dir) if out_dir else pkl.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [out_dir / f"{pkl.stem}_pretty.pdf", out_dir / f"{pkl.stem}_pretty.png"]
    fig.write_image(paths[0])
    fig.write_image(paths[1], scale=SCALE)
    return paths
