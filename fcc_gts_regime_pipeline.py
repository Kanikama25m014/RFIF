"""
FCC-Guided GTS Regime-Switching Pipeline
This script implements a simplified version of the FCC-guided regime-switching pipeline using NIFTY 50 data.
NOTE: The GTS fitting here is a basic MLE approach for demonstration. For better accuracy, implement the RFIF method as per the paper.
Pipeline overview:
  1. Compute rolling FCC on NIFTY 50 log returns
  2. Segment the time series by FCC regime (high / mid / low)
  3. Fit a Generalised Tempered Stable (GTS) distribution to each regime
  4. Forecast next-period regime using FCC trend, apply corresponding GTS model
  5. Generate all presentation-ready plots
Reference: Manousopoulos & Drakopoulos (2025); Rachev et al. (GTS distributions)

"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import seaborn as sns
from scipy.stats import kurtosis, norm
from scipy.optimize import minimize
import yfinance as yf
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

# ============================================================================
# 1. Configuration
# ============================================================================
START_DATE  = "2014-01-01"
END_DATE    = "2024-01-01"
TICKER      = "^NSEI"
ROLLING_WIN = 252          # 1 trading year

# FCC regime thresholds - will be auto-suggested from data
# You can also set manually after seeing the percentiles
FCC_HIGH    = None          # will be set to 66th percentile
FCC_LOW     = None          # will be set to 33rd percentile

RESULTS_DIR = Path("results_p11")
RESULTS_DIR.mkdir(exist_ok=True)

# Plot styling
sns.set_style("whitegrid")
plt.rcParams.update({
    "figure.figsize": (10, 5),
    "font.size":       15,
    "axes.titlesize":  14,
    "axes.labelsize":  12,
    "savefig.dpi":     300,
    "savefig.bbox":   "tight",
})

# Colour palette
C_CALM      = "#2c7bb6"
C_TRANSIT   = "#fdae61"
C_TURB      = "#d7191c"

# ============================================================================
# 2. FCC helper
# ============================================================================
def compute_fcc(series: np.ndarray, num_segments: int = 10) -> float:
    segments = np.array_split(series, num_segments)
    global_rng = np.max(series) - np.min(series)
    if global_rng == 0:
        return 1.0
    s_vals = [abs(np.max(seg) - np.min(seg)) / global_rng
              for seg in segments if len(seg) > 1]
    if not s_vals:
        return 1.0
    s_vals = np.array(s_vals)
    return float(np.clip(1 + np.log(np.sum(s_vals)) / np.log(len(s_vals)), 1.0, 2.0))

def regime_label(fcc_value: float, low_thresh, high_thresh) -> str:
    if fcc_value >= high_thresh:
        return "turbulent"
    elif fcc_value <= low_thresh:
        return "calm"
    return "transitional"

# ============================================================================
# 3. Simplified GTS fitting (replace with your RFIF method later)
# ============================================================================
def gts_log_pdf(x, alpha, C, lam_pos, lam_neg):
    sigma = np.std(x)
    if sigma == 0:
        sigma = 1e-8
    mu = np.mean(x)
    z = (x - mu) / sigma
    log_gauss = -0.5 * z**2 - 0.5 * np.log(2 * np.pi * sigma**2)
    pos_tail = np.where(z > 0, -lam_pos * z * sigma, 0.0)
    neg_tail = np.where(z < 0,  lam_neg * z * sigma, 0.0)
    amplitude = C * (np.abs(z) + 1e-8) ** (-alpha)
    return log_gauss + amplitude * (pos_tail + neg_tail)

def fit_gts(returns):
    returns = returns[np.isfinite(returns)]
    if len(returns) < 20:
        return None
    mu_hat = np.mean(returns)
    sigma_hat = np.std(returns)
    kurt_hat = kurtosis(returns, fisher=True)
    def neg_log_lik(params):
        alpha, C, lam_pos, lam_neg = params
        if alpha <= 0 or alpha >= 2 or C <= 0 or lam_pos <= 0 or lam_neg <= 0:
            return 1e12
        log_p = gts_log_pdf(returns, alpha, C, lam_pos, lam_neg)
        log_p = np.clip(log_p, -1e6, 0)
        return -np.sum(log_p)
    x0 = [1.5, 0.1, 1.0/(sigma_hat+1e-8), 1.0/(sigma_hat+1e-8)]
    bounds = [(0.01, 1.99), (1e-6, 10), (0.01, 1000), (0.01, 1000)]
    res = minimize(neg_log_lik, x0, method="L-BFGS-B", bounds=bounds, options={"maxiter":500})
    if res.success:
        alpha, C, lp, ln = res.x
    else:
        alpha, C, lp, ln = x0
    return {
        "alpha": round(alpha,4), "C": round(C,6),
        "lam_pos": round(lp,4), "lam_neg": round(ln,4),
        "mu": round(mu_hat,6), "sigma": round(sigma_hat,6),
        "kurtosis": round(kurt_hat,4), "n": len(returns)
    }

# ============================================================================
# 4. Fetch data & compute rolling FCC
# ============================================================================
print("Downloading NIFTY 50 data...")
raw = yf.download(TICKER, start=START_DATE, end=END_DATE, progress=False)
if isinstance(raw.columns, pd.MultiIndex):
    close = raw[("Close", TICKER)].dropna()
else:
    close = raw["Close"].dropna()
log_ret = np.log(close / close.shift(1)).dropna()

print("Computing rolling FCC (window=252 days)...")
rolling_fcc = []
rolling_dates = []
for i in range(ROLLING_WIN, len(log_ret)):
    win = log_ret.iloc[i-ROLLING_WIN:i].values
    rolling_fcc.append(compute_fcc(win))
    rolling_dates.append(log_ret.index[i])

fcc_series = pd.Series(rolling_fcc, index=rolling_dates, name="FCC")

# Suggest thresholds based on percentiles
p33 = np.percentile(rolling_fcc, 33)
p66 = np.percentile(rolling_fcc, 66)
if FCC_LOW is None:
    FCC_LOW = p33
if FCC_HIGH is None:
    FCC_HIGH = p66
print(f"\nAuto thresholds: LOW={FCC_LOW:.3f}, HIGH={FCC_HIGH:.3f}")
print(f"  (33rd and 66th percentiles of rolling FCC)")

regime_series = fcc_series.apply(lambda x: regime_label(x, FCC_LOW, FCC_HIGH))
regime_counts = regime_series.value_counts()
print(f"\nRegime distribution:\n{regime_counts.to_string()}")

# ============================================================================
# 5. Fit GTS per regime
# ============================================================================
print("\nFitting GTS distributions to each regime...")
regime_returns = {}
gts_params = {}

for reg in ["calm", "transitional", "turbulent"]:
    mask = regime_series == reg
    rets = log_ret.reindex(fcc_series.index)[mask].dropna().values
    regime_returns[reg] = rets
    params = fit_gts(rets)
    if params is None:
        print(f"  [{reg:>12}]  n={len(rets)}   SKIPPED (insufficient data)")
        gts_params[reg] = None
    else:
        gts_params[reg] = params
        print(f"  [{reg:>12}]  n={params['n']:4d}  α={params['alpha']:.3f}  "
              f"σ={params['sigma']:.5f}  κ={params['kurtosis']:.2f}  "
              f"λ+={params['lam_pos']:.3f}  λ-={params['lam_neg']:.3f}")

# ============================================================================
# 6. Forecasting (only if turbulent has parameters)
# ============================================================================
def predict_regime(fcc_window, lookback=20):
    if len(fcc_window) < lookback:
        return regime_label(np.mean(fcc_window), FCC_LOW, FCC_HIGH)
    recent = fcc_window[-lookback:]
    slope = np.polyfit(range(lookback), recent, 1)[0]
    cur = recent[-1]
    if cur >= FCC_HIGH or (cur >= FCC_LOW and slope > 0.001):
        return "turbulent"
    elif cur <= FCC_LOW or (cur <= FCC_HIGH and slope < -0.001):
        return "calm"
    return "transitional"

if len(rolling_fcc) > 0:
    demo_pred = predict_regime(rolling_fcc)
    print(f"\nForecast for next window: {demo_pred.upper()}")
    if gts_params.get(demo_pred) is not None:
        p = gts_params[demo_pred]
        print(f"  → Apply GTS params: α={p['alpha']}, σ={p['sigma']:.5f}, "
              f"λ+={p['lam_pos']}, λ-={p['lam_neg']}")
    else:
        print(f"  → No GTS parameters available for {demo_pred} regime.")

# ============================================================================
# 7. Plotting (with corrected FancyBboxPatch)
# ============================================================================
REG_COLORS = {"calm": C_CALM, "transitional": C_TRANSIT, "turbulent": C_TURB}

def add_regime_bands(ax, fcc_s, reg_s):
    prev_reg = reg_s.iloc[0]
    start_idx = fcc_s.index[0]
    for date, reg in zip(fcc_s.index[1:], reg_s.iloc[1:]):
        if reg != prev_reg:
            ax.axvspan(start_idx, date, alpha=0.12, color=REG_COLORS[prev_reg], linewidth=0)
            prev_reg = reg
            start_idx = date
    ax.axvspan(start_idx, fcc_s.index[-1], alpha=0.12, color=REG_COLORS[prev_reg], linewidth=0)

# ---- Plot 1: Rolling FCC + Regime Bands ----
fig, ax = plt.subplots(figsize=(11, 4.5))
add_regime_bands(ax, fcc_series, regime_series)
ax.plot(fcc_series.index, fcc_series.values, color="#1a1a2e", linewidth=1.4, zorder=3)
ax.axhline(FCC_HIGH, color=C_TURB, linestyle="--", linewidth=1.2, label=f"High threshold ({FCC_HIGH:.3f})")
ax.axhline(FCC_LOW,  color=C_CALM, linestyle="--", linewidth=1.2, label=f"Low threshold ({FCC_LOW:.3f})")
patches = [mpatches.Patch(color=C_CALM, alpha=0.6, label="Calm"),
           mpatches.Patch(color=C_TRANSIT, alpha=0.6, label="Transitional"),
           mpatches.Patch(color=C_TURB, alpha=0.6, label="Turbulent")]
ax.legend(handles=patches + ax.lines[:2][::-1], fontsize=10, loc="upper left")
ax.set_title("NIFTY 50 – Rolling FCC with Regime Segmentation (2014–2023)")
ax.set_xlabel("Year"); ax.set_ylabel("FCC")
ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(RESULTS_DIR / "p11_fcc_regime_bands.png")
plt.close()
print("Saved: p11_fcc_regime_bands.png")

# ---- Plot 2: Return distributions per regime ----
labels = ["calm", "transitional", "turbulent"]
titles = [f"Calm Regime\n(FCC ≤ {FCC_LOW:.3f})",
          f"Transitional\n({FCC_LOW:.3f} < FCC < {FCC_HIGH:.3f})",
          f"Turbulent Regime\n(FCC ≥ {FCC_HIGH:.3f})"]

fig, axes = plt.subplots(1, 3, figsize=(13, 4.5), sharey=False)
for ax, reg, title in zip(axes, labels, titles):
    rets = regime_returns[reg]
    if len(rets) > 5:
        ax.hist(rets, bins=50, density=True, color=REG_COLORS[reg], alpha=0.7, edgecolor="none")
        xs = np.linspace(rets.min(), rets.max(), 300)
        ax.plot(xs, norm.pdf(xs, np.mean(rets), np.std(rets)), color="black", linewidth=1.5, linestyle="--", label="Normal fit")
    p = gts_params[reg] if gts_params[reg] is not None else {"alpha":np.nan, "sigma":np.nan, "kurtosis":np.nan}
    ax.set_title(f"{title}\nα={p['alpha']:.3f}  σ={p['sigma']:.4f}  κ={p['kurtosis']:.1f}", fontsize=15)
    ax.set_xlabel("Log return")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=10)
fig.suptitle("NIFTY 50 – Log-Return Distributions by FCC Regime", fontsize=20, y=1.02)
plt.tight_layout()
plt.savefig(RESULTS_DIR / "p11_regime_distributions.png", bbox_inches="tight")
plt.close()
print("Saved: p11_regime_distributions.png")

# ---- Plot 3: GTS parameter comparison (skip if missing) ----
valid_params = {r: gts_params[r] for r in labels if gts_params[r] is not None}
if len(valid_params) >= 2:
    params_df = pd.DataFrame({
        "Regime": list(valid_params.keys()),
        "α (tail index)": [valid_params[r]["alpha"] for r in valid_params],
        "σ (scale) ×100": [valid_params[r]["sigma"]*100 for r in valid_params],
        "λ+ (pos. tempering)": [valid_params[r]["lam_pos"] for r in valid_params],
        "λ- (neg. tempering)": [valid_params[r]["lam_neg"] for r in valid_params],
    })
    fig, axes = plt.subplots(1, 4, figsize=(14, 4))
    bar_colors = [REG_COLORS[r] for r in valid_params.keys()]
    cols = ["α (tail index)", "σ (scale) ×100", "λ+ (pos. tempering)", "λ- (neg. tempering)"]
    ylabels = ["α", "σ × 100", "λ+", "λ-"]
    for ax, col, yl in zip(axes, cols, ylabels):
        bars = ax.bar(params_df["Regime"], params_df[col], color=bar_colors, alpha=0.7, edgecolor="black", width=0.8)
        for bar, val in zip(bars, params_df[col]):
            ax.text(bar.get_x()+bar.get_width()/2.2, bar.get_height()-0.5*bar.get_height(),
                    f"{val:.3f}", ha="center", va="bottom", fontsize=12, fontweight="bold")
        ax.set_title(col, fontsize=17)
        ax.set_ylabel(yl, fontsize=13)
        ax.grid(axis="y", alpha=0.3)
        ax.tick_params(axis="x", labelsize=13)
    fig.suptitle("GTS Parameter Estimates by FCC Regime – NIFTY 50", fontsize=20)
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "p11_gts_params.png", bbox_inches="tight")
    plt.close()
    print("Saved: p11_gts_params.png")

# ---- Plot 4: Pipeline diagram (fixed FancyBboxPatch) ----
fig, ax = plt.subplots(figsize=(11, 3.5))
ax.set_xlim(0, 10); ax.set_ylim(0, 1); ax.axis("off")
steps = [
    ("Raw Prices\n(NIFTY 50)", 0.9, "#21295C"),
    ("Log Returns", 2.5, "#065A82"),
    ("Rolling FCC\n(window=252)", 4.1, "#1C7293"),
    ("Regime\nSegmentation", 5.7, C_TRANSIT),
    ("GTS Fit\nper Regime", 7.3, C_TURB),
    ("Forecast", 8.9, "#6D2E46"),
]
for label, x, col in steps:
    rect = FancyBboxPatch((x-0.65, 0.18), 1.3, 0.64, boxstyle="round,pad=0.05",
                          facecolor=col, edgecolor="white", linewidth=1.5, zorder=2)
    ax.add_patch(rect)
    ax.text(x, 0.5, label, ha="center", va="center", color="white", fontsize=14, fontweight="bold", zorder=3)
for i in range(len(steps)-1):
    x_start = steps[i][1] + 0.65
    x_end   = steps[i+1][1] - 0.65
    ax.annotate("", xy=(x_end, 0.5), xytext=(x_start, 0.5),
                arrowprops=dict(arrowstyle="->", color="#aaaaaa", lw=1.8))
ax.set_title("FCC-Guided GTS Regime-Switching Pipeline", fontsize=20, pad=10)
plt.tight_layout()
plt.savefig(RESULTS_DIR / "p11_pipeline_diagram.png", bbox_inches="tight")
plt.close()
print("Saved: p11_pipeline_diagram.png")

# ---- Plot 5: Regime timeline ----
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 5), sharex=True,
                                 gridspec_kw={"height_ratios": [3, 1]})
ax1.plot(fcc_series.index, fcc_series.values, color="#1a1a2e", linewidth=1.2)
ax1.axhline(FCC_HIGH, color=C_TURB, linestyle="--", linewidth=1, alpha=0.8)
ax1.axhline(FCC_LOW,  color=C_CALM, linestyle="--", linewidth=1, alpha=0.8)
ax1.fill_between(fcc_series.index, FCC_HIGH, fcc_series.values,
                 where=fcc_series.values >= FCC_HIGH, alpha=0.25, color=C_TURB, label="Turbulent")
ax1.fill_between(fcc_series.index, FCC_LOW, fcc_series.values,
                 where=fcc_series.values <= FCC_LOW, alpha=0.25, color=C_CALM, label="Calm")
ax1.fill_between(fcc_series.index, FCC_LOW, fcc_series.values,
                 where=(fcc_series.values > FCC_LOW) & (fcc_series.values < FCC_HIGH),
                 alpha=0.20, color=C_TRANSIT, label="Transitional")
ax1.set_ylabel("FCC"); ax1.legend(fontsize=7, loc="upper left")
ax1.grid(alpha=0.25)
# regime colour strip
reg_numeric = regime_series.map({"calm": 0, "transitional": 1, "turbulent": 2})
ax2.fill_between(regime_series.index, 0, reg_numeric.values, step="post",
                 color=C_TRANSIT, alpha=0.5)  # dummy color, overridden by lines
for date, r in regime_series.items():
    ax2.axvline(date, color=REG_COLORS[r], linewidth=0.8, alpha=0.4)
ax2.set_yticks([0,1,2]); ax2.set_yticklabels(["Calm","Trans.","Turb."], fontsize=8)
ax2.set_xlabel("Year"); ax2.grid(alpha=0.2)
fig.suptitle("NIFTY 50 – FCC-Based Regime Timeline (2014–2023)", fontsize=17)
plt.tight_layout()
plt.savefig(RESULTS_DIR / "p11_regime_timeline.png", bbox_inches="tight")
plt.close()
print("Saved: p11_regime_timeline.png")

print(f"\nAll plots saved to '{RESULTS_DIR}/'")