# Sleep pattern explorer

A local diary for reviewing morning sleep, mood and daily habits, with a linear model for the upcoming night. This package contains the Python source, an editable SQLite diary, exported charts and model results for peer evaluation.

The supplied **50 diary days, 1 September–20 October 2026**, are demonstration records for a Sydney-based student studying at UTS.

## 1. Open the project

Use Python 3.11 or 3.12:

```bash
python -m venv .venv
```

Activate with `.venv\Scripts\activate` on Windows or `source .venv/bin/activate` on macOS/Linux, then:

```bash
python -m pip install -r requirements.txt
python start.py
```

Open **http://127.0.0.1:8050**. Keep the terminal open. Installation needs internet access; the dashboard uses local files. If an older page remains, reload fully with Ctrl+Shift+R on Windows or Cmd+Shift+R on macOS. Port 8050 must be free.

## 2. Understand a diary row before entering data

The date is a **calendar diary day**, not a label for all the activities before that morning's sleep.

| Field on 1 September | Meaning |
| --- | --- |
| `diary_date` | 1 September 2026 |
| `bedtime`, `wake_time` | The sleep period ending on the morning of 1 September |
| `time_in_bed_hours` | Duration of that previous night, calculated from the clock times |
| `sleep_quality` | Rating for that previous night |
| `mood` | How you feel on waking on 1 September |
| `doomscroll_minutes`, `caffeine_cups`, `exercise_minutes` | Totals for 1 September daytime/evening, before the upcoming sleep |
| Model target | Duration recorded on 2 September, after the upcoming night has finished |

A 23:00 bedtime with a 07:00 wake time belongs to the previous calendar evening. A 01:00 bedtime with a 08:00 wake time is on the diary date itself. Times use Australia/Sydney and elapsed duration includes daylight saving. For example, 01:50–08:50 on 4 October 2026 is six elapsed hours. This simple overnight convention does not represent split sleep, naps or shift-work schedules.

**Time in bed is not measured sleep duration.** The app does not know how long you took to fall asleep or how long you were awake overnight.

### Mood guide

Record mood **on waking**, before the daytime habits and the night being predicted. These labels are a diary convention, not a clinical assessment.

| Rating | Meaning |
| --- | --- |
| 1 | Very low |
| 2 | Low |
| 3 | Neutral |
| 4 | Good |
| 5 | Very good |

The dashboard has a collapsible **Mood ratings and diary dates** guide. The mood chart includes the same key. Sleep quality is a separate rating: 1–2 Poor, 3 Neutral, 4–5 Good.

## 3. Try the dashboard

The opening selection is **14–20 October**. All six chart panels have figures in the initial layout; the tables and six summary cards are also populated. Chart data uses ordinary JSON lists.

1. Choose dates and a sleep-rating group to explore the descriptive views.
2. Select several habits in **Habits to compare**. Cups and minutes retain separate axes. Clearing the habits leaves the sleep views available.
3. Open **Add or update a diary day**, select a saved day and click **Load into form**. Loading does not write data. To replace that date, tick the update box and click **Save day**.
4. For a new record, load **New diary day**, choose its date and enter the morning values and that day's habits. Update the habit totals before bed if they were incomplete earlier.
5. Saving refreshes the descriptive dashboard and the full-diary model, and selects the full stored date range. Rating and habit choices remain selected.
6. Download daily records, weekly means or the comparison ZIP. Restarting preserves entries in `output/sleep_diary.sqlite`.

Use a separate extracted copy for experiments if you want to preserve the bundled records. This is a local single-user prototype with no accounts, cloud sync or delete button.

### Charts and measures

| Chart | Interpretation |
| --- | --- |
| Last night's time in bed | Previous-night duration for each selected diary date |
| Sleep rating and mood | Previous-night sleep quality and mood on waking, with a mood meaning key |
| Daily habits | That day's scrolling, caffeine and exercise on separate scales |
| Calendar-week averages | Selected diary-day means, with recorded counts and partial weeks visible |
| Today's habits by morning sleep rating | Today's habits grouped by the **previous** night's rating; this does not estimate how those habits affect the upcoming night |
| Next-night prediction: observed vs predicted | Predictions for later held-out nights, compared with their recorded durations |

Main chart titles are bold, unnumbered and larger than axis labels. The daily table contains all recorded variables; the weekly table contains their means and coverage. Weeks run Monday–Sunday. A date or rating filter can leave a partial week. The six cards average the selected records; habit selection changes displayed series, not which records are counted. Mean mood in summaries is descriptive; the primary model does not treat the numeric mood codes as equally spaced effects.

The period comparison uses the selected window and an immediately preceding window of equal calendar length. Missing dates are excluded, not filled with zeros. A difference is selected mean minus previous mean. Its default windows are 14–20 October and 7–13 October.

## 4. How the prediction works

The four numeric inputs for diary day D are **previous-night time in bed, today's scrolling, today's caffeine and today's exercise**. Morning mood supplies categorical inputs. The target is time in bed on **D + 1 calendar day**.

`make_pairs()` joins by exact date. Sorting then shifting blindly would pair unrelated dates when a day is missing; this code does not. Sleep quality, future mood, future habits and the target's bed/wake times are not model features. The last diary day has no outcome yet and is used for forecasting, not as a completed training pair.

### Mood encoding

The primary linear model uses indicators for mood 1, 2, 4 and 5, with **Neutral (3) as the reference** and an intercept. This allows each mood category a different association instead of forcing a constant step per rating. The diary keeps its original 1–5 values. Mood 1 has no completed examples in this package, so its coefficient is labelled **not estimated**; it is not interpreted as a zero effect. A latest entry with an unsupported mood receives no forecast.

### Evaluation and full-data training

Dashboard date, rating and habit filters **never select model training rows**. With the supplied data:

| Stage | Rows and dates |
| --- | --- |
| Completed pairs | 49, with input dates 1 September–19 October |
| Evaluation training | First 39 pairs: input dates 1 September–9 October, outcomes 2 September–10 October |
| Held-out evaluation | Last 10 pairs: input dates 10–19 October, outcomes 11–20 October |
| Final forecast fit | All 49 completed pairs, after evaluation |
| Latest forecast input | 20 October; predicts the night ending 21 October, whose outcome is unknown |

The graph shows **held-out predictions**, not the final model's fitted values. Its dashed diagonal represents perfect agreement. A separate table compares the preselected one-hot model, a numeric-mood alternative and a constant prediction equal to the earlier training outcomes' mean. All comparisons score the same supported held-out dates; an evaluation mood absent from earlier training is excluded from every metric.

On the included data, one-hot MAE is **40.18 minutes**, numeric-mood MAE **39.16 minutes**, and baseline MAE **32.92 minutes**. One-hot R² is approximately **−0.99**. The primary model therefore does not outperform the simple baseline on this split. Lower MAE is better. Negative R² means worse squared-error performance than the held-out outcome mean. The baseline is calculated from training data, so its comparison is separate. These results are development examples, not evidence of real-world predictive accuracy.

The primary encoding remains one-hot; the test results are not used to choose a winner. There is no tuning or claim that these habits cause changes in sleep. Coefficients are from the full-data refit and express predicted minute differences while holding other inputs constant. They can be unstable with limited data or rare moods.

The model requires at least 30 completed pairs (20 earlier training pairs and 10 held-out pairs), and a Neutral mood in the evaluation training period. Otherwise the dashboard explains why the model is unavailable. The forecast assumes daytime totals are complete. The app does not clip implausible estimates into a convincing-looking range: an estimate outside its 0–16 hour entry range is flagged and not displayed as usable.

## 5. What each script does

**`start.py` — launch and report refresh.** `ensure_database()` seeds the CSV only if the SQLite file is missing, preserving ordinary edits on restart. Without options it opens the Dash server. With `--reports` it runs the reporting scripts and model export against stored records.

**`sleep_records.py` — prepare and save the diary.** `prepare_records()` checks the eight input columns, parses dates and times, calculates Sydney elapsed duration and attaches sleep-rating groups. Required checks protect database writes; they are not a separate testing framework. `save_records()` uses a date primary key to insert or replace one diary day. `summarise()` and `summarise_weeks()` calculate counts and means. The script also produces the original static overview charts and a text report.

**`dashboard.py` — forms, tables and callbacks.** `serve_layout()` builds an initially populated page. `update_view()` applies descriptive filters and returns five figures, cards and tables. `save_entry()` validates form values before storing them; loading only fills the form. `update_model()` reads the entire database and depends only on the save refresh signal, not the filters. Download callbacks build CSVs or an in-memory comparison archive without changing stored data.

**`charts.py` — five descriptive Plotly figures.** Small chart functions accept selected frames. `finish_chart()` centralises font sizes, bold titles and spacing. Habit panels use separate subplots so unlike units are not mixed. Empty selections receive a readable message. The rating plot includes the mood key.

**`regression.py` — pairing, fitting and exporting.** `make_pairs()` matches D to D+1. `new_model()` combines a column transformer and linear regression in a scikit-learn pipeline. `run_model()` separates earlier training and later evaluation, calculates comparable errors, refits one-hot regression on all pairs and prepares the latest forecast. `regression_chart()` draws the held-out scatter plot. `export_model()` writes pairs, predictions, errors, coefficients, metadata and a PNG. The saved JSON contains the fitted feature names, intercept and coefficients, not an opaque model file; the app refits directly from the diary when needed.

**`compare_periods.py` — equal-length date windows.** `compare_periods()` applies the same rating filter to both windows, retains coverage counts and subtracts unrounded means. Its command-line output uses the latest seven days against the preceding seven.

**`export_trends.py` — offline charts.** Reads SQLite and writes daily/weekly habit charts and a mood/rating chart. These PNGs can be inspected without starting the dashboard.

**`make_demo_data.py` — reproducible data construction.** `build_morning_records()` recreates the earlier 50-record example with its literal first 14 morning records and fixed random seed `20261020`. `build_demo()` preserves morning sleep/ratings/mood and moves each old pre-night habit set to the preceding calendar day. The final 20 October habit totals are explicit example values. `main()` writes the diary CSV, context CSV and alignment audit. Running this script changes CSVs only, not SQLite. Read `data/ABOUT_THE_DATA.md` before importing older data.

## 6. Refresh or inspect exported results

```bash
python start.py --reports
```

| Location | Contents |
| --- | --- |
| `data/sleep_diary.csv` | Eight input columns for 50 diary days |
| `data/day_context.csv` | Generated scenario context, not a model feature |
| `data/alignment_audit.csv` | Original source date and the habit reassignment explanation |
| `output/sleep_diary.sqlite` | Editable diary used by the dashboard |
| `output/stored_records.csv` | Current records including duration and rating group |
| `output/habit_summary.csv`, `weekly_summary.csv` | Group and calendar-week counts and means |
| `output/period_*.csv`, `period_notes.txt` | Selected/preceding window calculations |
| `output/*.png` | Six static descriptive chart files |
| `output/summary.txt`, `run_settings.json` | Report text and run settings |
| `output/model/model_pairs.csv` | Completed date-aligned input/target pairs |
| `output/model/held_out_predictions.csv` | Evaluation outcomes, predictions and mood support flags |
| `output/model/model_metrics.csv` | MAE, RMSE, R² and scored counts |
| `output/model/coefficients.csv`, `model_info.json` | Full-data coefficient descriptions and fit metadata |
| `output/model/latest_prediction.json` | Forecast date, value and support/range flags |
| `output/model/regression.png`, `model_notes.txt` | Offline model chart and interpretation |

To intentionally import another CSV using the same eight headers and calendar-day convention:

```bash
python sleep_records.py --input data/my_diary.csv --label "My imported entries"
python start.py --reports
```

Imports replace matching dates and preserve other stored dates. Running `sleep_records.py` without arguments intentionally reimports the packaged examples. Use `start.py` for ordinary launches. Do not import the old wake-date CSV without first aligning its habits.
