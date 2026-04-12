"""
Generate poster-quality charts for Sentinel Backend Results & Analysis section.
Run: conda run -n sentinel-env python3 results/generate_charts.py
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
import numpy as np
import csv
from pathlib import Path

OUT = Path(__file__).parent
OUT.mkdir(exist_ok=True)

# ── Palette ───────────────────────────────────────────────────────────────────
NAVY    = "#2C3E6B"
CORAL   = "#E8534A"
BLUE    = "#5B8DB8"
LBLUE   = "#8EAECF"
GOLD    = "#F0A500"
GREEN   = "#3DAA6D"
PURPLE  = "#7B5EA7"
ORANGE  = "#E67E22"

BG      = "#F9FAFB"
GRID    = "#E2E8F0"
TEXT    = "#1A202C"
SUBTEXT = "#4A5568"

plt.rcParams.update({
    "font.family":        "DejaVu Sans",
    "axes.facecolor":     BG,
    "figure.facecolor":   "white",
    "axes.edgecolor":     GRID,
    "axes.grid":          True,
    "grid.color":         GRID,
    "grid.linewidth":     0.8,
    "axes.titleweight":   "bold",
    "axes.titlesize":     14,
    "axes.labelsize":     11,
    "axes.labelcolor":    TEXT,
    "xtick.color":        SUBTEXT,
    "ytick.color":        SUBTEXT,
    "xtick.labelsize":    10,
    "ytick.labelsize":    10,
    "legend.framealpha":  0.9,
    "legend.edgecolor":   GRID,
    "savefig.dpi":        180,
    "savefig.bbox":       "tight",
    "savefig.facecolor":  "white",
})


# ─────────────────────────────────────────────────────────────────────────────
# 1 — Articles & Claims by Outlet (grouped bar)
# ─────────────────────────────────────────────────────────────────────────────
def chart_outlet_breakdown():
    outlets  = ["The Guardian", "BBC", "NPR", "CBS", "NBC", "ABC", "Euronews", "CBC"]
    articles = [194, 179, 115, 86, 53, 55, 56, 39]
    claims   = [1679, 1547, 831, 629, 398, 400, 346, 309]

    x = np.arange(len(outlets))
    w = 0.38

    fig, ax = plt.subplots(figsize=(11, 5.5))
    b1 = ax.bar(x - w/2, articles, w, label="Articles", color=NAVY,    zorder=3, linewidth=0)
    b2 = ax.bar(x + w/2, claims,   w, label="Claims",   color=CORAL,   zorder=3, linewidth=0)

    for bar in b1:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 18,
                str(int(bar.get_height())), ha="center", va="bottom",
                fontsize=8.5, color=NAVY, fontweight="bold")
    for bar in b2:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 18,
                str(int(bar.get_height())), ha="center", va="bottom",
                fontsize=8.5, color=CORAL, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(outlets, rotation=20, ha="right")
    ax.set_ylabel("Count")
    ax.set_title("Articles and Extracted Claims by News Outlet", pad=12)
    ax.legend(fontsize=10)
    ax.set_ylim(0, max(claims) * 1.2)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.text(0.01, 0.97, "Total: 782 articles  |  6,177 claims",
            transform=ax.transAxes, fontsize=9, color=SUBTEXT, va="top",
            bbox=dict(boxstyle="round,pad=0.3", facecolor=BG, edgecolor=GRID))

    fig.tight_layout()
    fig.savefig(OUT / "chart1_outlet_breakdown.png")
    plt.close(fig)
    print("  ✓  chart1_outlet_breakdown.png")


# ─────────────────────────────────────────────────────────────────────────────
# 2 — Centrality Score Distribution (histogram + smooth KDE via numpy)
# ─────────────────────────────────────────────────────────────────────────────
def chart_centrality_distribution():
    scores = []
    with open("tests/claims_export.csv") as f:
        for row in csv.DictReader(f):
            try:
                scores.append(float(row["centrality_score"]))
            except (ValueError, KeyError):
                pass
    scores = np.array(scores)

    fig, ax = plt.subplots(figsize=(9, 5))

    n, bins, patches = ax.hist(scores, bins=40, color=BLUE, edgecolor="white",
                                linewidth=0.5, alpha=0.85, zorder=3)
    for patch, left in zip(patches, bins[:-1]):
        if left >= 0.7:
            patch.set_facecolor(CORAL)
            patch.set_alpha(0.92)

    # smooth density via histogram convolution (no scipy needed)
    counts, edges = np.histogram(scores, bins=200, density=False)
    centers = (edges[:-1] + edges[1:]) / 2
    kernel = np.exp(-0.5 * (np.linspace(-3, 3, 21))**2)
    kernel /= kernel.sum()
    smooth = np.convolve(counts, kernel, mode="same").astype(float)
    # rescale to match histogram y scale
    bin_w_orig = bins[1] - bins[0]
    bin_w_fine = edges[1] - edges[0]
    smooth *= bin_w_fine / bin_w_orig
    ax.plot(centers, smooth, color=NAVY, linewidth=2.2, zorder=4, label="Density")

    mean_v = float(np.mean(scores))
    ax.axvline(mean_v, color=GOLD, linewidth=1.8, linestyle="--", zorder=5,
               label=f"Mean = {mean_v:.3f}")
    ax.axvspan(0.7, 1.0, alpha=0.07, color=CORAL, zorder=0)

    ymax = ax.get_ylim()[1]
    ax.text(0.845, ymax * 0.88, "High\nCentrality\n(28.1%)",
            ha="center", fontsize=9, color=CORAL, fontweight="bold")

    ax.set_xlabel("Centrality Score")
    ax.set_ylabel("Number of Claims")
    ax.set_title("Distribution of Claim Centrality Scores", pad=12)
    ax.set_xlim(0, 1)
    ax.legend(fontsize=9)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)

    stats = (f"n = {len(scores):,}\n"
             f"Mean   = {mean_v:.3f}\n"
             f"Median = {float(np.median(scores)):.3f}\n"
             f"High (≥0.7) = 28.1%")
    ax.text(0.98, 0.97, stats, transform=ax.transAxes, ha="right", va="top",
            fontsize=8.5, bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                                    edgecolor=GRID, alpha=0.95))

    fig.tight_layout()
    fig.savefig(OUT / "chart2_centrality_distribution.png")
    plt.close(fig)
    print("  ✓  chart2_centrality_distribution.png")


# ─────────────────────────────────────────────────────────────────────────────
# 3 — NLP Pipeline Latency (strip + box)
# ─────────────────────────────────────────────────────────────────────────────
def chart_nlp_latency():
    latencies = [
        12.57, 37.23, 20.62, 34.80, 26.08, 20.64, 28.80, 25.16,
        20.21,  6.34, 22.92, 31.10,  7.48, 21.11, 20.75, 26.80,
        23.44, 21.17, 35.79, 21.00, 17.41, 24.66, 20.11, 23.65,
        18.90, 18.50,
    ]
    lat = np.array(latencies)

    fig, axes = plt.subplots(1, 2, figsize=(11, 5.5),
                              gridspec_kw={"width_ratios": [2.5, 1]})

    # strip
    ax = axes[0]
    rng = np.random.default_rng(42)
    jitter = rng.uniform(-0.13, 0.13, len(lat))
    ax.scatter(np.ones(len(lat)) + jitter, lat, color=BLUE, s=95,
               zorder=5, alpha=0.85, edgecolors="white", linewidth=0.8)

    for val, label, color in [
        (lat.mean(),             f"Mean = {lat.mean():.1f}s",               GOLD),
        (np.percentile(lat, 50), f"p50  = {np.percentile(lat,50):.1f}s",    GREEN),
        (np.percentile(lat, 95), f"p95  = {np.percentile(lat,95):.1f}s",    CORAL),
    ]:
        ax.axhline(val, color=color, linewidth=1.8, linestyle="--", zorder=4)
        ax.text(1.32, val, label, va="center", fontsize=9,
                color=color, fontweight="bold")

    ax.set_xlim(0.6, 1.6)
    ax.set_xticks([])
    ax.set_ylabel("Processing Time (seconds)")
    ax.set_title("Per-Article NLP Pipeline Latency", pad=10)
    ax.spines[["top", "right", "bottom"]].set_visible(False)
    ax.set_axisbelow(True)

    # box
    ax2 = axes[1]
    ax2.boxplot(lat, vert=True, patch_artist=True,
                medianprops=dict(color=CORAL, linewidth=2.5),
                boxprops=dict(facecolor=LBLUE, alpha=0.6, linewidth=1.2),
                whiskerprops=dict(linewidth=1.2, color=NAVY),
                capprops=dict(linewidth=1.5, color=NAVY),
                flierprops=dict(marker="o", color=CORAL, markersize=6, alpha=0.7))
    ax2.set_xticklabels(["All Articles"])
    ax2.set_title("Distribution", pad=10)
    ax2.spines[["top", "right"]].set_visible(False)
    ax2.set_axisbelow(True)
    stats = (f"n = {len(lat)}\nMin  = {lat.min():.1f}s\n"
             f"Max  = {lat.max():.1f}s\nMean = {lat.mean():.1f}s")
    ax2.text(0.97, 0.03, stats, transform=ax2.transAxes, ha="right", va="bottom",
             fontsize=8.5, bbox=dict(boxstyle="round,pad=0.35", facecolor="white",
                                     edgecolor=GRID, alpha=0.95))

    fig.tight_layout(w_pad=1.5)
    fig.savefig(OUT / "chart3_nlp_latency.png")
    plt.close(fig)
    print("  ✓  chart3_nlp_latency.png")


# ─────────────────────────────────────────────────────────────────────────────
# 4 — Ingestor Deduplication (donut + daily stacked bar)
# ─────────────────────────────────────────────────────────────────────────────
def chart_ingestor_dedup():
    daily = {
        "Apr 6":  {"new": 4067,  "seen": 38773},
        "Apr 7":  {"new": 738,   "seen": 22384},
        "Apr 10": {"new": 2290,  "seen": 7939},
        "Apr 11": {"new": 589,   "seen": 8866},
    }

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5))

    # donut
    ax = axes[0]
    total_new  = sum(v["new"]  for v in daily.values())
    total_seen = sum(v["seen"] for v in daily.values())
    total = total_new + total_seen

    wedges, _ = ax.pie(
        [total_seen, total_new],
        colors=[LBLUE, CORAL],
        startangle=90,
        wedgeprops=dict(width=0.52, edgecolor="white", linewidth=2),
    )
    ax.legend(wedges,
              [f"Deduplicated  {total_seen:,}  ({total_seen/total*100:.1f}%)",
               f"Net New  {total_new:,}  ({total_new/total*100:.1f}%)"],
              loc="lower center", bbox_to_anchor=(0.5, -0.14),
              fontsize=9.5, framealpha=0.9)
    ax.text(0, 0.1,  f"{total:,}",      ha="center", va="center",
            fontsize=18, fontweight="bold", color=TEXT)
    ax.text(0, -0.15, "URLs\nProcessed", ha="center", va="center",
            fontsize=9, color=SUBTEXT)
    ax.set_title("URL Deduplication — All Cycles", pad=12)

    # stacked bar
    ax2 = axes[1]
    days  = list(daily.keys())
    news  = [daily[d]["new"]  for d in days]
    seens = [daily[d]["seen"] for d in days]
    x = np.arange(len(days))

    ax2.bar(x, seens, color=LBLUE, label="Deduplicated", zorder=3)
    ax2.bar(x, news,  bottom=seens, color=CORAL, label="Net New", zorder=3)

    for i, (n, s) in enumerate(zip(news, seens)):
        ax2.text(i, s + n + 350, f"{s+n:,}", ha="center",
                 fontsize=8.5, color=TEXT, fontweight="bold")
        ax2.text(i, s + n/2, f"+{n:,}\n({n/(n+s)*100:.0f}%)", ha="center",
                 fontsize=7.5, color="white", fontweight="bold", va="center")

    ax2.set_xticks(x)
    ax2.set_xticklabels(days)
    ax2.set_ylabel("URL Count")
    ax2.set_title("Daily Ingestor Activity", pad=12)
    ax2.legend(fontsize=9, loc="upper right")
    ax2.set_axisbelow(True)
    ax2.spines[["top", "right"]].set_visible(False)

    fig.tight_layout(w_pad=2)
    fig.savefig(OUT / "chart4_ingestor_dedup.png")
    plt.close(fig)
    print("  ✓  chart4_ingestor_dedup.png")


# ─────────────────────────────────────────────────────────────────────────────
# 5 — NLP Stage Time Breakdown (stacked horizontal bar)
# ─────────────────────────────────────────────────────────────────────────────
def chart_pipeline_stages():
    stages = [
        ("Sentence Parsing\n(spaCy)", 0.3,  GREEN),
        ("Question Generation\n(QG)", 11.5, NAVY),
        ("Question Answering\n(QA)",  3.8,  BLUE),
        ("QA→Declarative\n(QA2D)",    7.1,  LBLUE),
        ("Rewrite",                   1.8,  GOLD),
        ("CheckWorthiness\n+ NER",    1.5,  CORAL),
        ("DB Write\n(Retrieval)",      0.3, GREEN),
    ]
    total = sum(s[1] for s in stages)

    fig, ax = plt.subplots(figsize=(12, 4.2))

    left = 0
    for label, t, color in stages:
        pct = t / total * 100
        ax.barh(0, t, left=left, height=0.5, color=color,
                edgecolor="white", linewidth=1.5, zorder=3)
        if pct > 3.5:
            ax.text(left + t/2, 0, f"{t:.1f}s\n({pct:.0f}%)",
                    ha="center", va="center", fontsize=9,
                    color="white", fontweight="bold")
        left += t

    ax.set_xlim(0, total * 1.01)
    ax.set_ylim(-0.6, 0.8)
    ax.set_yticks([])
    ax.set_xlabel("Time (seconds)")
    ax.set_title(f"Average NLP Pipeline Time Breakdown  (total ≈ {total:.1f}s / article)", pad=12)
    ax.spines[["top", "left", "right"]].set_visible(False)
    ax.grid(False)

    patches = [mpatches.Patch(color=c, label=l.replace("\n", " "))
               for l, _, c in stages]
    ax.legend(handles=patches, loc="lower center",
              bbox_to_anchor=(0.5, -0.52), ncol=4, fontsize=9, framealpha=0.9)

    fig.tight_layout()
    fig.savefig(OUT / "chart5_pipeline_stages.png")
    plt.close(fig)
    print("  ✓  chart5_pipeline_stages.png")


# ─────────────────────────────────────────────────────────────────────────────
# 6 — Claims per Article by Outlet (horizontal bar)
# ─────────────────────────────────────────────────────────────────────────────
def chart_claims_per_article():
    data = dict(sorted({
        "The Guardian": 8.7, "BBC": 8.6, "CBC": 7.9, "NBC": 7.5,
        "CBS": 7.3, "ABC": 7.3, "NPR": 7.2, "Euronews": 6.2,
    }.items(), key=lambda x: x[1]))

    outlets = list(data.keys())
    values  = list(data.values())
    y = np.arange(len(outlets))

    fig, ax = plt.subplots(figsize=(9, 5))
    colors = [CORAL if v == max(values) else NAVY for v in values]
    ax.barh(y, values, color=colors, height=0.6, zorder=3,
            edgecolor="white", linewidth=0.8)

    for i, val in enumerate(values):
        ax.text(val + 0.08, i, f"{val:.1f}", va="center",
                fontsize=10.5, color=TEXT, fontweight="bold")

    avg = np.mean(values)
    ax.axvline(avg, color=GOLD, linewidth=1.8, linestyle="--",
               zorder=4, label=f"Overall avg = {avg:.1f}")

    ax.set_yticks(y)
    ax.set_yticklabels(outlets, fontsize=11)
    ax.set_xlabel("Average Claims per Article")
    ax.set_title("Average Factual Claims Extracted per Article\nby News Outlet", pad=10)
    ax.set_xlim(0, max(values) + 1.3)
    ax.legend(fontsize=9)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.xaxis.grid(True, zorder=0)
    ax.yaxis.grid(False)

    fig.tight_layout()
    fig.savefig(OUT / "chart6_claims_per_outlet.png")
    plt.close(fig)
    print("  ✓  chart6_claims_per_outlet.png")


# ─────────────────────────────────────────────────────────────────────────────
# 7 — Summary Dashboard (KPI tiles)
# ─────────────────────────────────────────────────────────────────────────────
def chart_summary_dashboard():
    metrics = [
        ("782",    "Articles\nScraped",          NAVY),
        ("6,177",  "Factual Claims\nExtracted",   CORAL),
        ("7,684",  "New Articles\nDiscovered",    BLUE),
        ("91%",    "Deduplication\nRate",          GOLD),
        ("22.7s",  "Avg NLP\nLatency",            GREEN),
        ("7.9",    "Claims per\nArticle",          LBLUE),
        ("129",    "RSS Feeds\nMonitored",         PURPLE),
        ("279ms",  "Avg DB Write\nLatency",        ORANGE),
    ]

    fig = plt.figure(figsize=(14, 4.2))
    gs  = gridspec.GridSpec(1, len(metrics), figure=fig, wspace=0.18)

    for i, (val, label, color) in enumerate(metrics):
        ax = fig.add_subplot(gs[0, i])
        ax.set_facecolor("white")
        # top coloured bar
        ax.axhspan(0.70, 1.0, color=color, alpha=0.12, transform=ax.transAxes)
        ax.plot([0, 1], [0.70, 0.70], color=color, linewidth=3,
                transform=ax.transAxes, clip_on=False)
        ax.text(0.5, 0.84, val, transform=ax.transAxes,
                ha="center", va="center", fontsize=21, fontweight="bold", color=color)
        ax.text(0.5, 0.30, label, transform=ax.transAxes,
                ha="center", va="center", fontsize=9.5, color=TEXT,
                multialignment="center")
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.axis("off")
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_edgecolor(GRID)
            spine.set_linewidth(1.2)

    fig.suptitle("Sentinel Backend — System-Wide Performance Summary",
                 fontsize=15, fontweight="bold", y=1.06, color=TEXT)
    fig.savefig(OUT / "chart7_summary_dashboard.png", bbox_inches="tight")
    plt.close(fig)
    print("  ✓  chart7_summary_dashboard.png")


# ─────────────────────────────────────────────────────────────────────────────
# 8 — CheckWorthiness Filter + Centrality Buckets (2-panel)
# ─────────────────────────────────────────────────────────────────────────────
def chart_checkworthiness():
    fig, axes = plt.subplots(1, 2, figsize=(11, 5))

    # funnel bar
    ax = axes[0]
    vals   = [326, 171]
    colors = [LBLUE, CORAL]
    labels = ["Sentences\nInput", "Passed\nCheckWorthiness\n(Claims)"]
    bars = ax.bar(labels, vals, color=colors, width=0.45,
                  zorder=3, edgecolor="white", linewidth=1)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width()/2, v + 5,
                str(v), ha="center", va="bottom", fontsize=13, fontweight="bold")

    ax.annotate("52.5%\npass rate",
                xy=(0.67, 150), xycoords=("axes fraction", "data"),
                fontsize=10.5, color=GOLD, fontweight="bold", ha="center",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                          edgecolor=GOLD, alpha=0.9))
    ax.set_ylabel("Count")
    ax.set_title("CheckWorthiness Filter\n(Claim Identification Rate)", pad=10)
    ax.set_ylim(0, 420)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.yaxis.grid(True)
    ax.xaxis.grid(False)

    # centrality bucket pie
    ax2 = axes[1]
    bucket_labels = ["0.0–0.2\n(Low)", "0.2–0.4", "0.4–0.6\n(Mid)", "0.6–0.8", "0.8–1.0\n(High)"]
    bucket_vals   = [3265, 455, 584, 329, 1544]
    bcolors       = [LBLUE, "#A8C8E0", BLUE, "#5B9BD5", CORAL]

    wedges, texts, autotexts = ax2.pie(
        bucket_vals, labels=bucket_labels, colors=bcolors,
        autopct="%1.1f%%", startangle=140,
        wedgeprops=dict(edgecolor="white", linewidth=1.5),
        pctdistance=0.78, textprops=dict(fontsize=9),
    )
    for at in autotexts:
        at.set_fontsize(9); at.set_fontweight("bold"); at.set_color("white")

    ax2.set_title("Centrality Score Distribution\n(6,177 claims)", pad=10)

    fig.tight_layout(w_pad=2.5)
    fig.savefig(OUT / "chart8_checkworthy_centrality.png")
    plt.close(fig)
    print("  ✓  chart8_checkworthy_centrality.png")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\nGenerating Sentinel Backend poster charts...\n")
    chart_outlet_breakdown()
    chart_centrality_distribution()
    chart_nlp_latency()
    chart_ingestor_dedup()
    chart_pipeline_stages()
    chart_claims_per_article()
    chart_summary_dashboard()
    chart_checkworthiness()
    print(f"\nAll charts saved to: {OUT.resolve()}\n")
