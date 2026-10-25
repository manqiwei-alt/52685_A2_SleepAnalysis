# Compare a selected window with the preceding equally long window.
from pathlib import Path
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
MEASURES = {"time_in_bed_hours": "Time in bed (h)", "sleep_quality": "Sleep rating (1–5)",
            "mood": "Mood (1–5)", "doomscroll_minutes": "Scrolling (min)"}


# Calendar length defines the windows; missing dates do not become zero-valued nights.
def compare_periods(records, start, end, quality="All"):
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    days = (end - start).days + 1
    if days < 1:
        raise ValueError("The end date must be on or after the start date.")
    earlier_end = start - pd.Timedelta(days=1)
    earlier_start = start - pd.Timedelta(days=days)
    periods = []
    for label, first, last in [("Previous", earlier_start, earlier_end), ("Selected", start, end)]:
        chosen = records[records.diary_date.between(first.strftime("%Y-%m-%d"), last.strftime("%Y-%m-%d"))]
        if quality != "All":
            chosen = chosen[chosen.quality_group == quality]
        row = {"period": label, "start": first.strftime("%Y-%m-%d"), "end": last.strftime("%Y-%m-%d"),
               "calendar_days": days, "recorded_nights": len(chosen), "rating_filter": quality}
        row.update({name: chosen[name].mean() for name in MEASURES})
        periods.append(row)
    # NaN means there is no mean for an empty window, rather than an average of zero.
    summary = pd.DataFrame(periods)
    changes = pd.DataFrame([{"measure": label, "previous_mean": summary.iloc[0][name],
                             "selected_mean": summary.iloc[1][name],
                             "difference": summary.iloc[1][name] - summary.iloc[0][name]}
                            for name, label in MEASURES.items()])
    return summary, changes


def main():
    with sqlite3.connect(f"file:{ROOT / 'output/sleep_diary.sqlite'}?mode=ro", uri=True) as connection:
        records = pd.read_sql_query("SELECT * FROM sleep_log ORDER BY diary_date", connection)
    # The export demonstration uses the latest seven calendar dates in the database.
    end = pd.Timestamp(records.diary_date.max())
    start = end - pd.Timedelta(days=6)
    summary, changes = compare_periods(records, start, end)
    summary.round(3).to_csv(ROOT / "output/period_summary.csv", index=False)
    changes.round(3).to_csv(ROOT / "output/period_changes.csv", index=False)
    text = ("SLEEP JOURNAL / CONSECUTIVE DATE WINDOWS\nStored records (starting data: generated examples)\n\n"
            + summary.to_string(index=False) + "\n\n" + changes.round(3).to_string(index=False)
            + "\n\nDifference = selected mean minus previous mean, calculated before rounding.\n"
              "Only recorded nights contribute. An empty period has no mean or difference.\n"
              "These are descriptive differences; they do not establish a habit's effect.\n")
    (ROOT / "output/period_notes.txt").write_text(text, encoding="utf-8")
    print(text)
    plt.rcParams.update({"axes.titlesize": 20, "axes.titleweight": "bold", "axes.labelsize": 12,
                         "axes.labelweight": "bold", "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), layout="constrained", facecolor="#f7f9fc")
    for ax, column in zip(axes, ["time_in_bed_hours", "doomscroll_minutes"]):
        values = summary[column]
        bars = ax.bar(summary.period, values.fillna(0), color=["#97b6c7", "#276b8e"], width=0.55)
        labels = ["No records" if pd.isna(v) else f"{v:.2f}\nn={int(n)}" for v, n in zip(values, summary.recorded_nights)]
        ax.bar_label(bars, labels=labels, padding=5)
        ax.set(title=MEASURES[column], ylabel=MEASURES[column], ylim=(0, max(1, values.max() * 1.35)))
        ax.grid(axis="y", color="#dce2e8"); ax.set_axisbelow(True)
    fig.suptitle("Selected dates and the preceding window", fontsize=20, fontweight="bold")
    fig.supxlabel(f"Previous: {summary.iloc[0]['start']} to {summary.iloc[0]['end']} | Selected: {summary.iloc[1]['start']} to {summary.iloc[1]['end']}\nn = recorded nights; starting data: generated examples", fontsize=10)
    fig.savefig(ROOT / "output/period_comparison.png", dpi=220)
    plt.close(fig)


if __name__ == "__main__":
    main()
