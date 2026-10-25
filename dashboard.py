# Explore diary days, save entries and download a reproducible comparison.

from pathlib import Path
import sqlite3

import pandas as pd
from charts import (HABITS, night_chart, ratings_chart, daily_habits_chart,
                    weekly_chart, rating_groups_chart, empty_chart)
from dash import Dash, Input, Output, State, dcc, html, no_update
from sleep_records import FIELDS, prepare_records, save_records, summarise_weeks
from start import ensure_database
from regression import run_model, regression_chart, MOOD_LABELS
from io import BytesIO
from zipfile import ZipFile
import json
import traceback
from compare_periods import compare_periods

# Use the same database as the CSV processor; each callback reads its latest rows.
ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "output/sleep_diary.sqlite"


def read_records():
    with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as connection:
        return pd.read_sql_query("SELECT * FROM sleep_log ORDER BY diary_date", connection)


# Reuse one selection rule for both the visible charts and the CSV download.
def select_records(start, end, quality):
    records = read_records()
    start = start or records.diary_date.min()
    end = end or records.diary_date.max()
    chosen = records[records.diary_date.between(start, end)].copy()
    if quality != "All":
        chosen = chosen[chosen.quality_group == quality]
    return chosen


ensure_database()
app = Dash(__name__)
app.title = "Sleep pattern explorer"



# Reuse one table renderer so daily and weekly rows have the same readable layout.
def make_table(frame, columns, headings):
    rows = [html.Tr([html.Td(value) for value in row])
            for row in frame[columns].round(2).itertuples(index=False, name=None)]
    return html.Table([html.Thead(html.Tr([html.Th(title) for title in headings])), html.Tbody(rows)])


# If a server-side chart update fails, show a visible message instead of leaving
# apparently valid old charts on screen. The terminal retains the full traceback.
def show_chart_error(error):
    traceback.print_exception(type(error), error, error.__traceback__)
    blank = empty_chart("Chart update failed — check the terminal message")
    return ("Unable to update the charts. Check the running terminal for details.",
            blank, blank, blank, blank, blank, "Not updated.", "Not updated.", [])


# Every date, rating or habit change refreshes all five chart panels and both tables.
@app.callback(Output("summary", "children"), Output("night-chart", "figure"),
              Output("ratings-chart", "figure"), Output("daily-habits-chart", "figure"),
              Output("weekly-chart", "figure"), Output("habit-chart", "figure"),
              Output("record-table", "children"), Output("weekly-table", "children"),
              Output("metric-cards", "children"),
              Input("dates", "start_date"), Input("dates", "end_date"),
              Input("quality", "value"), Input("habit", "value"), Input("refresh", "data"),
              on_error=show_chart_error)
def update_view(start, end, quality, habits, refresh):
    chosen = select_records(start, end, quality)
    # The multi-select sends a list; an empty list leaves the sleep charts available.
    habits = [name for name in (habits or []) if name in HABITS]
    if chosen.empty:
        blank = empty_chart("No matching diary days — change the dates or rating filter")
        return ("No matching diary days. Change the dates or rating group.", blank, blank, blank, blank, blank,
                "No rows to display.", "No weeks to display.", [])
    summary = f"{len(chosen)} diary days selected · {chosen.diary_date.min()} to {chosen.diary_date.max()} · Sydney local time"
    # Cards show means over the same selected records, not targets or health scores.
    cards = []
    measures = [("Time in bed", "time_in_bed_hours", "h"), ("Sleep rating", "sleep_quality", "/5"),
                ("Morning mood", "mood", "/5"), ("Scrolling", "doomscroll_minutes", "min"),
                ("Caffeine", "caffeine_cups", "cups"), ("Exercise", "exercise_minutes", "min")]
    for label, column, unit in measures:
        cards.append(html.Div([html.Span(label), html.Strong(f"{chosen[column].mean():.2f} {unit}"),
                               html.Small("Average per diary day")], className="metric-card"))
    weekly = summarise_weeks(chosen)
    daily_columns = ["diary_date", "bedtime", "wake_time", "time_in_bed_hours", "sleep_quality", "mood",
                     "doomscroll_minutes", "caffeine_cups", "exercise_minutes"]
    daily_headings = ["Diary date", "Last bedtime", "Morning wake", "Last night hours", "Sleep /5", "Morning mood /5",
                      "Scrolling min", "Caffeine cups", "Exercise min"]
    week_columns = ["week_start", "nights", "first_record", "last_record", "mean_time_in_bed_hours",
                    "mean_sleep_quality", "mean_mood", "mean_scrolling_minutes", "mean_caffeine_cups",
                    "mean_exercise_minutes"]
    week_headings = ["Week of", "Nights", "First record", "Last record", "Mean hours", "Mean sleep /5",
                     "Mean mood /5", "Mean scrolling min", "Mean caffeine cups", "Mean exercise min"]
    return (summary, night_chart(chosen), ratings_chart(chosen), daily_habits_chart(chosen, habits),
            weekly_chart(weekly, habits), rating_groups_chart(chosen, habits),
            make_table(chosen, daily_columns, daily_headings),
            make_table(weekly.reset_index(), week_columns, week_headings), cards)


# State reads the form only when Save is clicked, rather than on every keystroke.
@app.callback(Output("save-message", "children"), Output("refresh", "data"),
              Output("dates", "min_date_allowed"), Output("dates", "max_date_allowed"),
              Output("dates", "start_date"), Output("dates", "end_date"),
              Input("save-night", "n_clicks"), State("entry-date", "date"),
              State("entry-bed", "value"), State("entry-wake", "value"),
              State("entry-quality", "value"), State("entry-mood", "value"),
              State("entry-scroll", "value"), State("entry-caffeine", "value"),
              State("entry-exercise", "value"), State("replace-existing", "value"),
              prevent_initial_call=True)
def save_entry(clicks, day, bed, wake, quality, mood, scrolling, caffeine, exercise, replace):
    values = [day, bed, wake, quality, mood, scrolling, caffeine, exercise]
    # Validation happens before SQL, using the same function as CSV imports.
    try:
        incoming = prepare_records(pd.DataFrame([dict(zip(FIELDS, values))]))
    except ValueError as error:
        return (f"Not saved: {error}",) + (no_update,) * 5
    existing = incoming.diary_date.iloc[0] in set(read_records().diary_date)
    if existing and "yes" not in replace:
        return ("This date exists. Tick the update box to replace its values.",) + (no_update,) * 5
    stored = save_records(incoming, DB_PATH)
    action = "Updated" if existing else "Added"
    message = f"{action} {incoming.diary_date.iloc[0]}. Database now contains {len(stored)} diary days."
    first, last = stored.diary_date.min(), stored.diary_date.max()
    return message, clicks, first, last, first, last


# Export all stored columns for the same dates/rating filter used by the screen.
@app.callback(Output("download-records", "data"), Input("export-button", "n_clicks"),
              State("dates", "start_date"), State("dates", "end_date"),
              State("quality", "value"), prevent_initial_call=True)
def download_selection(clicks, start, end, quality):
    chosen = select_records(start, end, quality)
    # An empty selection produces a header-only CSV, never unrelated records.
    return dcc.send_data_frame(chosen.to_csv, "selected_sleep_records.csv", index=False)


@app.callback(Output("download-weeks", "data"), Input("export-weeks", "n_clicks"),
              State("dates", "start_date"), State("dates", "end_date"),
              State("quality", "value"), prevent_initial_call=True)
def download_weeks(clicks, start, end, quality):
    chosen = select_records(start, end, quality)
    return dcc.send_data_frame(summarise_weeks(chosen).to_csv, "selected_weekly_summary.csv")


# Refresh the date list after a save so newly added nights can be loaded too.
@app.callback(Output("saved-night", "options"), Input("refresh", "data"))
def list_saved_nights(refresh):
    return [{"label": "New diary day", "value": "new"}] + [
        {"label": day, "value": day} for day in read_records().diary_date]


# The load button reads the chosen row; it does not perform a database write.
@app.callback(Output("entry-date", "date"), Output("entry-bed", "value"),
              Output("entry-wake", "value"), Output("entry-quality", "value"),
              Output("entry-mood", "value"), Output("entry-scroll", "value"),
              Output("entry-caffeine", "value"), Output("entry-exercise", "value"),
              Output("replace-existing", "value"), Input("load-night", "n_clicks"),
              State("saved-night", "value"), prevent_initial_call=True)
def load_saved_night(clicks, day):
    if day == "new":
        return None, "23:00", "07:00", 4, 4, 15, 1, 30, []
    records = read_records()
    row = records.loc[records.diary_date == day].iloc[0]
    # Reset the update checkbox each time so loading is separate from choosing to update.
    return tuple(row[field] for field in FIELDS) + ([],)


@app.callback(Output("period-view", "children"), Input("dates", "start_date"),
              Input("dates", "end_date"), Input("quality", "value"), Input("refresh", "data"))
def update_periods(start, end, quality, refresh):
    records = read_records()
    start, end = start or records.diary_date.min(), end or records.diary_date.max()
    if start > end:
        return "Choose an end date on or after the start date."
    summary, changes = compare_periods(records, start, end, quality)
    coverage = " | ".join(f"{r.period}: {r.start} to {r.end}, {r.recorded_nights}/{r.calendar_days} nights"
                          for r in summary.itertuples())
    rows = []
    for row in changes.itertuples(index=False, name=None):
        # Missing comparison data stays visibly missing, rather than becoming zero.
        values = [row[0]] + ["—" if pd.isna(v) else f"{v:.2f}" for v in row[1:]]
        rows.append(html.Tr([html.Td(value) for value in values]))
    headings = ["Measure", "Previous mean", "Selected mean", "Difference"]
    return html.Div([html.P(coverage), html.Table([
        html.Thead(html.Tr([html.Th(title) for title in headings])), html.Tbody(rows)]),
        html.P("Difference = selected minus previous. Partial windows use recorded nights only.")])



# Put the displayed selection and its comparison in one portable review bundle.
# BytesIO holds the archive in memory: downloading does not alter stored records.
@app.callback(Output("download-comparison", "data"), Input("export-comparison", "n_clicks"),
              State("dates", "start_date"), State("dates", "end_date"),
              State("quality", "value"), prevent_initial_call=True)
def download_comparison(clicks, start, end, quality):
    records = read_records()
    start = start or records.diary_date.min()
    end = end or records.diary_date.max()
    if start > end:
        return no_update
    summary, changes = compare_periods(records, start, end, quality)
    # Include both windows so a reviewer can independently recalculate the means.
    first = summary.iloc[0]["start"]
    source = records[records.diary_date.between(first, end)]
    if quality != "All":
        source = source[source.quality_group == quality]
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("records.csv", source.to_csv(index=False))
        archive.writestr("period_summary.csv", summary.to_csv(index=False))
        archive.writestr("period_changes.csv", changes.to_csv(index=False))
        archive.writestr("selection.json", json.dumps({"start": start, "end": end, "rating": quality}, indent=2))
        archive.writestr("READ_ME.txt", "Previous and selected windows use equal calendar lengths.\n"
                          "Missing nights are excluded, not filled with zero. Blank means have no observations.\n"
                          "Differences = selected minus previous, before rounding.\n"
                          "Time in bed is a clock-time estimate, not measured sleep.\n"
                          "The supplied starting data is generated; later edits are entered by the app user.\n")
    return dcc.send_bytes(buffer.getvalue(), "sleep_comparison.zip")

# This callback deliberately has no date, rating or habit-filter inputs.
# Evaluation uses earlier rows; the forecast refit uses all completed date pairs.
@app.callback(Output("model-view", "children"), Input("refresh", "data"))
def update_model(refresh):
    result = run_model(read_records())
    introduction = [html.H2("Predicting the upcoming night"),
        html.P("Inputs: last night’s time in bed, today’s scrolling, caffeine and exercise, "
               "and mood on waking. Target: time in bed recorded the following calendar morning."),
        html.P("Uses the full stored diary, independently of the date, rating and habit filters above. "
               "Saving a day rebuilds the model. Time in bed is an estimate from clock times, not measured sleep.")]
    if not result["available"]:
        return html.Div(introduction + [html.P(result["message"])])
    info, forecast = result["fit_info"], result["forecast"]
    metrics = result["metrics"].copy()
    metrics["model"] = metrics.model.map({"one_hot": "One-hot mood (primary)",
        "numeric": "Numeric mood (comparison)", "training_mean": "Earlier training mean (baseline)"})
    coefficients = result["coefficients"].copy()
    coefficients["predicted_change_minutes"] = coefficients.predicted_change_minutes.map(
        lambda value: "Not estimated" if pd.isna(value) else f"{value:+.1f}")
    if forecast["predicted_hours"] is None:
        forecast_text = "Latest forecast unavailable: this mood has no completed training examples."
    elif forecast["outside_diary_range"]:
        forecast_text = "Latest model estimate falls outside the diary’s 0–16 hour range; it is not shown as a usable forecast."
    else:
        forecast_text = (f"Upcoming-night estimate: {forecast['predicted_hours']:.2f} hours in bed, "
                         f"for the night following {forecast['diary_date']} (wake date {forecast['wake_date']}).")
    return html.Div(introduction + [
        html.P(f"Evaluation trains on {info['evaluation_training_pairs']} earlier pairs, then holds out "
               f"{info['evaluation_held_out_pairs']} later pairs (wake dates {info['evaluation_target_start']} "
               f"to {info['evaluation_target_end']}). {info['evaluation_scored_pairs']} are scored; "
               "moods absent from earlier training are excluded from every comparison.", className="model-note"),
        dcc.Graph(id="regression-chart", figure=regression_chart(result), config={"displaylogo": False}),
        html.Div(make_table(metrics, ["model", "scored_nights", "mae_minutes", "r_squared"],
                            ["Model", "Scored nights", "MAE (minutes)", "R²"]), className="records"),
        html.P("Lower MAE means smaller errors. Negative R² means worse than the held-out outcome mean. "
               "Compare MAE with the earlier-training-mean baseline too. One-hot mood remains the chosen "
               "primary model; the held-out results are not used to select between encodings."),
        html.P(f"Final forecast fit: all {info['completed_pairs']} completed pairs from "
               f"{result['stored_days']} stored days. Its fitted values are not the points in the graph."),
        html.P(forecast_text, className="summary"),
        html.P("The forecast assumes today’s habit totals are complete. Update them before bed. "
               "An unrecorded following morning is never invented as a training outcome."),
        html.Details([html.Summary("How the inputs contribute"),
            html.P("These coefficients come from the full-data fit. Each change holds other inputs constant. "
                   "Mood uses separate indicators with Neutral (3) as the reference. "
                   "They describe model associations, not proven effects."),
            html.Div(make_table(coefficients, ["feature", "input_change", "predicted_change_minutes", "status"],
                ["Input", "Change", "Predicted minutes", "Coverage"]), className="records")]),
        html.P("Performance here describes computer-generated demonstration records, not collected personal observations.",
               className="footnote")])


# A fresh layout includes real figures, summary and table before any callback runs.
# This also reads the latest database dates when another tab opens the application.
def serve_layout():
    records = read_records()
    first_date, last_date = records.diary_date.min(), records.diary_date.max()
    initial_start = max(first_date, (pd.Timestamp(last_date) - pd.Timedelta(days=6)).date().isoformat())
    (initial_summary, night_figure, ratings_figure, daily_habits_figure, weekly_figure,
     habit_figure, initial_table, initial_weekly_table, initial_cards) = update_view(
        initial_start, last_date, "All", list(HABITS), 0)
    return html.Main([
        html.P("WEMANQ / SLEEP JOURNAL", className="eyebrow"),
        html.H1("Sleep pattern explorer"),
        html.P("Your diary of morning sleep, mood and daily habits. Explore the records, update a day or export a selection."),
        html.P("Times use Australia/Sydney. The supplied demonstration diary covers 1 September–20 October 2026.", className="footnote"),
        dcc.Store(id="refresh", data=0),
        html.Details([
            html.Summary("Mood ratings and diary dates"),
            html.P("Record mood on waking: how you feel that morning. These are diary labels, not a clinical scale."),
            html.Ul([html.Li(f"{level} — {meaning}") for level, meaning in MOOD_LABELS.items()]),
            html.P("For 1 September: sleep and mood describe waking on 1 September. "
                   "Habits describe 1 September daytime/evening. Those habits help predict "
                   "the next night, whose duration is recorded on 2 September."),
            html.P("Bedtime uses the previous date when the clock time is later than wake time; "
                   "an after-midnight bedtime before wake time uses the diary date.")
        ], className="entry-panel"),
        html.Details([
            html.Summary("Add or update a diary day"),
            html.P("Choose the calendar day. Bed/wake times and ratings describe the night ending that morning; "
                   "habits describe the chosen day before the upcoming sleep. Times use HH:MM."),
            html.Label("Load a saved day, or start a new entry"),
            dcc.Dropdown(id="saved-night", options=list_saved_nights(0), value="new", clearable=False),
            html.Button("Load into form", id="load-night", n_clicks=0),
            html.P("Loading only fills the form. Click Save day to store your changes."),
            html.Div([
                html.Div([html.Label("Diary date"), dcc.DatePickerSingle(
                    id="entry-date", date=None, display_format="DD MMM YYYY")]),
                html.Div([html.Label("Last night’s bedtime"), dcc.Input(id="entry-bed", type="text", value="23:00")]),
                html.Div([html.Label("This morning’s wake time"), dcc.Input(id="entry-wake", type="text", value="07:00")]),
                html.Div([html.Label("Last night’s sleep rating (1–5)"), dcc.Input(id="entry-quality", type="number", min=1, max=5, step=1, value=4)]),
                html.Div([html.Label("Mood on waking (1–5)"), dcc.Input(id="entry-mood", type="number", min=1, max=5, step=1, value=4)]),
                html.Div([html.Label("Today’s scrolling (minutes)"), dcc.Input(id="entry-scroll", type="number", min=0, max=1440, value=15)]),
                html.Div([html.Label("Today’s caffeine (cups)"), dcc.Input(id="entry-caffeine", type="number", min=0, max=20, value=1)]),
                html.Div([html.Label("Today’s exercise (minutes)"), dcc.Input(id="entry-exercise", type="number", min=0, max=1440, value=30)]),
            ], className="entry-grid"),
            dcc.Checklist(id="replace-existing", options=[{"label": "Update this date if it already exists", "value": "yes"}], value=[]),
            html.Button("Save day", id="save-night", n_clicks=0),
            html.P(id="save-message", role="status"),
            html.P("Saving refreshes the dashboard and selects the full stored date range. "
                   "Rating and habit filters stay as selected. The full-diary model also refreshes. Static reports are regenerated separately.", className="footnote"),
        ], className="entry-panel"),
        html.Div([
            html.Div([html.Label("Diary dates"), dcc.DatePickerRange(
                id="dates", min_date_allowed=first_date, max_date_allowed=last_date,
                start_date=initial_start, end_date=last_date, initial_visible_month=last_date,
                minimum_nights=0, display_format="DD MMM YYYY")]),
            html.Div([html.Label("Sleep rating group"), dcc.Dropdown(
                id="quality", options=["All", "Poor", "Neutral", "Good"], value="All", clearable=False)]),
            html.Div([html.Label("Habits to compare · select several"), dcc.Dropdown(
                id="habit", options=[{"label": label, "value": column} for column, label in HABITS.items()],
                value=list(HABITS), multi=True, clearable=True, placeholder="Choose habits")]),
        ], className="controls"),
        html.P(initial_summary, id="summary", className="summary", role="status"),
        html.Div(initial_cards, id="metric-cards", className="metric-cards"),
        html.P("Each card averages the currently selected records. Choose several habits above; cups and minutes keep separate axes.", className="footnote"),
        dcc.Loading(html.Div([
            html.Div([dcc.Graph(id="night-chart", figure=night_figure, config={"displaylogo": False}),
                      dcc.Graph(id="ratings-chart", figure=ratings_figure, config={"displaylogo": False})], className="charts"),
            dcc.Graph(id="daily-habits-chart", figure=daily_habits_figure, config={"displaylogo": False}),
            dcc.Graph(id="weekly-chart", figure=weekly_figure, config={"displaylogo": False}),
            dcc.Graph(id="habit-chart", figure=habit_figure, config={"displaylogo": False}),
        ], className="chart-panels"), type="circle"),
        html.Div(update_model(0), id="model-view", className="model-panel"),
        html.H2("Weekly measures"),
        html.P("Monday–Sunday weeks; averages and counts use selected recorded nights only. Date and rating filters can make a week partial."),
        html.Button("Download weekly CSV", id="export-weeks", n_clicks=0),
        dcc.Download(id="download-weeks"),
        html.Div(initial_weekly_table, id="weekly-table", className="records"),
        html.H2("Compared with the preceding date window"),
        html.P("The same rating filter applies to both windows. The opening view uses the latest seven nights. Select other dates to compare an equally long preceding window."),
        html.Div(update_periods(initial_start, last_date, "All", 0), id="period-view", className="records"),
        html.Button("Download comparison ZIP", id="export-comparison", n_clicks=0),
        dcc.Download(id="download-comparison"),
        html.H2("Daily measures"),
        html.Button("Download selected CSV", id="export-button", n_clicks=0),
        dcc.Download(id="download-records"),
        html.Div(initial_table, id="record-table", className="records"),
        html.P("Time in bed uses Sydney local times and accounts for daylight saving. Group averages describe this sample and do not establish causation.",
               className="footnote"),
    ])


app.layout = serve_layout

# Keep this terminal running while viewing the page; Ctrl+C stops the local server.
if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=8050)
