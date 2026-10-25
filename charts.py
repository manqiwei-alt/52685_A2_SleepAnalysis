# Five dashboard views, with separate axes for hours, ratings, minutes and cups.
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

HABITS = {"doomscroll_minutes": "Scrolling (minutes)",
          "caffeine_cups": "Caffeine (cups)", "exercise_minutes": "Exercise (minutes)"}
WEEKLY_FIELDS = {"doomscroll_minutes": "mean_scrolling_minutes",
                 "caffeine_cups": "mean_caffeine_cups",
                 "exercise_minutes": "mean_exercise_minutes"}
COLOURS = {"Poor": "#ca765a", "Neutral": "#b59b52", "Good": "#3f927f"}
HABIT_COLOURS = {"doomscroll_minutes": "#6a72a5", "caffeine_cups": "#b08043", "exercise_minutes": "#3f927f"}


def finish_chart(chart, title, height=370):
    # Common visual settings; each trace supplies ordinary lists, never binary arrays.
    chart.update_layout(template="plotly_white", title=dict(text=f"<b>{title}</b>", font=dict(size=20)), height=height,
                        margin=dict(l=65, r=30, t=75, b=60),
                        font=dict(family="Arial", size=12), 
                        paper_bgcolor="white", plot_bgcolor="white", showlegend=False)
    chart.update_xaxes(title_font=dict(size=12), tickfont=dict(size=11))
    chart.update_yaxes(title_font=dict(size=12), tickfont=dict(size=11))
    # Subplot headings have their own size between the main title and axis labels.
    for annotation in chart.layout.annotations:
        if annotation.text in HABITS.values() or annotation.text == "Last night’s time in bed (hours)":
            annotation.text = f"<b>{annotation.text}</b>"
            annotation.font.size = 15
    return chart


def empty_chart(message):
    chart = go.Figure()
    chart.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
    chart.update_xaxes(visible=False)
    chart.update_yaxes(visible=False)
    return finish_chart(chart, "")


def night_chart(frame):
    chart = go.Figure(go.Scatter(x=frame.diary_date.tolist(), y=frame.time_in_bed_hours.tolist(),
                                mode="lines+markers", line=dict(color="#276b8e", width=3),
                                hovertemplate="%{x}<br>%{y:.2f} hours<extra></extra>"))
    chart.update_xaxes(title="Diary date", type="date", tickformat="%d %b", nticks=7)
    chart.update_yaxes(title="Hours", rangemode="tozero")
    return finish_chart(chart, "Last night’s time in bed")


def ratings_chart(frame):
    chart = go.Figure()
    for column, label, colour in [("sleep_quality", "Sleep rating", "#276b8e"), ("mood", "Morning mood", "#bc7c52")]:
        chart.add_trace(go.Scatter(x=frame.diary_date.tolist(), y=frame[column].tolist(),
                                  name=label, mode="lines+markers", line=dict(color=colour),
                                  hovertemplate="%{x}<br>%{y:.0f}/5<extra>%{fullData.name}</extra>"))
    chart.update_xaxes(title="Diary date", type="date", tickformat="%d %b", nticks=7)
    chart.update_yaxes(title="Self-reported rating", range=[0.7, 5.3], dtick=1)
    finish_chart(chart, "Sleep rating and mood")
    chart.update_layout(showlegend=True, legend=dict(orientation="h", y=1.13, x=0),
                        height=430, margin=dict(l=65, r=30, t=85, b=125))
    chart.add_annotation(text="<b>Mood:</b> 1 Very low · 2 Low · 3 Neutral<br>4 Good · 5 Very good",
                         x=0, y=-0.4, xref="paper", yref="paper", xanchor="left",
                         showarrow=False, align="left", font=dict(size=12))
    return chart


def daily_habits_chart(frame, habits):
    if not habits:
        return empty_chart("Choose one or more habits above")
    # Separate rows prevent cups and minutes from being compared on the same scale.
    chart = make_subplots(rows=len(habits), cols=1, shared_xaxes=True,
                          subplot_titles=[HABITS[name] for name in habits], vertical_spacing=0.13)
    for row, name in enumerate(habits, 1):
        chart.add_trace(go.Bar(x=frame.diary_date.tolist(), y=frame[name].tolist(),
                              marker_color=HABIT_COLOURS[name], name=HABITS[name],
                              hovertemplate="%{x}<br>%{y}<extra>%{fullData.name}</extra>"), row=row, col=1)
        chart.update_yaxes(title_text="Cups" if name == "caffeine_cups" else "Minutes",
                           rangemode="tozero", row=row, col=1)
    chart.update_xaxes(type="date", tickformat="%d %b", nticks=8)
    chart.update_xaxes(title_text="Diary date · habits before the upcoming sleep", row=len(habits), col=1)
    return finish_chart(chart, "Daily habits", max(370, 210 * len(habits) + 100))


def weekly_chart(weekly, habits):
    measures = [("mean_time_in_bed_hours", "Last night’s time in bed (hours)", "#276b8e")]
    measures += [(WEEKLY_FIELDS[name], HABITS[name], HABIT_COLOURS[name]) for name in habits]
    chart = make_subplots(rows=len(measures), cols=1, shared_xaxes=True,
                          subplot_titles=[label for _, label, _ in measures], vertical_spacing=0.09)
    for row, (column, label, colour) in enumerate(measures, 1):
        values = weekly[column].tolist()
        labels = [f"{value:.2f} · n={int(n)}" for value, n in zip(values, weekly.nights)]
        chart.add_trace(go.Bar(x=weekly.index.tolist(), y=values, text=labels, textposition="outside",
                              cliponaxis=False, marker_color=colour, name=label,
                              hovertemplate="Week of %{x}<br>%{text}<extra>%{fullData.name}</extra>"), row=row, col=1)
        chart.update_yaxes(range=[0, max(1, max(values) * 1.4)], row=row, col=1)
    chart.update_xaxes(type="category")
    chart.update_xaxes(title_text="Week starting Monday · only selected recorded nights", row=len(measures), col=1)
    return finish_chart(chart, "Calendar-week averages", max(370, 200 * len(measures) + 100))


def rating_groups_chart(frame, habits):
    if not habits:
        return empty_chart("Choose one or more habits above")
    chart = make_subplots(rows=len(habits), cols=1, shared_xaxes=True,
                          subplot_titles=[HABITS[name] for name in habits], vertical_spacing=0.13)
    for row, name in enumerate(habits, 1):
        grouped = frame.groupby("quality_group")[name].agg(mean="mean", nights="size")
        grouped = grouped.reindex(["Poor", "Neutral", "Good"]).dropna(subset=["mean"])
        labels = [f"{value:.1f} · n={int(n)}" for value, n in zip(grouped["mean"], grouped.nights)]
        chart.add_trace(go.Bar(x=grouped.index.tolist(), y=grouped["mean"].tolist(), text=labels,
                              marker_color=[COLOURS[group] for group in grouped.index],
                              textposition="outside", cliponaxis=False, name=HABITS[name],
                              hovertemplate="%{x}<br>%{text}<extra>%{fullData.name}</extra>"), row=row, col=1)
        chart.update_yaxes(range=[0, max(1, float(grouped["mean"].max()) * 1.4)], row=row, col=1)
    chart.update_xaxes(title_text="Previous night’s rating · today’s habits", row=len(habits), col=1)
    return finish_chart(chart, "Today’s habits by morning sleep rating", max(370, 210 * len(habits) + 100))
