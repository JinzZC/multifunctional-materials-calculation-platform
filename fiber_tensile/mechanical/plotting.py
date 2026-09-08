"""Lazy matplotlib figures shared by the UI and reports."""

from .core import MODES, SOURCES


def build_figure(entries):
    import numpy as np
    from matplotlib.figure import Figure
    from ..config import apply_matplotlib_chinese

    apply_matplotlib_chinese()
    shown = entries[:20]
    modes = list(dict.fromkeys(e["spec"].mode for e in shown))
    fig = Figure(figsize=(8, max(4.5, len(modes) * 3.5)), constrained_layout=True)
    for row, mode in enumerate(modes):
        ax = fig.add_subplot(len(modes), 1, row + 1)
        subset = [e for e in shown if e["spec"].mode == mode]
        for entry in subset:
            result = entry["result"]
            indices = np.unique(np.r_[np.linspace(0, len(result.strain) - 1,
                                                   min(5000, len(result.strain)), dtype=int),
                                      result.peak_index])
            strain = np.asarray(result.strain) * 100
            label = f"{entry['name']} · {SOURCES[entry['spec'].source]}"
            line, = ax.plot(strain[indices], np.asarray(result.stress_mpa)[indices], label=label, lw=1.4)
            if len(subset) == 1:
                selected = result.fit_indices
                fit_x = np.array([result.strain[selected[0]], result.strain[selected[-1]]])
                ax.plot(fit_x * 100, result.slope_mpa * fit_x + result.intercept_mpa,
                        "--", color="#B65B20", label=f"拟合 E={result.modulus_gpa:.4g} GPa")
                ax.axvspan(fit_x[0] * 100, fit_x[1] * 100, alpha=.1, color=line.get_color())
                ax.scatter([strain[result.peak_index]], [result.strength_mpa], s=28, zorder=4, label="首次峰值")
                if result.fracture_strain_pct is not None:
                    ax.scatter([result.fracture_strain_pct], [result.fracture_stress_mpa],
                               marker="x", s=45, color="#AA3030", zorder=5, label="人工确认断裂点")
        ax.set(title=MODES[mode], xlabel="工程应变 / %", ylabel="工程应力 / MPa")
        ax.grid(alpha=.2)
        ax.legend(fontsize=8)
    if not modes:
        fig.add_subplot(111).set_title("请选择曲线")
    return fig
