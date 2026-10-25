# Read sleep records, store one row per date, and export descriptive reports.

import argparse
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import sqlite3

import matplotlib.pyplot as plt
import pandas as pd

# Resolve paths from this file so terminal location does not change the input folder.
ROOT = Path(__file__).resolve().parent
FIELDS = ["diary_date", "bedtime", "wake_time", "sleep_quality", "mood",
          "doomscroll_minutes", "caffeine_cups", "exercise_minutes"]


# Validate every row before changing the database.
def load_records(path):
    return prepare_records(pd.read_csv(path, dtype=str))


# CSV imports and the dashboard form use the same calculations and entry rules.
def prepare_records(frame):
    frame = frame.fillna("").astype(str)
    # Required headers and at least one row are needed for the later calculations.
    missing = set(FIELDS) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
    if frame.empty:
        raise ValueError("The input contains no sleep records.")
    cleaned = []
    # Build one cleaned dictionary per night, preserving the source row for error messages.
    for index, row in frame.iterrows():
        try:
            day = datetime.strptime(row.diary_date, "%Y-%m-%d").date().isoformat()
            bed_time = datetime.strptime(row.bedtime, "%H:%M").time()
            wake_time = datetime.strptime(row.wake_time, "%H:%M").time()
            night_ending = datetime.strptime(day, "%Y-%m-%d").date()
            bed_day = night_ending - timedelta(days=1) if bed_time >= wake_time else night_ending
            sydney = ZoneInfo("Australia/Sydney")
            bed = datetime.combine(bed_day, bed_time, tzinfo=sydney)
            wake = datetime.combine(night_ending, wake_time, tzinfo=sydney)
            # Compare UTC instants so Sydney's spring-forward night loses one hour.
            # A same-zone datetime subtraction would only compare wall-clock times.
            hours = (wake.astimezone(timezone.utc) - bed.astimezone(timezone.utc)).total_seconds() / 3600
            if not 0 < hours <= 16:
                raise ValueError("time in bed must be above 0 and at most 16 hours")
            values = {name: float(row[name]) for name in FIELDS[3:]}
            # Reject impossible entry values before they can enter the database.
            bounds = {"sleep_quality": (1, 5), "mood": (1, 5),
                      "doomscroll_minutes": (0, 1440), "caffeine_cups": (0, 20),
                      "exercise_minutes": (0, 1440)}
            for name, (low, high) in bounds.items():
                if not low <= values[name] <= high:
                    raise ValueError(f"{name} must be between {low} and {high}")
            for name in ("sleep_quality", "mood"):
                if not values[name].is_integer():
                    raise ValueError(f"{name} must be a whole-number rating")
            # Keep rating groups explicit: 1-2, 3, and 4-5.
            quality = values["sleep_quality"]
            group = "Poor" if quality <= 2 else "Good" if quality >= 4 else "Neutral"
            cleaned.append({"diary_date": day, "bedtime": row.bedtime,
                            "wake_time": row.wake_time, **values,
                            "time_in_bed_hours": round(hours, 3), "quality_group": group})
        except ValueError as error:
            raise ValueError(f"Record {index + 1}: {error}") from error
    result = pd.DataFrame(cleaned).sort_values("diary_date")
    # Two entries for the same night inside one CSV would be ambiguous.
    if result.diary_date.duplicated().any():
        raise ValueError("Duplicate diary_date values; keep one record per night.")
    return result


# Upsert by date so re-running the same input does not duplicate nights.
def save_records(frame, db_path):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS sleep_log (
            diary_date TEXT PRIMARY KEY, bedtime TEXT, wake_time TEXT,
            sleep_quality REAL, mood REAL, doomscroll_minutes REAL,
            caffeine_cups REAL, exercise_minutes REAL,
            time_in_bed_hours REAL, quality_group TEXT)""")
        # SQL placeholders pass values separately from the SQL command.
        # The date is the key: importing an existing date updates that record.
        placeholders = ",".join("?" for _ in frame.columns)
        connection.executemany(
            f"INSERT OR REPLACE INTO sleep_log VALUES ({placeholders})",
            list(frame.itertuples(index=False, name=None)))
        # Return all stored nights, including dates from earlier imports.
        return pd.read_sql_query("SELECT * FROM sleep_log ORDER BY diary_date", connection)


# Keep group counts alongside averages so a small sample is visible.
def summarise(frame):
    # Group rows by rating, count them, then average each numeric measure.
    # Reindex fixes the display order instead of sorting group names alphabetically.
    return frame.groupby("quality_group").agg(
        nights=("diary_date", "count"),
        mean_time_in_bed_hours=("time_in_bed_hours", "mean"),
        mean_doomscroll_minutes=("doomscroll_minutes", "mean"),
        mean_caffeine_cups=("caffeine_cups", "mean"),
        mean_exercise_minutes=("exercise_minutes", "mean"),
        mean_mood=("mood", "mean"),
    ).reindex(["Poor", "Neutral", "Good"]).dropna(subset=["nights"]).round(2)


# Create an exportable picture of the first analysis stage.
def draw_chart(frame, summary, destination, label):
    plt.rcParams.update({"font.size": 10, "axes.titlesize": 20,
                         "axes.titleweight": "bold", "axes.labelsize": 12,
                         "axes.labelweight": "bold", "axes.spines.top": False,
                         "axes.spines.right": False})
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.5), layout="constrained")
    fig.set_facecolor("#f7f9fc")
    # The left chart shows individual nights; the right chart compares group averages.
    dates = pd.to_datetime(frame.diary_date)
    axes[0].plot(dates, frame.time_in_bed_hours, marker="o", color="#276b8e")
    axes[0].set(title="Last night’s time in bed", xlabel="Diary date", ylabel="Hours")
    import matplotlib.dates as mdates
    axes[0].xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=6))
    axes[0].xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    axes[0].set_ylim(0, max(10, frame.time_in_bed_hours.max() + 1))
    colors = {"Poor": "#ca765a", "Neutral": "#b59b52", "Good": "#3f927f"}
    bars = axes[1].bar(summary.index, summary.mean_doomscroll_minutes,
                       color=[colors[g] for g in summary.index])
    # Show sample sizes because a mean from one night differs from a mean from many.
    labels = [f"{v:.1f} min\nn={int(n)}" for v, n in
              zip(summary.mean_doomscroll_minutes, summary.nights)]
    axes[1].bar_label(bars, labels=labels, padding=4)
    axes[1].set_ylim(0, max(10, summary.mean_doomscroll_minutes.max() * 1.35))
    axes[1].set(title="Today’s scrolling by morning sleep rating", xlabel="Previous night’s sleep rating",
                ylabel="Mean scrolling today (min)")
    for axis in axes:
        axis.set_axisbelow(True)
        axis.grid(axis="y", color="#dce2e8", alpha=0.8)
    fig.suptitle(label, fontsize=20, fontweight="bold")
    fig.savefig(destination, dpi=220)
    plt.close(fig)


# Group nights into Monday-to-Sunday calendar weeks.
def summarise_weeks(frame):
    weekly_rows = frame.copy()
    dates = pd.to_datetime(weekly_rows["diary_date"])
    # W-SUN means a week ends on Sunday; start_time therefore identifies Monday.
    weekly_rows["week_start"] = dates.dt.to_period("W-SUN").dt.start_time.dt.strftime("%Y-%m-%d")
    # Count the actual nights rather than treating every group as seven observations.
    return weekly_rows.groupby("week_start").agg(
        nights=("diary_date", "count"),
        first_record=("diary_date", "min"),
        last_record=("diary_date", "max"),
        mean_time_in_bed_hours=("time_in_bed_hours", "mean"),
        mean_sleep_quality=("sleep_quality", "mean"),
        mean_scrolling_minutes=("doomscroll_minutes", "mean"),
        mean_mood=("mood", "mean"),
        mean_caffeine_cups=("caffeine_cups", "mean"),
        mean_exercise_minutes=("exercise_minutes", "mean"),
    ).round(2)


# Export the new weekly view so it can be shown without running the dashboard.
def draw_weekly_chart(weekly, destination, label):
    plt.rcParams.update({"axes.titlesize": 20, "axes.titleweight": "bold",
                         "axes.labelsize": 12, "axes.labelweight": "bold",
                         "axes.spines.top": False, "axes.spines.right": False})
    fig, ax = plt.subplots(figsize=(9, 5.4), layout="constrained")
    fig.set_facecolor("#f7f9fc")
    labels = pd.to_datetime(weekly.index).strftime("%d %b")
    bars = ax.bar(labels, weekly.mean_time_in_bed_hours, color="#276b8e", width=0.55)
    # The n labels make partial weeks visible in the picture itself.
    notes = [f"{hours:.2f} h\nn={int(nights)}" for hours, nights in
             zip(weekly.mean_time_in_bed_hours, weekly.nights)]
    ax.bar_label(bars, labels=notes, padding=5)
    ax.set_ylim(0, max(10, weekly.mean_time_in_bed_hours.max() + 2))
    ax.set(title="Recorded time in bed by calendar week", xlabel="Week starting Monday", ylabel="Mean hours")
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#dce2e8")
    fig.suptitle(label, fontsize=20, fontweight="bold")
    fig.supxlabel("n = recorded nights; partial weeks use only the available records", fontsize=10)
    fig.savefig(destination, dpi=220)
    plt.close(fig)


def main():
    # Defaults reproduce the packaged demo; optional paths support a different CSV.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/sleep_diary.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "output")
    parser.add_argument("--label", default="generated sleep records | development demo")
    parser.add_argument("--stored", action="store_true", help="Refresh reports from SQLite without reimporting CSV")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        if args.stored:
            # Preserve edits made in the form: read the database without CSV upserts.
            with sqlite3.connect(f"file:{args.output / 'sleep_diary.sqlite'}?mode=ro", uri=True) as connection:
                frame = pd.read_sql_query("SELECT * FROM sleep_log ORDER BY diary_date", connection)
            incoming = frame.iloc[0:0]
        else:
            incoming = load_records(args.input)
            frame = save_records(incoming, args.output / "sleep_diary.sqlite")
    except (ValueError, OSError, pd.errors.ParserError) as error:
        parser.exit(2, f"Input error: {error}\n")
    # Regenerate rating-group summaries and the calendar-week view.
    summary = summarise(frame)
    weekly = summarise_weeks(frame)
    weekly.to_csv(args.output / "weekly_summary.csv")
    draw_weekly_chart(weekly, args.output / "weekly_overview.png", args.label)
    frame.to_csv(args.output / "stored_records.csv", index=False)
    summary.to_csv(args.output / "habit_summary.csv")
    draw_chart(frame, summary, args.output / "sleep_overview.png", args.label)
    source_note = "Read stored database; no CSV imported." if args.stored else f"Loaded {len(incoming)} input rows."
    report = (f"{args.label}\n\n{source_note} Database: {len(frame)} diary days.\n"
              f"Mean time in bed: {frame.time_in_bed_hours.mean():.2f} hours.\n\n"
              + summary.to_string() + "\n\nCalendar-week comparison:\n"
              + weekly.to_string() + "\n\n"
              "Sleep quality: Poor=1-2, Neutral=3, Good=4-5.\n"
              "Mood on waking: 1 Very low, 2 Low, 3 Neutral, 4 Good, 5 Very good.\n"
              "Time in bed is derived from clock times; it is not measured sleep duration.\n"
              "Sleep and mood describe the morning of diary_date; habits describe that day before the next sleep.\n"
              "Times are local Australia/Sydney; elapsed duration accounts for daylight saving.\n"
              "These descriptive comparisons do not establish causation.\n")
    (args.output / "summary.txt").write_text(report, encoding="utf-8")
    (args.output / "run_settings.json").write_text(json.dumps({
        "mode": "stored" if args.stored else "import",
        "input_filename": None if args.stored else args.input.name, "label": args.label,
        "input_rows": len(incoming), "stored_nights": len(frame), "calendar_weeks": len(weekly)}, indent=2))
    print(report)


# Importing these functions elsewhere does not run the CSV import automatically.
if __name__ == "__main__":
    main()
