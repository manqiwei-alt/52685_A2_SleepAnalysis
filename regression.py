# Predict the upcoming night's time in bed from a calendar-day diary."""

from pathlib import Path
import json
import sqlite3
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import matplotlib.pyplot as plt
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LinearRegression
from charts import finish_chart, empty_chart

ROOT = Path(__file__).resolve().parent
NUMERIC = ["time_in_bed_hours", "doomscroll_minutes", "caffeine_cups", "exercise_minutes"]
FEATURES = NUMERIC + ["mood"]
MOOD_LABELS = {1: "Very low", 2: "Low", 3: "Neutral", 4: "Good", 5: "Very good"}


def make_pairs(records):
    # Join by exact calendar date, not by physical row order. A gap creates no pair.
    days = records.sort_values("diary_date").copy()
    days["target_date"] = (pd.to_datetime(days.diary_date) + pd.Timedelta(days=1)).dt.strftime("%Y-%m-%d")
    outcomes = records[["diary_date", "time_in_bed_hours"]].rename(
        columns={"diary_date": "target_date", "time_in_bed_hours": "next_night_hours"})
    return days.merge(outcomes, on="target_date", how="inner", validate="one_to_one").sort_values("diary_date").reset_index(drop=True)


def new_model(encoding):
    # Category meanings are fixed by the diary guide. Neutral (3) is the reference.
    # Fit the preprocessing and regression together using training rows only.
    if encoding == "one_hot":
        encoder = OneHotEncoder(categories=[[1, 2, 3, 4, 5]], drop=[3], sparse_output=False)
        transform = ColumnTransformer([("numeric", "passthrough", NUMERIC), ("mood", encoder, ["mood"])])
    else:
        transform = ColumnTransformer([("numeric", "passthrough", FEATURES)])
    return Pipeline([("features", transform), ("linear", LinearRegression())])


def score_predictions(actual, predicted):
    # Undefined R-squared stays absent when there is no variation in actual hours.
    actual, predicted = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    if len(actual) == 0:
        return {"mae_minutes": None, "rmse_hours": None, "r_squared": None}
    errors = actual - predicted
    denominator = float(np.sum((actual - actual.mean()) ** 2))
    return {"mae_minutes": float(np.mean(np.abs(errors)) * 60),
            "rmse_hours": float(np.sqrt(np.mean(errors ** 2))),
            "r_squared": float(1 - np.sum(errors ** 2) / denominator) if denominator > 0 else None}


def run_model(records):
    pairs = make_pairs(records)
    result = {"available": False, "stored_days": len(records), "eligible_pairs": len(pairs), "pairs": pairs}
    # Ten later examples are reserved for evaluation; at least twenty precede them.
    if len(pairs) < 30:
        result["message"] = "At least 30 completed consecutive-day pairs are needed: 20 for training and 10 for evaluation."
        return result
    train, test = pairs.iloc[:-10].copy(), pairs.iloc[-10:].copy()
    if 3 not in set(train.mood):
        result["message"] = "The earlier training period needs a Neutral (3) mood record to estimate reference-category effects."
        return result
    training_moods = set(train.mood.astype(int))
    supported = test.mood.astype(int).isin(training_moods)
    predictions = test[["diary_date", "target_date", "next_night_hours", "mood"]].copy()
    predictions["mood_seen_in_training"] = supported.to_numpy()
    metrics = []
    # One-hot is the preselected primary model. The numeric alternative is a
    # comparison, not a reason to choose a winner using the held-out results.
    for encoding in ["one_hot", "numeric"]:
        fitted = new_model(encoding).fit(train[FEATURES], train.next_night_hours)
        estimate = fitted.predict(test[FEATURES])
        predictions[encoding + "_prediction"] = estimate
        metrics.append({"model": encoding, "scored_nights": int(supported.sum()),
                        **score_predictions(test.loc[supported, "next_night_hours"], estimate[supported])})
    # Do not interpret the zero-coded effect of a mood absent from earlier training.
    predictions.loc[~supported, "one_hot_prediction"] = np.nan
    baseline = float(train.next_night_hours.mean())
    predictions["baseline_prediction"] = baseline
    metrics.append({"model": "training_mean", "scored_nights": int(supported.sum()),
                    **score_predictions(test.loc[supported, "next_night_hours"], np.full(int(supported.sum()), baseline))})

    # After evaluation, refit the primary model on EVERY completed pair.
    final = new_model("one_hot").fit(pairs[FEATURES], pairs.next_night_hours)
    names = final.named_steps["features"].get_feature_names_out().tolist()
    coefficients = final.named_steps["linear"].coef_.tolist()
    mood_counts = {level: int((pairs.mood == level).sum()) for level in MOOD_LABELS}
    labels = {"time_in_bed_hours": ("Last night's time in bed", 1, "+1 hour"),
              "doomscroll_minutes": ("Today's scrolling", 30, "+30 minutes"),
              "caffeine_cups": ("Today's caffeine", 1, "+1 cup"),
              "exercise_minutes": ("Today's exercise", 30, "+30 minutes")}
    coefficient_rows = []
    for name, coefficient in zip(names, coefficients):
        feature = name.split("__", 1)[1]
        if feature in labels:
            label, multiplier, change = labels[feature]
            status = "Estimated from all completed pairs"
        else:
            level = int(float(feature.split("_")[-1]))
            label, multiplier, change = f"Mood {level}: {MOOD_LABELS[level]}", 1, "Compared with Neutral"
            status = f"{mood_counts[level]} training examples"
            if mood_counts[level] == 0:
                coefficient = None
                status = "Not estimated: no examples of this mood"
        coefficient_rows.append({"feature": label, "input_change": change,
                                 "predicted_change_minutes": coefficient * multiplier * 60 if coefficient is not None else None,
                                 "status": status})
    latest = records.sort_values("diary_date").tail(1)
    mood_supported = mood_counts[int(latest.mood.iloc[0])] > 0
    latest_prediction = float(final.predict(latest[FEATURES])[0]) if mood_supported else None
    forecast = {"diary_date": latest.diary_date.iloc[0],
                "wake_date": (pd.Timestamp(latest.diary_date.iloc[0]) + pd.Timedelta(days=1)).date().isoformat(),
                "predicted_hours": latest_prediction,
                "mood_supported": mood_supported,
                "outside_diary_range": latest_prediction is not None and not 0 < latest_prediction <= 16}
    fit_info = {"encoding": "one_hot", "reference_mood": 3, "feature_names": names,
                "intercept_hours": float(final.named_steps["linear"].intercept_),
                "coefficients": dict(zip(names, coefficients)), "mood_counts": mood_counts,
                "completed_pairs": len(pairs), "input_start": pairs.diary_date.min(), "input_end": pairs.diary_date.max(),
                "evaluation_train_input_end": train.diary_date.max(),
                "evaluation_target_start": test.target_date.min(), "evaluation_target_end": test.target_date.max(),
                "evaluation_training_pairs": len(train), "evaluation_held_out_pairs": len(test),
                "evaluation_scored_pairs": int(supported.sum()), "dashboard_filters_used": False}
    result.update(available=True, message="Model ready", predictions=predictions, metrics=pd.DataFrame(metrics),
                  coefficients=pd.DataFrame(coefficient_rows), fit_info=fit_info, forecast=forecast)
    return result


def regression_chart(result):
    if not result["available"]:
        return empty_chart(result["message"])
    data = result["predictions"].dropna(subset=["one_hot_prediction"])
    if data.empty:
        return empty_chart("Held-out mood categories were absent from training; no supported comparison")
    observed, predicted = data.next_night_hours.tolist(), data.one_hot_prediction.tolist()
    low, high = min(observed + predicted) - 0.3, max(observed + predicted) + 0.3
    chart = go.Figure(go.Scatter(x=observed, y=predicted, mode="markers", name="Held-out nights",
                                marker=dict(size=10, color="#276b8e"), customdata=data.target_date.tolist(),
                                hovertemplate="Wake date %{customdata}<br>Observed %{x:.2f} h<br>Predicted %{y:.2f} h<extra></extra>"))
    chart.add_trace(go.Scatter(x=[low, high], y=[low, high], mode="lines", name="Perfect agreement",
                              line=dict(color="#bc7c52", dash="dash")))
    finish_chart(chart, "Next-night prediction: observed vs predicted", height=480)
    chart.update_xaxes(title_text="Observed following-night time in bed (hours)", range=[low, high])
    chart.update_yaxes(title_text="Predicted time in bed (hours)", range=[low, high])
    chart.update_layout(showlegend=True, legend=dict(orientation="h", y=-0.2), margin=dict(l=80, r=30, t=80, b=100))
    return chart


def export_model(result, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    result["pairs"].to_csv(destination / "model_pairs.csv", index=False)
    if not result["available"]:
        # Remove stale results in this model-only folder if too few pairs remain.
        for name in ["held_out_predictions.csv", "model_metrics.csv", "coefficients.csv", "model_info.json", "latest_prediction.json", "regression.png"]:
            (destination / name).unlink(missing_ok=True)
        (destination / "model_notes.txt").write_text(result["message"], encoding="utf-8")
        return
    for name, frame in [("held_out_predictions.csv", result["predictions"]), ("model_metrics.csv", result["metrics"]),
                        ("coefficients.csv", result["coefficients"])]:
        frame.to_csv(destination / name, index=False)
    for name, data in [("model_info.json", result["fit_info"]), ("latest_prediction.json", result["forecast"])]:
        (destination / name).write_text(json.dumps(data, indent=2, allow_nan=False), encoding="utf-8")
    info = result["fit_info"]
    text = (f"Full-diary next-night model | {result['stored_days']} diary days; {info['completed_pairs']} completed pairs.\n"
            f"Evaluation: {info['evaluation_training_pairs']} earlier pairs; 10 later pairs held out.\n"
            f"Held-out wake dates: {info['evaluation_target_start']} to {info['evaluation_target_end']}.\n"
            f"Scored nights: {info['evaluation_scored_pairs']}; unseen training mood categories are excluded from all metrics.\n\n"
            + result['metrics'].round(4).to_string(index=False)
            + "\n\nThe one-hot model is the preselected primary model. Numeric mood is a comparison only.\n"
              "The final primary model is refitted on all completed pairs; dashboard filters never select training rows.\n"
              "Plot points are held-out predictions from the earlier-only fit, not fitted values from the full-data model.\n"
              "Coefficient estimates describe associations, not causal effects. A missing mood level has no estimated effect.\n"
              "The bundled diary contains computer-generated demonstration records, not collected personal observations.\n")
    (destination / "model_notes.txt").write_text(text, encoding="utf-8")
    data = result["predictions"].dropna(subset=["one_hot_prediction"])
    fig, ax = plt.subplots(figsize=(9, 7), layout="constrained", facecolor="#f7f9fc")
    if len(data):
        ax.scatter(data.next_night_hours, data.one_hot_prediction, color="#276b8e", s=65, label="Held-out nights")
        low = min(data.next_night_hours.min(), data.one_hot_prediction.min()) - 0.3
        high = max(data.next_night_hours.max(), data.one_hot_prediction.max()) + 0.3
        ax.plot([low, high], [low, high], color="#bc7c52", linestyle="--", label="Perfect agreement")
        ax.set_xlim(low, high); ax.set_ylim(low, high)
    else:
        ax.text(.5, .5, "No supported held-out mood categories", transform=ax.transAxes, ha="center")
    ax.set_title("Next-night prediction", fontsize=20, fontweight="bold")
    ax.set_xlabel("Observed following-night time in bed (hours)", fontsize=12)
    ax.set_ylabel("Predicted time in bed (hours)", fontsize=12)
    ax.grid(color="#dce2e8");ax.set_axisbelow(True)
    if len(data):ax.legend()
    fig.supxlabel("Later held-out nights | Generated demonstration records", fontsize=10)
    fig.savefig(destination / "regression.png", dpi=220)
    plt.close(fig)


def main():
    with sqlite3.connect(f"file:{ROOT / 'output/sleep_diary.sqlite'}?mode=ro", uri=True) as connection:
        records = pd.read_sql_query("SELECT * FROM sleep_log ORDER BY diary_date", connection)
    result = run_model(records)
    export_model(result, ROOT / "output/model")
    print(result["metrics"].round(3).to_string(index=False) if result["available"] else result["message"])


if __name__ == "__main__":
    main()
