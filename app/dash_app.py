# =============================================================================
# app/dash_app.py — The AI Shift Dashboard
# =============================================================================
# "What measurably changed after generative AI went public in November 2022?"
#
# SIDEBAR FILTERS (apply live to all relevant plots):
#   - Date range slider       → Plots 1,2,3,4 (Google Trends / FRED)
#   - AI keyword selector     → Plots 1,2
#   - Show ChatGPT line       → All trend plots
#   - Show COVID shade        → All trend plots
#   - Role filter             → Plot 5 (employer demand)
#   - Survey year             → Plots 6,8 (Stack Overflow)
#
# TAB 1 — Information & Interest Shift
#   Plot 1: The Moment Everything Changed
#   Plot 2: Are People Still Googling?
#   Plot 3: Did People Stop Reading Docs?
#   Plot 4: Job Search Intent Shifted
#
# TAB 2 — Jobs, Skills & Economy
#   Plot 5: What Employers Now Want
#   Plot 6: Developer AI Adoption
#   Plot 7: The Salary Premium
#   Plot 8: The New Skill Stack
# =============================================================================

from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dcc, html

# ─────────────────────────────────────────────────────────────────────────────
# PATHS & DATA
# ─────────────────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent.parent / "data" / "processed"

mt   = pd.read_parquet(BASE / "master_timeline.parquet")
so   = pd.read_parquet(BASE / "stackoverflow_clean.parquet")
sk   = pd.read_parquet(BASE / "stackoverflow_skills_long.parquet")
li   = pd.read_parquet(BASE / "linkedin_clean.parquet")
bls  = pd.read_parquet(BASE / "bls_salary_role_summary.parquet")

mt["date"] = pd.to_datetime(mt["date"])

# ── Constants ─────────────────────────────────────────────────────────────────
CHATGPT_DATE = "2022-11-01"
MIN_DATE_IDX = 0   # 2020-01
MAX_DATE_IDX = len(mt) - 1  # 2026-06

AI_KEYWORDS = ["ChatGPT", "Gemini", "Claude AI", "LLM",
               "Generative AI", "Prompt Engineering", "LangChain",
               "OpenAI API", "Fine tuning LLM", "AI Assistant"]

PLATFORM_KEYWORDS = ["Stack Overflow", "GitHub", "Google Search"]

JOB_KEYWORDS = ["Data Analyst jobs", "Data Scientist jobs",
                "AI Engineer jobs", "Prompt Engineer jobs", "ML Engineer jobs"]

TRAD_KEYWORDS = ["SQL tutorial", "Excel tutorial", "Power BI", "Tableau"]

ALL_ROLES = [r for r in li["role_category"].unique() if r != "Other"]
ALL_ROLES_SORTED = sorted(ALL_ROLES)

C_BLUE   = "#2C5F8A"
C_RED    = "#C44E52"
C_GREEN  = "#55A868"
C_ORANGE = "#DD8452"
C_PURPLE = "#8172B2"
C_GRAY   = "#6b7280"

KW_COLORS = {
    "ChatGPT":           C_RED,
    "Gemini":            C_BLUE,
    "Claude AI":         C_PURPLE,
    "LLM":               C_GREEN,
    "Generative AI":     C_ORANGE,
    "Prompt Engineering":"#937860",
    "LangChain":         "#DA8BC3",
    "OpenAI API":        "#64B5CD",
    "Fine tuning LLM":   "#CCB974",
    "AI Assistant":      "#8C8C8C",
    "Stack Overflow":    C_ORANGE,
    "GitHub":            C_GREEN,
    "Google Search":     C_BLUE,
}

px.defaults.template = "plotly_white"

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
CARD = {
    "background": "white",
    "border": "1px solid #e5e7eb",
    "borderRadius": "8px",
    "padding": "4px",
    "boxShadow": "0 1px 4px rgba(0,0,0,0.06)",
}
GRID_2 = {
    "display": "grid",
    "gridTemplateColumns": "1fr 1fr",
    "gap": "14px",
    "padding": "14px",
}
H = 400


def base_layout(fig, title, height=H):
    fig.update_layout(
        title=dict(text=title, font=dict(size=12, color="#1a1a2e")),
        height=height,
        margin=dict(l=55, r=20, t=52, b=45),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, font=dict(size=10)),
        hovermode="x unified",
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    return fig


def slice_mt(date_range_idx):
    """Slice master_timeline by index range from the slider."""
    lo = mt.iloc[date_range_idx[0]]["date"]
    hi = mt.iloc[date_range_idx[1]]["date"]
    return mt[(mt["date"] >= lo) & (mt["date"] <= hi)].copy()


def add_chatgpt_line(fig, show=True):
    if not show:
        return fig
    fig.add_vline(x=CHATGPT_DATE, line_dash="dash",
                  line_color=C_RED, line_width=1.5, opacity=0.8)
    fig.add_annotation(
        x=CHATGPT_DATE, y=1, yref="paper",
        text="ChatGPT<br>Nov 2022",
        showarrow=False,
        font=dict(size=9, color=C_RED),
        bgcolor="rgba(255,255,255,0.85)",
        xanchor="left", yanchor="top", xshift=4,
    )
    return fig


def add_covid_shade(fig, show=True):
    if not show:
        return fig
    fig.add_vrect(
        x0="2020-03-01", x1="2021-12-01",
        fillcolor="gray", opacity=0.07,
        layer="below", line_width=0,
        annotation_text="COVID",
        annotation_position="top left",
        annotation_font=dict(size=9, color="gray"),
    )
    return fig


def date_label(idx):
    return mt.iloc[idx]["date"].strftime("%b %Y")


# ─────────────────────────────────────────────────────────────────────────────
# PLOT BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

def plot1_ai_surge(d, ai_kws, show_chatgpt, show_covid):
    fig = go.Figure()
    for kw in ai_kws:
        if kw not in d.columns:
            continue
        fig.add_trace(go.Scatter(
            x=d["date"], y=d[kw], name=kw, mode="lines",
            line=dict(color=KW_COLORS.get(kw, C_BLUE), width=2),
            hovertemplate=f"{kw}: %{{y:.0f}}<extra></extra>",
        ))
    add_covid_shade(fig, show_covid)
    add_chatgpt_line(fig, show_chatgpt)
    fig.update_xaxes(title="")
    fig.update_yaxes(title="Search Interest (0–100)", range=[0, 105])
    return base_layout(fig,
        "Plot 1 — The Moment Everything Changed: AI Search Interest Exploded After Nov 2022")


def plot2_platform_decline(d, ai_kws, show_chatgpt, show_covid):
    fig = go.Figure()
    # Platforms always shown
    for col, color in [("Stack Overflow", C_ORANGE),
                       ("GitHub", C_GREEN),
                       ("Google Search", C_BLUE)]:
        if col in d.columns:
            fig.add_trace(go.Scatter(
                x=d["date"], y=d[col], name=col, mode="lines",
                line=dict(color=color, width=2, dash="dot"),
                hovertemplate=f"{col}: %{{y:.0f}}<extra></extra>",
            ))
    # Selected AI keywords overlaid
    for kw in ai_kws:
        if kw not in d.columns:
            continue
        fig.add_trace(go.Scatter(
            x=d["date"], y=d[kw], name=kw, mode="lines",
            line=dict(color=KW_COLORS.get(kw, C_RED),
                      width=3 if kw == "ChatGPT" else 1.5),
            hovertemplate=f"{kw}: %{{y:.0f}}<extra></extra>",
        ))
    add_covid_shade(fig, show_covid)
    add_chatgpt_line(fig, show_chatgpt)
    fig.update_xaxes(title="")
    fig.update_yaxes(title="Search Interest (0–100)", range=[0, 105])
    return base_layout(fig,
        "Plot 2 — Are People Still Googling? Platforms (dotted) vs AI Tools")


def plot3_stackoverflow_decline(d, show_chatgpt, show_covid):
    fig = go.Figure()
    if "Stack Overflow" in d.columns:
        fig.add_trace(go.Scatter(
            x=d["date"], y=d["Stack Overflow"],
            name="Stack Overflow searches", mode="lines", fill="tozeroy",
            line=dict(color=C_ORANGE, width=2),
            fillcolor="rgba(221,132,82,0.12)",
            hovertemplate="Stack Overflow: %{y:.0f}<extra></extra>",
        ))
    if "ChatGPT" in d.columns:
        fig.add_trace(go.Scatter(
            x=d["date"], y=d["ChatGPT"],
            name="ChatGPT searches", mode="lines",
            line=dict(color=C_RED, width=2.5),
            hovertemplate="ChatGPT: %{y:.0f}<extra></extra>",
        ))
        # Dynamic crossover annotation
        if "Stack Overflow" in d.columns:
            cross = d[d["ChatGPT"] >= d["Stack Overflow"]]["date"].min()
            if pd.notna(cross):
                y_val = float(d.loc[d["date"] == cross, "ChatGPT"].values[0])
                fig.add_annotation(
                    x=str(cross)[:10], y=y_val,
                    text="ChatGPT overtakes<br>Stack Overflow",
                    showarrow=True, arrowhead=2,
                    font=dict(size=9, color=C_RED),
                    bgcolor="rgba(255,255,255,0.85)",
                    ax=45, ay=-35,
                )
    add_covid_shade(fig, show_covid)
    add_chatgpt_line(fig, show_chatgpt)
    fig.update_xaxes(title="")
    fig.update_yaxes(title="Search Interest (0–100)", range=[0, 105])
    return base_layout(fig,
        "Plot 3 — Did People Stop Reading Docs? Stack Overflow vs ChatGPT")


def plot4_job_search(d, show_chatgpt, show_covid):
    styles = {
        "Data Analyst jobs":    (C_BLUE,   "dot",   1.5),
        "Data Scientist jobs":  (C_GREEN,  "dot",   1.5),
        "AI Engineer jobs":     (C_RED,    "solid", 2.5),
        "Prompt Engineer jobs": (C_PURPLE, "solid", 2.5),
        "ML Engineer jobs":     (C_ORANGE, "dot",   1.5),
    }
    fig = go.Figure()
    for col, (color, dash, width) in styles.items():
        if col not in d.columns:
            continue
        fig.add_trace(go.Scatter(
            x=d["date"], y=d[col],
            name=col.replace(" jobs", ""),
            mode="lines",
            line=dict(color=color, width=width, dash=dash),
            hovertemplate=f"{col}: %{{y:.0f}}<extra></extra>",
        ))
    add_covid_shade(fig, show_covid)
    add_chatgpt_line(fig, show_chatgpt)
    fig.update_xaxes(title="")
    fig.update_yaxes(title="Search Interest (0–100)", range=[0, 105])
    return base_layout(fig,
        "Plot 4 — Job Search Intent Shifted: AI Roles Surged After Nov 2022")


def plot5_employer_demand(selected_roles):
    roles = selected_roles if selected_roles else ALL_ROLES_SORTED
    role_data = (
        li[li["role_category"].isin(roles)]
        .groupby("role_category")
        .agg(
            mean_ai_score=("ai_skill_score", "mean"),
            pct_ai=("ai_skill_score", lambda x: (x > 0).mean() * 100),
            count=("job_id", "count"),
        )
        .reset_index()
        .sort_values("mean_ai_score", ascending=True)
    )
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=role_data["role_category"],
        x=role_data["mean_ai_score"],
        orientation="h",
        marker=dict(
            color=role_data["mean_ai_score"],
            colorscale="Blues", showscale=False,
        ),
        text=role_data["mean_ai_score"].round(1),
        textposition="outside",
        customdata=np.stack([role_data["pct_ai"].round(1),
                             role_data["count"]], axis=-1),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Avg AI score: %{x:.1f}<br>"
            "% postings with AI: %{customdata[0]}%<br>"
            "Total postings: %{customdata[1]:,}<extra></extra>"
        ),
    ))
    fig.update_xaxes(title="Avg AI Keyword Score in Job Description")
    fig.update_yaxes(title="")
    fig.update_layout(hovermode="y unified")
    return base_layout(fig,
        "Plot 5 — What Employers Now Want: AI Keyword Density by Role (LinkedIn, Apr 2024)")


def plot6_ai_adoption(survey_years):
    def simplify(val):
        if pd.isna(val): return None
        v = str(val).lower()
        if "daily" in v or "weekly" in v or "monthly" in v or v == "yes":
            return "Yes — active user"
        if "plan to" in v: return "Not yet but planning"
        if "don't plan" in v: return "No & not planning"
        return None

    years = [int(y) for y in survey_years] if survey_years else [2023, 2025]
    so_f = so[so["survey_year"].isin(years)].copy()
    so_f["ai_simplified"] = so_f["ai_select"].apply(simplify)
    grp = (
        so_f[so_f["ai_simplified"].notna()]
        .groupby(["survey_year", "ai_simplified"])
        .size().reset_index(name="count")
    )
    grp["survey_year"] = grp["survey_year"].astype(str)
    total = grp.groupby("survey_year")["count"].transform("sum")
    grp["pct"] = (grp["count"] / total * 100).round(1)

    cat_order  = ["Yes — active user", "Not yet but planning", "No & not planning"]
    cat_colors = [C_GREEN, C_ORANGE, C_GRAY]

    fig = go.Figure()
    for cat, color in zip(cat_order, cat_colors):
        d = grp[grp["ai_simplified"] == cat]
        fig.add_trace(go.Bar(
            x=d["survey_year"], y=d["pct"], name=cat,
            marker_color=color,
            text=d["pct"].astype(str) + "%",
            textposition="inside",
            hovertemplate=f"{cat}: %{{y:.1f}}%<extra></extra>",
        ))
    fig.update_layout(barmode="stack", hovermode="x unified")
    fig.update_xaxes(title="Survey Year")
    fig.update_yaxes(title="% of Respondents", range=[0, 105])
    return base_layout(fig,
        "Plot 6 — Developer AI Adoption: Active Usage Rose from 43.8% (2023) to 53.8% (2025)")


def plot7_salary():
    pre  = bls[bls["year"] == 2020][["role_category", "role_median_salary"]].rename(
               columns={"role_median_salary": "sal_2020"})
    post = bls[bls["year"] == 2022][["role_category", "role_median_salary"]].rename(
               columns={"role_median_salary": "sal_2022"})
    merged = pre.merge(post, on="role_category")
    merged = merged[merged["role_category"] != "Other"].copy()
    merged["change_pct"] = ((merged["sal_2022"] - merged["sal_2020"])
                             / merged["sal_2020"] * 100).round(1)
    merged = merged.sort_values("sal_2022", ascending=True)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=merged["role_category"], x=merged["sal_2020"] / 1000,
        name="2020 baseline", orientation="h",
        marker_color=C_BLUE, opacity=0.6,
        hovertemplate="2020 median: $%{x:.0f}K<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        y=merged["role_category"], x=merged["sal_2022"] / 1000,
        name="2022 (pre-ChatGPT peak)", orientation="h",
        marker_color=C_RED, opacity=0.85,
        hovertemplate="2022 median: $%{x:.0f}K<extra></extra>",
    ))
    for _, row in merged.iterrows():
        sign = "+" if row["change_pct"] > 0 else ""
        color = C_GREEN if row["change_pct"] > 0 else C_RED
        fig.add_annotation(
            y=row["role_category"],
            x=max(row["sal_2020"], row["sal_2022"]) / 1000 + 3,
            text=f"{sign}{row['change_pct']:.0f}%",
            showarrow=False,
            font=dict(size=9, color=color),
            xanchor="left",
        )
    fig.update_layout(barmode="overlay")
    fig.update_xaxes(title="Median Salary ($K)")
    fig.update_yaxes(title="")
    return base_layout(fig,
        "Plot 7 — The Salary Premium: 2020 vs 2022 Median Salary by Role (BLS)")


def plot8_skill_stack(survey_years):
    years = [int(y) for y in survey_years] if survey_years else [2023, 2025]
    lang = sk[(sk["skill_type"] == "language_used") &
              (sk["survey_year"].isin(years))]
    top15 = (lang.groupby("value")["ResponseId"].count()
                  .sort_values(ascending=False).head(15).index.tolist())
    lang_top = lang[lang["value"].isin(top15)]
    pivot = (lang_top.groupby(["value", "survey_year"]).size()
                      .reset_index(name="count"))
    totals = so[so["survey_year"].isin(years)].groupby(
        "survey_year")["ResponseId"].count().to_dict()
    pivot["pct"] = pivot.apply(
        lambda r: r["count"] / totals.get(r["survey_year"], 1) * 100, axis=1
    ).round(1)
    pivot["survey_year"] = pivot["survey_year"].astype(str)

    color_map = {"2023": C_BLUE, "2025": C_RED}
    fig = px.bar(
        pivot, x="pct", y="value", color="survey_year",
        barmode="group", orientation="h",
        color_discrete_map=color_map,
        labels={"pct": "% of Respondents", "value": "Language", "survey_year": "Year"},
        text=pivot["pct"].astype(str) + "%",
    )
    fig.update_traces(textposition="outside", textfont_size=9)
    fig.update_xaxes(title="% of Survey Respondents")
    fig.update_yaxes(title="", categoryorder="total ascending")
    return base_layout(fig,
        "Plot 8 — The New Skill Stack: Top 15 Languages Used (2023 vs 2025)", height=500)


# ─────────────────────────────────────────────────────────────────────────────
# STAT CARDS
# ─────────────────────────────────────────────────────────────────────────────
def stat_card(value, label, color=C_BLUE):
    return html.Div([
        html.Div(value, style={"fontSize": "20px", "fontWeight": "700",
                                "color": color, "lineHeight": "1.2"}),
        html.Div(label, style={"fontSize": "10px", "color": C_GRAY,
                                "marginTop": "3px", "lineHeight": "1.3"}),
    ], style={
        "background": "white",
        "border": "1px solid #e5e7eb",
        "borderLeft": f"3px solid {color}",
        "borderRadius": "6px",
        "padding": "10px 14px",
        "flex": "1", "minWidth": "150px",
    })


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
sidebar = html.Div([
    html.H3("Filters", style={"marginTop": 0, "fontSize": "15px",
                               "color": "#1a1a2e", "marginBottom": "16px"}),

    # ── Date range ────────────────────────────────────────────────────────────
    html.Label("Date range", style={"fontSize": "12px", "fontWeight": "600",
                                     "color": "#374151"}),
    dcc.RangeSlider(
        id="date-sl",
        min=0, max=MAX_DATE_IDX, step=1,
        value=[0, MAX_DATE_IDX],
        allowCross=False,
        tooltip={"always_visible": False, "placement": "bottom"},
        marks={
            0:  {"label": "Jan 2020", "style": {"fontSize": "9px"}},
            24: {"label": "Jan 2022", "style": {"fontSize": "9px"}},
            34: {"label": "Nov 2022", "style": {"fontSize": "9px",
                                                  "color": C_RED}},
            48: {"label": "Jan 2024", "style": {"fontSize": "9px"}},
            77: {"label": "Jun 2026", "style": {"fontSize": "9px"}},
        },
    ),
    html.Div(id="date-label",
             style={"fontSize": "11px", "color": "#888", "marginBottom": "14px"}),

    # ── AI keywords ───────────────────────────────────────────────────────────
    html.Label("AI keywords  (Plots 1 & 2)",
               style={"fontSize": "12px", "fontWeight": "600", "color": "#374151"}),
    dcc.Dropdown(
        id="kw-dd",
        options=[{"label": k, "value": k} for k in AI_KEYWORDS],
        value=["ChatGPT", "LLM", "Generative AI", "Prompt Engineering"],
        multi=True, placeholder="Select keywords…",
        style={"fontSize": "12px"},
    ),

    html.Div(style={"marginTop": "14px"}),

    # ── Toggles ───────────────────────────────────────────────────────────────
    html.Label("Display options",
               style={"fontSize": "12px", "fontWeight": "600",
                      "color": "#374151", "marginBottom": "6px",
                      "display": "block"}),
    dcc.Checklist(
        id="toggles",
        options=[
            {"label": " Show ChatGPT launch line", "value": "chatgpt"},
            {"label": " Show COVID period shade",  "value": "covid"},
        ],
        value=["chatgpt", "covid"],
        labelStyle={"display": "block", "fontSize": "12px",
                    "color": "#4b5563", "marginBottom": "4px"},
    ),

    html.Hr(style={"margin": "14px 0"}),

    # ── Role filter ───────────────────────────────────────────────────────────
    html.Label("Job roles  (Plot 5)",
               style={"fontSize": "12px", "fontWeight": "600", "color": "#374151"}),
    dcc.Dropdown(
        id="role-dd",
        options=[{"label": r, "value": r} for r in ALL_ROLES_SORTED],
        value=[], multi=True, placeholder="All roles",
        style={"fontSize": "12px"},
    ),

    html.Div(style={"marginTop": "14px"}),

    # ── Survey year ───────────────────────────────────────────────────────────
    html.Label("Survey years  (Plots 6 & 8)",
               style={"fontSize": "12px", "fontWeight": "600", "color": "#374151"}),
    dcc.Checklist(
        id="year-check",
        options=[{"label": " 2023", "value": "2023"},
                 {"label": " 2025", "value": "2025"}],
        value=["2023", "2025"],
        labelStyle={"display": "inline-block", "marginRight": "14px",
                    "fontSize": "12px", "color": "#4b5563"},
    ),

    html.Hr(style={"margin": "14px 0"}),

    # ── Summary ───────────────────────────────────────────────────────────────
    html.Div(id="filter-summary",
             style={"fontSize": "11px", "color": "#888", "lineHeight": "1.6"}),

], style={
    "width": "260px", "flex": "0 0 260px",
    "padding": "16px 14px",
    "borderRight": "1px solid #eee",
    "background": "#fafafa",
    "overflowY": "auto",
    "position": "sticky", "top": 0,
    "maxHeight": "100vh",
})


# ─────────────────────────────────────────────────────────────────────────────
# TAB CONTENT
# ─────────────────────────────────────────────────────────────────────────────
tab1_content = html.Div([
    html.Div([
        html.Div([dcc.Graph(id="p1", config={"displayModeBar": False})], style=CARD),
        html.Div([dcc.Graph(id="p2", config={"displayModeBar": False})], style=CARD),
    ], style=GRID_2),
    html.Div([
        html.Div([dcc.Graph(id="p3", config={"displayModeBar": False})], style=CARD),
        html.Div([dcc.Graph(id="p4", config={"displayModeBar": False})], style=CARD),
    ], style=GRID_2),
])

tab2_content = html.Div([
    html.Div([
        html.Div([dcc.Graph(id="p5", config={"displayModeBar": False})], style=CARD),
        html.Div([dcc.Graph(id="p6", config={"displayModeBar": False})], style=CARD),
    ], style=GRID_2),
    html.Div([
        html.Div([dcc.Graph(id="p7", config={"displayModeBar": False})], style=CARD),
        html.Div([dcc.Graph(id="p8", config={"displayModeBar": False})],
                 style={**CARD, "gridColumn": "1 / -1"}),
    ], style=GRID_2),
])


# ─────────────────────────────────────────────────────────────────────────────
# APP LAYOUT
# ─────────────────────────────────────────────────────────────────────────────
app = Dash(__name__)
app.title = "The AI Shift"

stat_row = html.Div([
    stat_card("Nov 2022",   "ChatGPT public release",                     C_RED),
    stat_card("43%→54%",   "Developer AI adoption 2023→2025",            C_GREEN),
    stat_card("6% of jobs", "LinkedIn postings mention AI  (Apr 2024)",   C_BLUE),
    stat_card("~0→100",    "ChatGPT search interest surge",              C_PURPLE),
    stat_card("5 sources", "GT · FRED · SO · LinkedIn · BLS",            C_ORANGE),
], style={"display": "flex", "gap": "10px",
          "padding": "10px 14px 0", "flexWrap": "wrap"})

app.layout = html.Div([

    # ── Header ───────────────────────────────────────────────────────────────
    html.Div([
        html.H1("The AI Shift",
                style={"margin": "0 0 3px", "fontSize": "22px", "color": "#1a1a2e"}),
        html.P(
            "What measurably changed after generative AI went public in November 2022 — "
            "in how people find information, what skills employers demand, and how developers work.",
            style={"margin": 0, "fontSize": "12px", "color": C_GRAY}
        ),
    ], style={"padding": "14px 20px 12px",
              "borderBottom": f"2px solid {C_BLUE}",
              "background": "white"}),

    # ── Stat row ─────────────────────────────────────────────────────────────
    stat_row,

    # ── Body: sidebar + tabs ─────────────────────────────────────────────────
    html.Div([
        sidebar,
        html.Div([
            dcc.Tabs(
                id="tabs", value="t1",
                style={"margin": "0 14px"},
                children=[
                    dcc.Tab(
                        label="📈  Information & Interest Shift", value="t1",
                        style={"fontSize": "13px", "padding": "8px 16px"},
                        selected_style={"fontWeight": "700", "fontSize": "13px",
                                        "padding": "8px 16px",
                                        "borderTop": f"3px solid {C_BLUE}"},
                    ),
                    dcc.Tab(
                        label="💼  Jobs, Skills & Economy", value="t2",
                        style={"fontSize": "13px", "padding": "8px 16px"},
                        selected_style={"fontWeight": "700", "fontSize": "13px",
                                        "padding": "8px 16px",
                                        "borderTop": f"3px solid {C_BLUE}"},
                    ),
                ],
            ),
            html.Div(id="tab-content"),
        ], style={"flex": "1", "minWidth": 0, "overflowX": "auto"}),
    ], style={"display": "flex", "alignItems": "flex-start",
              "marginTop": "10px"}),

    # ── Footer ───────────────────────────────────────────────────────────────
    html.Div(
        "Data: Google Trends (Jan 2020–Jun 2026) · FRED (Jan 2018–May 2026) · "
        "Stack Overflow Survey (2023 & 2025 only, no other years) · "
        "LinkedIn Job Postings (Apr 2024 snapshot only) · BLS Salary (2020–2022). "
        "Google Trends values are batch-normalised 0–100 — not comparable across keyword groups.",
        style={"padding": "8px 16px", "fontSize": "10px", "color": "#aaa",
               "borderTop": "1px solid #eee", "background": "#fafafa",
               "marginTop": "8px"}
    ),

], style={
    "fontFamily": "Arial, sans-serif",
    "maxWidth": "1600px",
    "margin": "0 auto",
    "background": "#f9fafb",
    "minHeight": "100vh",
})


# ─────────────────────────────────────────────────────────────────────────────
# CALLBACKS
# ─────────────────────────────────────────────────────────────────────────────

@app.callback(Output("tab-content", "children"), Input("tabs", "value"))
def render_tab(tab):
    return tab1_content if tab == "t1" else tab2_content


@app.callback(
    Output("date-label",     "children"),
    Output("filter-summary", "children"),
    Input("date-sl",   "value"),
    Input("kw-dd",     "value"),
    Input("role-dd",   "value"),
    Input("year-check","value"),
    Input("toggles",   "value"),
)
def update_labels(date_range, kws, roles, years, toggles):
    lo = date_label(date_range[0])
    hi = date_label(date_range[1])
    d  = slice_mt(date_range)
    n_months = len(d)
    role_str = ", ".join(roles) if roles else "All roles"
    year_str = " & ".join(years) if years else "None"
    return (
        f"{lo} → {hi}",
        f"📅 {n_months} months  ({lo} – {hi})\n"
        f"🔑 {len(kws) if kws else 0} keywords selected\n"
        f"💼 Roles: {role_str}\n"
        f"📊 SO years: {year_str}"
    )


@app.callback(
    Output("p1", "figure"),
    Output("p2", "figure"),
    Output("p3", "figure"),
    Output("p4", "figure"),
    Input("date-sl",  "value"),
    Input("kw-dd",    "value"),
    Input("toggles",  "value"),
)
def update_tab1(date_range, kws, toggles):
    d = slice_mt(date_range)
    show_chatgpt = "chatgpt" in (toggles or [])
    show_covid   = "covid"   in (toggles or [])
    kws = kws or ["ChatGPT"]
    return (
        plot1_ai_surge(d, kws, show_chatgpt, show_covid),
        plot2_platform_decline(d, kws, show_chatgpt, show_covid),
        plot3_stackoverflow_decline(d, show_chatgpt, show_covid),
        plot4_job_search(d, show_chatgpt, show_covid),
    )


@app.callback(
    Output("p5", "figure"),
    Output("p6", "figure"),
    Output("p7", "figure"),
    Output("p8", "figure"),
    Input("role-dd",    "value"),
    Input("year-check", "value"),
)
def update_tab2(roles, years):
    return (
        plot5_employer_demand(roles),
        plot6_ai_adoption(years),
        plot7_salary(),
        plot8_skill_stack(years),
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=False)