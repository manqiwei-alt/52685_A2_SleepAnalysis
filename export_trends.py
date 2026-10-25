# Save daily and weekly habit views for reviewing without the dashboard.
from pathlib import Path
import sqlite3
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
from sleep_records import summarise_weeks

ROOT = Path(__file__).resolve().parent
HABITS = [("doomscroll_minutes", "mean_scrolling_minutes", "Scrolling (minutes)", "#6a72a5"),
          ("caffeine_cups", "mean_caffeine_cups", "Caffeine (cups)", "#b08043"),
          ("exercise_minutes", "mean_exercise_minutes", "Exercise (minutes)", "#3f927f")]


def main():
    with sqlite3.connect(f"file:{ROOT / 'output/sleep_diary.sqlite'}?mode=ro", uri=True) as connection:
        frame = pd.read_sql_query("SELECT * FROM sleep_log ORDER BY diary_date", connection)
    weekly = summarise_weeks(frame)
    plt.rcParams.update({"axes.titlesize": 20, "axes.titleweight": "bold",
                         "axes.labelsize": 12, "axes.labelweight": "bold",
                         "axes.spines.top": False, "axes.spines.right": False})
    # Each variable keeps its own axis and unit in both daily and weekly exports.
    for period in ["daily", "weekly"]:
        fig, axes = plt.subplots(3, 1, figsize=(11, 10), layout="constrained", facecolor="#f7f9fc")
        for ax, (column, weekly_column, label, colour) in zip(axes, HABITS):
            if period == "daily":
                ax.bar(pd.to_datetime(frame.diary_date), frame[column], color=colour)
                ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
            else:
                bars = ax.bar(pd.to_datetime(weekly.index).strftime("%d %b"), weekly[weekly_column], color=colour)
                ax.bar_label(bars, labels=[f"{v:.1f}\nn={int(n)}" for v, n in zip(weekly[weekly_column], weekly.nights)], padding=4)
                ax.set_ylim(0, max(1, weekly[weekly_column].max() * 1.45))
            ax.set(title=label, ylabel="Daily value" if period == "daily" else "Recorded-night mean")
            ax.grid(axis="y", color="#dce2e8"); ax.set_axisbelow(True)
        axes[-1].set_xlabel("Diary date" if period == "daily" else "Week starting Monday")
        fig.suptitle(f"{period.title()} habits | stored records", fontsize=20, fontweight="bold")
        fig.supxlabel("Computer-generated demonstration records. Weekly means use recorded nights only.", fontsize=10)
        fig.savefig(ROOT / f"output/{period}_habits.png", dpi=220)
        plt.close(fig)
    # Keep ratings together because both use the same 1–5 scale.
    fig, ax = plt.subplots(figsize=(11, 5), layout="constrained", facecolor="#f7f9fc")
    dates = pd.to_datetime(frame.diary_date)
    ax.plot(dates, frame.sleep_quality, marker="o", color="#276b8e", label="Sleep rating")
    ax.plot(dates, frame.mood, marker="s", color="#bc7c52", label="Morning mood")
    ax.set(title="Daily sleep rating and mood", ylabel="Self-reported rating /5", xlabel="Diary date",
           ylim=(0.7, 5.3), yticks=[1, 2, 3, 4, 5])
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.legend(); ax.grid(axis="y", color="#dce2e8")
    fig.supxlabel("Mood: 1 Very low | 2 Low | 3 Neutral | 4 Good | 5 Very good\nMorning ratings; generated demonstration records.", fontsize=10)
    fig.savefig(ROOT / "output/daily_ratings.png", dpi=220)
    plt.close(fig)
    print("Saved daily_habits.png, weekly_habits.png and daily_ratings.png")


if __name__ == "__main__":
    main()
