from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# --- CONFIGURATION ---

# Directory where the benchmark result files are stored.
LOGS_DIRECTORY = Path("tests/logs")
# Directory where the generated reports and charts will be saved.
REPORTS_DIRECTORY = LOGS_DIRECTORY / "reports"
# The top-level key in the JSON file that contains the list of jobs.
JOB_LIST_KEY = "scrape_group"


# --- DATA CLASSES ---

@dataclass
class MetricStats:
    """Stores detailed statistics for a single metric."""
    avg: float = 0.0
    p50: float = 0.0
    p75: float = 0.0
    p95: float = 0.0
    p50_job: Dict[str, Any] = None
    p75_job: Dict[str, Any] = None
    p95_job: Dict[str, Any] = None


@dataclass()
class StatisticForGroup():
    """Holds the calculated statistics for a group of jobs."""
    job_count: int = 0
    total_bench_time: MetricStats = field(default_factory=MetricStats)
    total_wait_time: MetricStats = field(default_factory=MetricStats)
    fetch_time: MetricStats = field(default_factory=MetricStats)
    parse_time: MetricStats = field(default_factory=MetricStats)
    # Holds the raw list of durations for plotting
    raw_durations: Dict[str, List[float]] = field(default_factory=dict)


# --- CORE LOGIC ---

class Group():
    def __init__(self, name: str, jobs: List[Dict[str, Any]]):
        self.name = name
        self.jobs = jobs

    def calculate_statistics(self) -> StatisticForGroup:
        """
        Calculates rich statistics including average and percentiles for all jobs in this group.
        """
        if not self.jobs:
            return StatisticForGroup()

        durations = {"bench_time": [], "wait_total": [], "fetch_time": [], "parse_time": []}
        valid_jobs = []

        for job in self.jobs:
            timestamps = job.get("stage_timestamps", [])
            if len(timestamps) < 7:
                continue
            valid_jobs.append(job)
            
            durations["bench_time"].append(timestamps[-1]["offset_s"] - timestamps[0]["offset_s"])
            wait_1 = timestamps[1]["offset_s"] - timestamps[0]["offset_s"]
            wait_2 = timestamps[2]["offset_s"] - timestamps[1]["offset_s"]
            durations["wait_total"].append(wait_1 + wait_2)
            durations["fetch_time"].append(timestamps[3]["offset_s"] - timestamps[2]["offset_s"])
            durations["parse_time"].append(timestamps[5]["offset_s"] - timestamps[4]["offset_s"])

        if not valid_jobs:
            return StatisticForGroup()

        def get_metric_stats(values: List[float], jobs: List[Dict]) -> MetricStats:
            if not values: return MetricStats()
            p50_val, p75_val, p95_val = np.percentile(values, [50, 75, 95])
            def find_closest_job(target_val):
                closest_index = min(range(len(values)), key=lambda i: abs(values[i] - target_val))
                return jobs[closest_index]
            return MetricStats(
                avg=np.mean(values), p50=p50_val, p75=p75_val, p95=p95_val,
                p50_job=find_closest_job(p50_val), p75_job=find_closest_job(p75_val), p95_job=find_closest_job(p95_val)
            )

        stats = StatisticForGroup(job_count=len(valid_jobs), raw_durations=durations)
        stats.total_bench_time = get_metric_stats(durations["bench_time"], valid_jobs)
        stats.total_wait_time = get_metric_stats(durations["wait_total"], valid_jobs)
        stats.fetch_time = get_metric_stats(durations["fetch_time"], valid_jobs)
        stats.parse_time = get_metric_stats(durations["parse_time"], valid_jobs)
        return stats


def read_and_segment_groups(result_path: Path) -> Tuple[Group, Group, Group]:
    print(result_path)
    with open(result_path, "r") as file:
        file_data = json.load(file)
    user_jobs, background_jobs = [], []
    all_jobs = file_data.get(JOB_LIST_KEY, [])
    for job in all_jobs:
        job_type = job.get("header", {}).get("type")
        if job_type == "user": user_jobs.append(job)
        elif job_type == "background": background_jobs.append(job)
    return (Group("COMBINED", all_jobs), Group("USER", user_jobs), Group("BACKGROUND", background_jobs))


# --- PLOTTING & REPORTING ---

def generate_report_image(group: Group, base_filename: str):
    """Generates and saves a JPG image of the statistics report."""
    stats = group.calculate_statistics()
    if stats.job_count == 0: return

    fig = plt.figure(figsize=(10, 6), dpi=120)
    plt.axis('off') # Hide the plot axes

    # --- Table Data ---
    col_labels = ['Average', 'p50', 'p75', 'p95']
    row_labels = ["End-to-End Job Time", "Total Wait Time", "HTML Fetch Time", "HTML Parse Time"]
    table_data = [
        [f"{s.avg:.2f}s", f"{s.p50:.2f}s", f"{s.p75:.2f}s", f"{s.p95:.2f}s"]
        for s in [stats.total_bench_time, stats.total_wait_time, stats.fetch_time, stats.parse_time]
    ]
    
    table = plt.table(cellText=table_data, colLabels=col_labels, rowLabels=row_labels, loc='center', cellLoc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    table.scale(1, 2)

    # --- Title and Percentile Job Info ---
    title = f"Performance Report for: {group.name} (Jobs: {stats.job_count})"
    plt.title(title, fontsize=16, y=0.85)

    def get_job_duration(job):
        ts = job['stage_timestamps']
        return ts[-1]['offset_s'] - ts[0]['offset_s']

    p_stats = stats.total_bench_time
    p50_job_uid = p_stats.p50_job['stage_timestamps'][0]['job_uid']
    p50_duration = get_job_duration(p_stats.p50_job)
    p75_job_uid = p_stats.p75_job['stage_timestamps'][0]['job_uid']
    p75_duration = get_job_duration(p_stats.p75_job)
    p95_job_uid = p_stats.p95_job['stage_timestamps'][0]['job_uid']
    p95_duration = get_job_duration(p_stats.p95_job)

    percentile_text = (
        f"Jobs at Percentiles (for End-to-End Job Time):\n"
        f"  - p50 ({p_stats.p50:.2f}s): Job {p50_job_uid[:18]}... (Actual: {p50_duration:.2f}s)\n"
        f"  - p75 ({p_stats.p75:.2f}s): Job {p75_job_uid[:18]}... (Actual: {p75_duration:.2f}s)\n"
        f"  - p95 ({p_stats.p95:.2f}s): Job {p95_job_uid[:18]}... (Actual: {p95_duration:.2f}s)"
    )
    plt.figtext(0.5, 0.2, percentile_text, ha="center", fontsize=11, family="monospace")

    plt.tight_layout()
    image_path = REPORTS_DIRECTORY / f"{base_filename}_{group.name}_report.jpg"
    plt.savefig(image_path, bbox_inches='tight', pad_inches=0.5)
    plt.close()
    print(f"   -> Saved report image: {image_path}")


def generate_charts(user_stats: StatisticForGroup, background_stats: StatisticForGroup, base_filename: str):
    """Generates and saves all comparison charts."""
    if user_stats.job_count == 0 or background_stats.job_count == 0:
        print("   -> Skipping chart generation (missing USER or BACKGROUND group).")
        return

    # 1. Comparison Bar Chart
    df = pd.DataFrame({
        'Group': ['USER', 'BACKGROUND'],
        'Average End-to-End Time (s)': [user_stats.total_bench_time.avg, background_stats.total_bench_time.avg],
        'Average Wait Time (s)': [user_stats.total_wait_time.avg, background_stats.total_wait_time.avg]
    })
    df.plot(x='Group', y=['Average End-to-End Time (s)', 'Average Wait Time (s)'], kind='bar', figsize=(10, 7), rot=0)
    plt.title(f"Performance Comparison: User vs. Background\n({base_filename})", fontsize=16)
    plt.ylabel("Time (seconds)")
    plt.grid(axis='y', linestyle='--')
    plt.tight_layout()
    bar_chart_path = REPORTS_DIRECTORY / f"{base_filename}_comparison_bar.jpg"
    plt.savefig(bar_chart_path)
    plt.close()
    print(f"   -> Saved bar chart: {bar_chart_path}")

    # 2. Latency Distribution Box Plot
    plt.figure(figsize=(10, 7))
    plt.boxplot([user_stats.raw_durations["bench_time"], background_stats.raw_durations["bench_time"]],
                labels=['USER', 'BACKGROUND'])
    plt.title(f"End-to-End Job Time Distribution\n({base_filename})", fontsize=16)
    plt.ylabel("Time (seconds)")
    plt.grid(axis='y', linestyle='--')
    plt.tight_layout()
    box_plot_path = REPORTS_DIRECTORY / f"{base_filename}_distribution_boxplot.jpg"
    plt.savefig(box_plot_path)
    plt.close()
    print(f"   -> Saved box plot: {box_plot_path}")

    # 3. Time Breakdown Stacked Bar Chart
    labels = ['USER', 'BACKGROUND']
    wait_times = [user_stats.total_wait_time.avg, background_stats.total_wait_time.avg]
    fetch_times = [user_stats.fetch_time.avg, background_stats.fetch_time.avg]
    parse_times = [user_stats.parse_time.avg, background_stats.parse_time.avg]
    
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.bar(labels, wait_times, label='Wait Time')
    ax.bar(labels, fetch_times, bottom=wait_times, label='Fetch Time')
    ax.bar(labels, parse_times, bottom=np.array(wait_times) + np.array(fetch_times), label='Parse Time')
    
    ax.set_ylabel('Average Time (seconds)')
    ax.set_title(f'Average Job Time Breakdown\n({base_filename})', fontsize=16)
    ax.legend()
    plt.tight_layout()
    stacked_bar_path = REPORTS_DIRECTORY / f"{base_filename}_breakdown_stacked_bar.jpg"
    plt.savefig(stacked_bar_path)
    plt.close()
    print(f"   -> Saved stacked bar chart: {stacked_bar_path}")


if __name__ == "__main__":
    # Create the reports directory if it doesn't exist
    REPORTS_DIRECTORY.mkdir(parents=True, exist_ok=True)

    benchmark_files = sorted(LOGS_DIRECTORY.glob("benchmark_*_*_timestamps.json"))

    if not benchmark_files:
        print(f"No benchmark files found in '{LOGS_DIRECTORY}' matching the pattern 'benchmark_*_*_timestamps.json'.")
        print("Please ensure your files are in the correct directory and you have run 'pip install matplotlib pandas numpy'.")
    
    for benchmark_file in benchmark_files:
        print("\n" + "=" * 72)
        print(f"📊 Analyzing Benchmark File: {benchmark_file.name}")
        print("=" * 72)

        # Get the base name of the file for naming the output images
        base_filename = benchmark_file.stem.replace('_timestamps', '')
        
        combined, user, background = read_and_segment_groups(benchmark_file)

        # Generate JPG reports for each group
        generate_report_image(combined, base_filename)
        generate_report_image(user, base_filename)
        generate_report_image(background, base_filename)
        
        # Generate comparison charts
        user_stats = user.calculate_statistics()
        background_stats = background.calculate_statistics()
        generate_charts(user_stats, background_stats, base_filename)

    print("\n✅ Analysis complete. All reports and charts saved in:", REPORTS_DIRECTORY)
