import dash
from dash import dcc, html, Input, Output, State, ctx
import dash_bootstrap_components as dbc
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

CODEFORCES_API = "https://codeforces.com/api"
APP_TITLE = "Codeforces Dashboard"

def cf_user(handle: str):
    try:
        r = requests.get(f"{CODEFORCES_API}/user.info", params={"handles": handle}, timeout=10)
        j = r.json()
        if j.get("status") != "OK":
            return None
        return j["result"][0]
    except Exception:
        return None

def cf_submissions(handle: str, count: int = 800):
    try:
        r = requests.get(f"{CODEFORCES_API}/user.status", params={"handle": handle, "from": 1, "count": count}, timeout=12)
        j = r.json()
        if j.get("status") != "OK":
            return pd.DataFrame()
        rows = []
        for s in j["result"]:
            rows.append({
                "id": s.get("id"),
                "contestId": s.get("contestId"),
                "problem_name": s.get("problem", {}).get("name"),
                "problem_rating": s.get("problem", {}).get("rating"),
                "tags": s.get("problem", {}).get("tags", []),
                "verdict": s.get("verdict"),
                "time": datetime.fromtimestamp(s.get("creationTimeSeconds")) if s.get("creationTimeSeconds") else None,
                "index": s.get("problem", {}).get("index"),
                "url": f"https://codeforces.com/problemset/problem/{s.get('contestId')}/{s.get('problem', {}).get('index')}"
            })
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()

def cf_rating_history(handle: str):
    try:
        r = requests.get(f"{CODEFORCES_API}/user.rating", params={"handle": handle}, timeout=12)
        j = r.json()
        if j.get("status") != "OK":
            return pd.DataFrame()
        df = pd.DataFrame(j["result"])
        if not df.empty:
            df["ratingUpdateTimeSeconds"] = pd.to_datetime(df["ratingUpdateTimeSeconds"], unit="s")
        return df
    except Exception:
        return pd.DataFrame()

def cf_problemset_df():
    try:
        r = requests.get(f"{CODEFORCES_API}/problemset.problems", timeout=15)
        j = r.json()
        if j.get("status") != "OK":
            return pd.DataFrame()
        problems = j["result"]["problems"]
        df = pd.DataFrame(problems)
        if not df.empty:
            df["link"] = df.apply(lambda r: f"https://codeforces.com/problemset/problem/{r.get('contestId')}/{r.get('index')}" if r.get("contestId") and r.get("index") else "", axis=1)
        return df
    except Exception:
        return pd.DataFrame()

CF_RANK_COLORS = {
    "newbie": "#8a8a8a",
    "pupil": "#2ecc71",
    "specialist": "#03a89e",
    "expert": "#1f77b4",
    "candidate master": "#9b59b6",
    "master": "#e67e22",
    "international master": "#e67e22",
    "grandmaster": "#e74c3c",
    "international grandmaster": "#c0392b",
    "legendary grandmaster": "#900c3f",
}
def rank_color(rank):
    if not rank:
        return "#888888"
    return CF_RANK_COLORS.get(rank.lower(), "#999999")

def compute_streaks(subs):
    if subs is None or subs.empty:
        return {"current":0, "longest":0}
    ok_dates = sorted(set(subs[subs["verdict"]=="OK"]["time"].dt.date.tolist()))
    if not ok_dates:
        return {"current":0, "longest":0}
    longest = 1
    cur = 1
    for i in range(1, len(ok_dates)):
        if (ok_dates[i] - ok_dates[i-1]).days == 1:
            cur += 1
            longest = max(longest, cur)
        else:
            cur = 1
    streak = 0
    d = datetime.now().date()
    while d in ok_dates:
        streak += 1
        d = d - timedelta(days=1)
    return {"current": streak, "longest": longest}

def build_rating_figure(rating_hist, color="#00d4ff"):
    if rating_hist is None or rating_hist.empty:
        fig = go.Figure()
        fig.add_annotation(text="No rating history", showarrow=False)
        return fig
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=rating_hist["ratingUpdateTimeSeconds"],
        y=rating_hist["newRating"],
        mode="lines+markers",
        line=dict(color=color, width=3),
        marker=dict(size=6, color=color),
        hovertemplate="%{x|%Y-%m-%d} — %{y}<extra></extra>"
    ))
    bands = [
        (0,1199,"#888888"), (1200,1399,"#2ecc71"), (1400,1599,"#03a89e"),
        (1600,1899,"#1f77b4"), (1900,2099,"#9b59b6"), (2100,2299,"#e67e22"),
        (2300,3500,"#e74c3c")
    ]
    for lo, hi, col in bands:
        fig.add_hrect(y0=lo, y1=hi, fillcolor=col, opacity=0.06, line_width=0)
    fig.update_layout(margin=dict(l=20,r=20,t=30,b=30), height=360, template="plotly_dark", hovermode="x unified")
    return fig

def build_heatmap(subs, days=120):
    if subs is None or subs.empty:
        return go.Figure()
    end = datetime.now().date()
    start = end - timedelta(days=days)
    subs["date"] = subs["time"].dt.date
    all_dates = pd.date_range(start, end).date
    counts = subs.groupby("date").size().reindex(all_dates, fill_value=0)
    dates = list(counts.index)
    heat = pd.DataFrame({"date": dates, "count": counts.values})
    heat["dow"] = heat["date"].apply(lambda d: d.weekday())
    heat["w"] = heat["date"].apply(lambda d: (d - start).days // 7)
    pivot = heat.pivot_table(index="dow", columns="w", values="count", fill_value=0).reindex(index=[0,1,2,3,4,5,6])
    fig = go.Figure(data=go.Heatmap(z=pivot.values, x=pivot.columns.astype(str), y=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"], colorscale="greens"))
    fig.update_layout(height=300, margin=dict(l=30,r=10,t=30,b=30), template="plotly_dark")
    return fig

def analyze_weak_tags(subs, min_attempts=3):
    if subs is None or subs.empty:
        return []
    tag_rows = []
    for _, row in subs.iterrows():
        tags = row["tags"] or []
        for t in tags:
            tag_rows.append((t, row["verdict"] == "OK"))
    df = pd.DataFrame(tag_rows, columns=["tag","solved"])
    counts = df.groupby("tag").agg(total=("solved","size"), solved=("solved","sum")).reset_index()
    counts["success_rate"] = counts["solved"] / counts["total"]
    counts = counts[counts["total"] >= min_attempts].sort_values("success_rate")
    return counts.head(6).to_dict("records")

def recommend_for_tag(problem_df, tag, n=6, user_rating=None):
    if problem_df is None or problem_df.empty:
        return []
    cand = problem_df[problem_df["tags"].apply(lambda ts: (isinstance(ts, list) and tag in ts) or (isinstance(ts, str) and tag in ts))]
    if cand.empty:
        return []
    if user_rating:
        cand = cand.assign(diff=abs(cand["rating"].fillna(1500) - user_rating)).sort_values("diff").head(n)
    else:
        cand = cand.sample(min(n, len(cand)), random_state=42)
    recs = []
    for _, r in cand.head(n).iterrows():
        recs.append({"name": r.get("name") or r.get("title") or "Unnamed", "rating": r.get("rating", "N/A"), "link": r.get("link","")})
    return recs

external_stylesheets = [dbc.icons.FONT_AWESOME,
                        "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap"]
app = dash.Dash(__name__, external_stylesheets=external_stylesheets, suppress_callback_exceptions=True)
app.title = APP_TITLE

custom_css = """
:root { --accent1: #667eea; --accent2: #764ba2; --card-radius: 14px; font-family: 'Inter', sans-serif; }
body.light { --glass-bg: rgba(0,0,0,0.02); background: #f8f9fa; color: #222; }
body.dark { --glass-bg: rgba(255,255,255,0.04); background: #121212; color: #eee; }
.profile-glow { border-radius: var(--card-radius); padding: 12px; background: var(--glass-bg); border: 1px solid rgba(255,255,255,0.04); box-shadow: 0 8px 30px rgba(102, 126, 234, 0.08); transition: transform .18s ease; }
.profile-glow:hover { transform: translateY(-6px); box-shadow: 0 20px 50px rgba(102, 126, 234, 0.14); }
.glass-card { background: var(--glass-bg); border-radius: var(--card-radius); padding: 12px; border:1px solid rgba(255,255,255,0.03); transition: all .18s ease; }
.glass-card:hover{ transform: translateY(-6px); box-shadow: 0 14px 40px rgba(0,0,0,0.5); }
.weak-tag { margin-right:6px; margin-bottom:6px; border-radius:10px; box-shadow: 0 6px 18px rgba(0,0,0,0.5); }
.reco-card { border-radius:10px; padding:10px; margin:6px; background: var(--glass-bg); transition: transform .15s ease, box-shadow .15s ease; }
.reco-card:hover { transform: translateY(-6px); box-shadow: 0 14px 34px rgba(0,0,0,0.6); }
.modern-btn { border-radius: 12px; background: linear-gradient(90deg, var(--accent1), var(--accent2)); color: white; border: none; box-shadow: 0 8px 30px rgba(118, 75, 162, 0.15); }
"""
app.index_string = app.index_string.replace("</head>", f"<style>{custom_css}</style></head>")

app.layout = dbc.Container([
    dcc.Store(id="theme-store", storage_type="local", data="dark"),
    dcc.Store(id="problemset-store"),
    html.Link(id="theme-css", rel="stylesheet", href=dbc.themes.CYBORG),
    html.Div(id="body-class-dummy", style={"display":"none"}),
    dbc.Navbar([
        html.Div([html.I(className="fa-solid fa-bolt me-2"), html.Span(APP_TITLE, style={"fontWeight":"600"})]),
        dbc.Input(id="cf-handle", placeholder="handle (e.g. tourist)", value="tourist", style={"width":"260px"}),
        dbc.Button("Load", id="load-btn", color="light", className="ms-2"),
        dbc.Button(html.I(className="fa-solid fa-sun"), id="theme-toggle", color="link", className="ms-2", title="Toggle theme")
    ], color="primary", dark=True, className="mb-3", expand="md"),
    dcc.Loading(id="main-loader", type="dot", children=html.Div(id="main-area")),
    html.Footer(html.Div("Made By imunderthetree :))", className="text-center text-muted small mt-4"))
], fluid=True)

@app.callback(Output("problemset-store", "data"), Input("load-btn", "n_clicks"), State("cf-handle", "value"), prevent_initial_call=True)
def load_problemset(n, handle):
    df = cf_problemset_df()
    if df is None or df.empty:
        return []
    df_small = df[["name","rating","tags","link"]].to_dict(orient="records")
    return df_small

@app.callback(Output("main-area", "children"),
              Input("load-btn", "n_clicks"),
              State("cf-handle", "value"),
              State("problemset-store", "data"),
              prevent_initial_call=True)
def render_main(n, handle, problemset_json):
    user = cf_user(handle)
    subs = cf_submissions(handle, count=800)
    rating_hist = cf_rating_history(handle)
    problemset = pd.DataFrame(problemset_json) if problemset_json else cf_problemset_df()

    if user is None:
        return dbc.Alert("Could not fetch user. Check handle or network.", color="danger")

    rc = rank_color(user.get("rank"))
    streaks = compute_streaks(subs)
    weak_tags = analyze_weak_tags(subs)

    avatar = user.get("avatar") or user.get("titlePhoto") or ""
    profile = dbc.Card([
    dbc.Row([
        dbc.Col(
            html.Img(
                src=avatar,
                style={
                    "width":"100px",
                    "borderRadius":"50%",
                    "border":f"3px solid {rc}",
                    "boxShadow":f"0 0 18px {rc}"
                }
            ),
            width="auto"
        ),
        dbc.Col([
            html.H3(user.get("handle",""), style={"color":rc,"marginBottom":"4px"}),
            html.Div([
                dbc.Badge(user.get("rank","Unrated").title(), color="secondary", className="me-2"),
                html.Span(f"Rating: {user.get('rating','N/A')}", style={"marginRight":"10px"}),
                html.Span(f"Max: {user.get('maxRating','N/A')}", style={"opacity":0.8})
            ])
        ], style={"paddingLeft":"12px"})
    ], align="center")
], className="profile-glow mb-3", style={"border":f"1px solid {rc}"})


    stats = dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([html.Div([html.I(className="fa-solid fa-trophy me-2"), html.Span("Rating")]), html.H4(str(user.get("rating","N/A")), className="mt-2")]), color="dark", inverse=True), md=4),
        dbc.Col(dbc.Card(dbc.CardBody([html.Div([html.I(className="fa-solid fa-fire me-2"), html.Span("Current Streak")]), html.H4(f"{streaks['current']} days", className="mt-2")]), color="success", inverse=True), md=4),
        dbc.Col(dbc.Card(dbc.CardBody([html.Div([html.I(className="fa-solid fa-medal me-2"), html.Span("Longest Streak")]), html.H4(f"{streaks['longest']} days", className="mt-2")]), color="info", inverse=True), md=4),
    ], className="mb-3")

    rating_fig = build_rating_figure(rating_hist, color=rc)
    heatmap_fig = build_heatmap(subs, days=120)

    weak_tag_buttons = []
    for wt in weak_tags:
        t = wt["tag"]
        btn = dbc.Button(t, id={"type":"weak-tag","tag": t}, color="warning", outline=True, className="weak-tag")
        weak_tag_buttons.append(btn)

    rec_area = html.Div(id="rec-area", children=[html.P("Click a weak tag to get recommended practice problems.", className="text-muted")])

    left_col = [
        profile,
        stats,
        dbc.Card(dbc.CardBody([html.H5("Rating History"), dcc.Graph(figure=rating_fig, config={"displayModeBar":False})]), className="mb-3 glass-card"),
        dbc.Card(dbc.CardBody([html.H5("Weak Tags"), html.Div(weak_tag_buttons), rec_area]), className="mb-3 glass-card")
    ]
    right_col = [dbc.Card(dbc.CardBody([html.H5("Activity Heatmap (last 120 days)"), dcc.Graph(figure=heatmap_fig, config={"displayModeBar":False})]), className="mb-3 glass-card")]

    layout = dbc.Row([dbc.Col(left_col, md=8), dbc.Col(right_col, md=4)], className="g-3")
    return layout

@app.callback(Output("rec-area", "children"),
              Input({"type":"weak-tag","tag":dash.ALL}, "n_clicks"),
              State({"type":"weak-tag","tag":dash.ALL}, "id"),
              State("cf-handle", "value"),
              State("problemset-store", "data"),
              prevent_initial_call=True)
def show_recommendations(n_clicks, ids, handle, problemset_json):
    if not n_clicks or all(x is None for x in n_clicks):
        return dash.no_update
    triggered = ctx.triggered_id
    if triggered:
        tag = triggered["tag"]
    else:
        idx = max(range(len(n_clicks)), key=lambda i: (n_clicks[i] or 0))
        tag = ids[idx]["tag"]

    prob_df = pd.DataFrame(problemset_json) if problemset_json else cf_problemset_df()
    user = cf_user(handle)
    user_rating = user.get("rating") if user else None
    recs = recommend_for_tag(prob_df, tag, n=6, user_rating=user_rating)

    if not recs:
        return html.P("No problems found for this tag.", className="text-muted")

    cards = []
    for r in recs:
        rating = r.get("rating")
        rating_label = str(int(rating)) if pd.notna(rating) else "N/A"
        c = dbc.Card([
            dbc.Row([
                dbc.Col(html.Div([html.Div(r["name"], style={"fontWeight":"600"}), html.Small(f"Rating: {rating_label}", className="text-muted")]), md=8),
                dbc.Col(html.Div(dbc.Button("Solve Now", href=r.get("link"), target="_blank", className="modern-btn", n_clicks=0), style={"textAlign":"right"}), md=4)
            ], align="center")
        ], className="reco-card")
        cards.append(c)
    return dbc.Row([dbc.Col(card, md=12) for card in cards])

@app.callback(Output("theme-css", "href"), Output("theme-store", "data"),
              Input("theme-toggle", "n_clicks"), State("theme-store", "data"), prevent_initial_call=True)
def toggle_theme(n, current):
    if current == "dark":
        return dbc.themes.BOOTSTRAP, "light"
    else:
        return dbc.themes.CYBORG, "dark"

app.clientside_callback(
    """
    function(theme) {
        if (!theme) { return ''; }
        if (theme === 'dark') {
            document.body.classList.remove('light');
            document.body.classList.add('dark');
        } else {
            document.body.classList.remove('dark');
            document.body.classList.add('light');
        }
        return '';
    }
    """,
    Output("body-class-dummy", "children"),
    Input("theme-store", "data"),
)

if __name__ == "__main__":
    app.run(debug=True)
