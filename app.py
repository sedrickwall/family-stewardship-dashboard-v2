import os
import random
import datetime as dt
from typing import List, Dict

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px

# ---------------------------
# CONFIG
# ---------------------------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
DEFAULT_SHEET_ID = st.secrets.get("GOOGLE_SHEET_ID", "")
DEFAULT_RENTAL_MONTHLY = 2500.00
DEFAULT_TITHE_PCT = 10.0
DEFAULT_SAVINGS_PCT = 10.0

SCRIPTURE = [
    ("Malachi 3:10", "Bring the whole tithe into the storehouse... 'Test me in this,' says the LORD Almighty."),
    ("Proverbs 21:20", "The wise store up choice food and olive oil, but fools gulp theirs down."),
    ("Luke 14:28", "Suppose one of you wants to build a tower. Won’t you first sit down and estimate the cost?"),
    ("2 Corinthians 9:7", "God loves a cheerful giver."),
    ("Philippians 4:11–12", "I have learned to be content whatever the circumstances..."),
]

CATEGORIES_ORDERED = [
    "Tithe",
    "Rental Reserve",
    "Savings (Emergency)",
    "Food",
    "Transportation",
    "Insurance/Health",
    "Child",
    "Debt",
    "Clothing/Personal",
    "Subscriptions/Misc",
]

LOW_LEVEL_CATEGORIES = CATEGORIES_ORDERED

# ---------------------------
# AUTH HELPERS (Streamlit Secrets)
# ---------------------------
def get_gspread_client_oauth() -> gspread.client.Client:
    """Authenticate with Google Sheets using Streamlit Secrets (Service Account)."""
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )

    # Fix for "_auth_request" issues on Streamlit Cloud
    import google.auth.transport.requests
    authed_session = google.auth.transport.requests.AuthorizedSession(creds)
    client = gspread.Client(auth=creds, session=authed_session)
    return client

def open_or_create_worksheet(sh, title: str, headers: List[str] = None):
    try:
        ws = sh.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=1000, cols=50)
        if headers:
            ws.update('A1', [headers])
    return ws

# ---------------------------
# DATA INIT & UTILITIES
# ---------------------------
def init_sheets(client: gspread.Client, sheet_id: str):
    sh = client.open_by_key(sheet_id)

    budget_headers = ["Category",
                      "Check1_Temp", "Check2_Temp", "Check3_Temp", "Check4_Temp",
                      "Check1_Post", "Check2_Post", "Check3_Post", "Check4_Post",
                      "Monthly_Target"]
    ws_budgets = open_or_create_worksheet(sh, "Budgets", budget_headers)

    daily_headers = ["Date", "Category", "Amount", "Memo"]
    ws_daily = open_or_create_worksheet(sh, "Daily_Spending", daily_headers)

    dash_headers = ["Key", "Value"]
    ws_dash = open_or_create_worksheet(sh, "Dashboard_Data", dash_headers)

    current_vals = ws_budgets.get_all_values()
    if len(current_vals) <= 1:
        seed_rows = [[cat, 0, 0, 0, 0, 0, 0, 0, 0, ""] for cat in CATEGORIES_ORDERED]
        ws_budgets.update(f"A2:J{len(seed_rows)+1}", seed_rows)

    dash_vals = ws_dash.get_all_values()
    if len(dash_vals) <= 1:
        ws_dash.update("A2:B10", [
            ["Monthly_Income", 0],
            ["Rental_Monthly", DEFAULT_RENTAL_MONTHLY],
            ["Tithe_Pct", DEFAULT_TITHE_PCT],
            ["Savings_Pct", DEFAULT_SAVINGS_PCT],
            ["Emergency_Target_Months", 3],
            ["Emergency_Current", 0],
            ["Mode", "Temporary"],
            ["Verse_Index", 0],
        ])

    return sh, ws_budgets, ws_daily, ws_dash

def df_from_ws(ws):
    vals = ws.get_all_values()
    if not vals:
        return pd.DataFrame()
    df = pd.DataFrame(vals[1:], columns=vals[0])
    return df

def to_float(x):
    try:
        if isinstance(x, str):
            x = x.replace("$","").replace(",","").strip()
        return float(x)
    except:
        return 0.0

def compute_totals(budget_df: pd.DataFrame, mode_cols: List[str]) -> Dict[str, float]:
    totals = {}
    for cat in CATEGORIES_ORDERED:
        row = budget_df[budget_df["Category"] == cat]
        totals[cat] = row[mode_cols].applymap(to_float).sum(axis=1).values[0] if not row.empty else 0.0
    return totals

def kpi_row(label, value, suffix=""):
    st.metric(label, f"{value:,.2f}{suffix}")

# ---------------------------
# UI HELPERS
# ---------------------------
def verse_header(ws_dash):
    dash_df = df_from_ws(ws_dash)
    idx = 0
    try:
        idx = int(float(dash_df.loc[dash_df["Key"]=="Verse_Index","Value"].values[0]))
    except:
        idx = 0
    idx = idx % len(SCRIPTURE)
    ref, text = SCRIPTURE[idx]
    st.markdown(f"### “{text}”  \n*— {ref}*")
    if st.button("New verse"):
        idx = random.randint(0, len(SCRIPTURE)-1)
        ws_dash.update_cell(int(dash_df.index[dash_df["Key"]=="Verse_Index"][0]) + 2, 2, idx)

def render_budget_table(ws_budgets, mode_cols: List[str], title: str):
    st.subheader(title)
    df = df_from_ws(ws_budgets)
    display_cols = ["Category"] + mode_cols + ["Monthly_Target"]
    df_show = df[display_cols].copy()
    edited = st.data_editor(df_show, num_rows="dynamic", use_container_width=True, key=title)
    if st.button(f"Save changes to {title}"):
        base = df_from_ws(ws_budgets)
        for col in mode_cols + ["Monthly_Target"]:
            base[col] = edited[col]
        ws_budgets.update(f"A2:J{len(base)+1}", base.values.tolist())
        st.success("Saved.")

def render_daily_spending(ws_daily, budget_df, date_filter, category_filter):
    st.subheader("Add Transaction")
    with st.form("add_txn", clear_on_submit=True):
        col1, col2 = st.columns(2)
        date = col1.date_input("Date", dt.date.today())
        category = col2.selectbox("Category", LOW_LEVEL_CATEGORIES)
        amount = st.number_input("Amount", min_value=0.0, step=1.0)
        memo = st.text_input("Memo (optional)")
        submitted = st.form_submit_button("Add")
        if submitted:
            ws_daily.append_row([str(date), category, amount, memo])
            st.success("Transaction added.")

    st.subheader("Transactions")
    df = df_from_ws(ws_daily)
    if df.empty:
        st.info("No transactions yet.")
        return

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
    start_date, end_date = date_filter
    if start_date: df = df[df["Date"] >= start_date]
    if end_date: df = df[df["Date"] <= end_date]
    if category_filter != "All": df = df[df["Category"] == category_filter]

    st.dataframe(df.sort_values("Date", ascending=False), use_container_width=True, height=360)

    st.markdown("#### Category Totals vs Budget")
    totals = df.groupby("Category")["Amount"].sum().reset_index()
    temp_cols = ["Check1_Temp","Check2_Temp","Check3_Temp","Check4_Temp"]
    bdf = budget_df.copy()
    bdf["Budget_Total"] = bdf[temp_cols].applymap(to_float).sum(axis=1)
    merged = totals.merge(bdf[["Category","Budget_Total"]], on="Category", how="left").fillna(0)
    st.dataframe(merged, use_container_width=True)

    fig = px.bar(merged, x="Category", y=["Amount","Budget_Total"], barmode="group", title="Actual vs Budget")
    st.plotly_chart(fig, use_container_width=True, theme="streamlit")

# ---------------------------
# MAIN VIEWS
# ---------------------------
def dashboard_view(ws_budgets, ws_daily, ws_dash):
    verse_header(ws_dash)

    dash_df = df_from_ws(ws_dash)
    monthly_income = to_float(dash_df.loc[dash_df["Key"]=="Monthly_Income","Value"].values[0])
    rental_monthly = to_float(dash_df.loc[dash_df["Key"]=="Rental_Monthly","Value"].values[0])
    mode = dash_df.loc[dash_df["Key"]=="Mode","Value"].values[0] if "Mode" in dash_df["Key"].values else "Temporary"

    st.markdown("#### Settings")
    colA, colB, colC = st.columns(3)
    monthly_income = colA.number_input("Monthly Income", value=float(monthly_income), step=100.0)
    rental_monthly = colB.number_input("Rental (Vacancy) Monthly", value=float(rental_monthly), step=50.0)
    mode = colC.selectbox("Framework Mode", ["Temporary", "Post-Rental"], index=0 if mode=="Temporary" else 1)

    if st.button("Save Dashboard Settings"):
        ws_dash.update("A2:B2", [["Monthly_Income", monthly_income]])
        ws_dash.update("A3:B3", [["Rental_Monthly", rental_monthly]])
        ws_dash.update("A7:B7", [["Mode", mode]])
        st.success("Saved settings.")

    budget_df = df_from_ws(ws_budgets)
    temp_cols = ["Check1_Temp","Check2_Temp","Check3_Temp","Check4_Temp"]
    post_cols = ["Check1_Post","Check2_Post","Check3_Post","Check4_Post"]
    cols = temp_cols if mode == "Temporary" else post_cols
    totals = compute_totals(budget_df, cols)

    tithe_total = totals.get("Tithe", 0.0)
    rental_total = totals.get("Rental Reserve", 0.0)
    savings_total = totals.get("Savings (Emergency)", 0.0)
    living_total = sum(v for k,v in totals.items() if k not in ["Tithe","Rental Reserve","Savings (Emergency)"])

    st.markdown("### Monthly Overview")
    c1,c2,c3,c4,c5 = st.columns(5)
    kpi_row("Income", monthly_income)
    kpi_row("Tithe", tithe_total)
    kpi_row("Rental Reserve", rental_total)
    kpi_row("Savings (Emergency)", savings_total)
    kpi_row("Living / Expenses", living_total)

def budgets_view(ws_budgets):
    st.markdown("### Budgets (Checks 1–4)")
    with st.expander("Temporary (Vacancy)"):
        render_budget_table(ws_budgets, ["Check1_Temp","Check2_Temp","Check3_Temp","Check4_Temp"], "Temporary Mode Editor")
    with st.expander("Post-Rental (Normal)"):
        render_budget_table(ws_budgets, ["Check1_Post","Check2_Post","Check3_Post","Check4_Post"], "Post-Rental Mode Editor")

def daily_view(ws_daily, ws_budgets):
    st.markdown("### Daily Spending Ledger")
    col1, col2, col3 = st.columns(3)
    start_date = col1.date_input("Start date", dt.date(dt.date.today().year, dt.date.today().month, 1))
    end_date = col2.date_input("End date", dt.date.today())
    budget_df = df_from_ws(ws_budgets)
    category_filter = col3.selectbox("Category filter", ["All"] + list(budget_df["Category"].unique()))
    render_daily_spending(ws_daily, budget_df, (start_date, end_date), category_filter)

# ---------------------------
# MAIN APP
# ---------------------------
def main():
    st.set_page_config(page_title="Family Stewardship Dashboard", page_icon="📊", layout="wide")
    st.title("Family Stewardship Dashboard")
    st.caption("Modern neutrals • Faith-centered • Practical & clear")

    st.subheader("🔗 Google Sheet Connection")

    sheet_id = st.secrets.get("GOOGLE_SHEET_ID", DEFAULT_SHEET_ID)
    if not sheet_id:
        st.error("❌ No Google Sheet ID found. Add it under 'Settings → Secrets'.")
        st.stop()
    else:
        st.success("✅ Connected to Google Sheet successfully.")
        st.caption(f"📄 Connected Sheet ID: `{sheet_id}`")

    try:
        client = get_gspread_client_oauth()
        sh, ws_budgets, ws_daily, ws_dash = init_sheets(client, sheet_id)
    except Exception as e:
        st.error(f"Google auth / sheet error: {e}")
        st.stop()

    tab1, tab2, tab3 = st.tabs(["📈 Dashboard", "📋 Budgets", "🧾 Daily Spending"])
    with tab1: dashboard_view(ws_budgets, ws_daily, ws_dash)
    with tab2: budgets_view(ws_budgets)
    with tab3: daily_view(ws_daily, ws_budgets)

if __name__ == "__main__":
    main()
