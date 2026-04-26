
"""
NIFTY Fractal Complexity Analysis (FCC) – 2014 to 2023
This script computes a simplified Fractal Complexity Coefficient (FCC) for the NIFTY 50 index,
and compares it with S&P 500 and NASDAQ over the same period.
Overall FCC is computed for the entire period, and yearly FCC is computed for each calendar year.
Observations:
- NIFTY 50 has an overall FCC of around 1.35, indicating moderate complexity.
- Yearly FCC fluctuates, with some years showing higher complexity (e.g., 2020) likely due to market turbulence.
- S&P 500 and NASDAQ have slightly higher overall FCCs, suggesting more complex price dynamics.
The script generates the following plots:
1. Rolling FCC time series for NIFTY 50 (window = 1 year)
2. Yearly FCC bar chart for NIFTY 50
3. Yearly volatility (std of log returns) for NIFTY 50
4. Yearly kurtosis (Pearson) for NIFTY 50
5. Comparison of overall FCC for NIFTY 50, S&P 500, and NASDAQ (bar chart)
All data is fetched live from Yahoo Finance, and no local data files are created. Plots are saved in the 'results/' folder with high resolution (300 dpi).
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import kurtosis
import yfinance as yf
from pathlib import Path

# ============================================================================
# 1. Configuration
# ============================================================================
START_DATE = "2014-01-01"
END_DATE   = "2024-01-01"
TICKERS = {
    "NIFTY 50":   "^NSEI",
    "S&P 500":    "^GSPC",
    "NASDAQ":     "^IXIC"
}

RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)

# ----------------------------------------------------------------------------
# Enhanced plot styling – larger text, professional dark‑theme friendly
# ----------------------------------------------------------------------------
sns.set_style("whitegrid")
plt.rcParams.update({
    "figure.figsize": (10, 5),
    "font.size": 13,               # base font size (affects legends, etc.)
    "axes.titlesize": 16,          # title font size
    "axes.labelsize": 14,          # axis labels
    "xtick.labelsize": 12,         # x‑axis tick labels
    "ytick.labelsize": 12,         # y‑axis tick labels
    "savefig.dpi": 300,
    "savefig.bbox": "tight"
})

# ============================================================================
# 2. FCC Calculation (simplified fractal complexity measure)
# ============================================================================
def compute_fcc(series, num_segments=10):
    """
    Compute Fractal Complexity Coefficient (FCC) for a 1D time series.
    FCC = 1 + log(∑ sₙ) / log(N_segments)
    where sₙ = local_range / global_range for each segment.
    """
    segments = np.array_split(series, num_segments)
    global_range = np.max(series) - np.min(series)
    if global_range == 0:
        return 1.0

    s_vals = []
    for seg in segments:
        if len(seg) > 1:
            local_range = np.max(seg) - np.min(seg)
            s_n = local_range / global_range
            s_vals.append(abs(s_n))

    if not s_vals:
        return 1.0

    s_vals = np.array(s_vals)
    fcc = 1 + np.log(np.sum(s_vals)) / np.log(len(s_vals))
    return np.clip(fcc, 1.0, 2.0)


def compute_yearly_metrics(prices_series, dates):
    """Compute yearly volatility, kurtosis, and FCC for a price series."""
    df = pd.DataFrame({"price": prices_series}, index=dates)
    df["log_return"] = np.log(df["price"] / df["price"].shift(1))

    years = df.index.year
    yearly_vol = []
    yearly_kurt = []
    yearly_fcc = []
    years_list = []

    for year in sorted(df.index.year.unique()):
        mask = years == year
        rets = df.loc[mask, "log_return"].dropna()
        if len(rets) < 10:   # skip years with too few data
            continue
        yearly_vol.append(rets.std())
        yearly_kurt.append(kurtosis(rets, fisher=False))
        yearly_fcc.append(compute_fcc(rets.values, num_segments=10))
        years_list.append(year)

    return years_list, yearly_vol, yearly_kurt, yearly_fcc

# ============================================================================
# 3. Fetch data and compute metrics for all indices (live from Yahoo Finance)
# ============================================================================
print("Downloading data from Yahoo Finance...")
all_data = {}
all_metrics = {}

for name, ticker in TICKERS.items():
    df = yf.download(ticker, start=START_DATE, end=END_DATE, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        close = df[('Close', ticker)].dropna()
    else:
        close = df['Close'].dropna()

    close = close.loc[START_DATE:END_DATE]
    all_data[name] = close

    years, vols, kurts, fccs = compute_yearly_metrics(close.values, close.index)
    all_metrics[name] = {
        "years": years,
        "volatility": vols,
        "kurtosis": kurts,
        "fcc": fccs,
        "overall_fcc": compute_fcc(close.values, num_segments=10)
    }
    print(f"  {name}: overall FCC = {all_metrics[name]['overall_fcc']:.4f}")

# ============================================================================
# 4. Generate all required plots
# ============================================================================
nifty_metrics = all_metrics["NIFTY 50"]

# ---- Plot 1: Rolling FCC time series (window = 1 year) ----
prices_nifty = all_data["NIFTY 50"]
rolling_fcc = []
window = 252  # trading days per year
for i in range(window, len(prices_nifty)):
    window_data = prices_nifty.iloc[i-window:i].values
    rolling_fcc.append(compute_fcc(window_data, num_segments=10))

plt.figure()
plt.plot(prices_nifty.index[window:], rolling_fcc, color='#2c7bb6', linewidth=1.5)
plt.title("NIFTY 50 – Rolling Fractal Complexity (FCC, window=1 year)", fontsize=16)
plt.xlabel("Year", fontsize=14)
plt.ylabel("FCC", fontsize=14)
plt.xticks(fontsize=12)
plt.yticks(fontsize=12)
plt.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(RESULTS_DIR / "fcc_timeseries.png")
plt.close()

# ---- Plot 2: FCC per year (bar chart) ----
years = nifty_metrics["years"]
fcc_yearly = nifty_metrics["fcc"]
plt.figure()
bars = plt.bar(years, fcc_yearly, color='#d7191c', alpha=0.7, edgecolor='black')
plt.axhline(y=nifty_metrics["overall_fcc"], color='#2c7bb6', linestyle='--', 
            label=f"Overall FCC = {nifty_metrics['overall_fcc']:.3f}")
plt.title("NIFTY 50 – Yearly Fractal Complexity (FCC)", fontsize=16)
plt.xlabel("Year", fontsize=14)
plt.ylabel("FCC", fontsize=14)
plt.xticks(fontsize=12)
plt.yticks(fontsize=12)
plt.legend(fontsize=12)
plt.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig(RESULTS_DIR / "fcc_per_year.png")
plt.close()

# ---- Plot 3: Volatility per year ----
plt.figure()
plt.plot(years, nifty_metrics["volatility"], marker='o', color='#4dac26', linewidth=2)
plt.title("NIFTY 50 – Yearly Volatility (std of log returns)", fontsize=16)
plt.xlabel("Year", fontsize=14)
plt.ylabel("Volatility", fontsize=14)
plt.xticks(fontsize=12)
plt.yticks(fontsize=12)
plt.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(RESULTS_DIR / "volatility_per_year.png")
plt.close()

# ---- Plot 4: Kurtosis per year ----
plt.figure()
plt.plot(years, nifty_metrics["kurtosis"], marker='s', color='#f4a582', linewidth=2)
plt.title("NIFTY 50 – Yearly Kurtosis (Pearson)", fontsize=16)
plt.xlabel("Year", fontsize=14)
plt.ylabel("Kurtosis", fontsize=14)
plt.xticks(fontsize=12)
plt.yticks(fontsize=12)
plt.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(RESULTS_DIR / "kurtosis_per_year.png")
plt.close()

# ---- Plot 5: Comparison bar chart (NIFTY vs S&P 500 vs NASDAQ) ----
indices = list(all_metrics.keys())
overall_fcc_vals = [all_metrics[idx]["overall_fcc"] for idx in indices]
colors = ['#1b9e77', '#d95f02', '#7570b3']

plt.figure(figsize=(5, 4))   
bars = plt.bar(indices, overall_fcc_vals, color=colors, alpha=0.8, edgecolor='black', width=0.6)

# Place value labels *inside* the bars (just below the top edge)
for bar, val in zip(bars, overall_fcc_vals):
    # Annotation inside bar: 5% offset from top
    y_pos = bar.get_height() - (bar.get_height() - 1.24) * 0.15   # near top inside
    plt.text(bar.get_x() + bar.get_width()/2, y_pos,
             f"{val:.3f}", ha='center', va='top', fontsize=12, color='white', fontweight='bold')

plt.title("Comparison of Overall Fractal Complexity (FCC) – 2014 to 2023", fontsize=16)
plt.ylabel("FCC (higher = more complex)", fontsize=14)
plt.ylim(1.24, 1.44)               # reduced height – focus on the range of interest
plt.xticks(fontsize=12)
plt.yticks(fontsize=12)
plt.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig(RESULTS_DIR / "comparison_indices.png")
plt.close()

print("\n" + "="*60)
print("✅ All plots saved in 'results/' folder (no local data files created).")
print("="*60)
print("\nGenerated files:")
for f in sorted(RESULTS_DIR.glob("*")):
    print(f"  {f.name}")