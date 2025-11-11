
import os
import math
import random
import datetime as dt
from typing import List, Dict

import streamlit as st
import pandas as pd

# Google Sheets
import gspread
from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as UserCredentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Charts
import plotly.express as px

# ---------------------------
# CONFIG
# ---------------------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"]
DEFAULT_SHEET_ID = st.secrets.get("GOOGLE_SHEET_ID", "")  # Put your Sheet ID into Streamlit secrets for security
DEFAULT_RENTAL_MONTHLY = 2500.00  # You can change this in the UI
DEFAULT_TITHE_PCT = 10.0          # You can change this in the UI
DEFAULT_SAVINGS_PCT = 10.0        # "Emergency" savings target for normal mode

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

# Low-level category mapping for Daily Spending dropdown
LOW_LEVEL_CATEGORIES = [
    "Tithe", "Rental Reserve", "Savings (Emergency)",
    "Food", "Transportation", "Insurance/Health", "Child",
    "Debt", "Clothing/Personal", "Subscriptions/Misc"
]

# ---------------------------
# AUTH HELPERS (Google OAuth)
# ---------------------------
def get_gspread_client_oauth() -> gspread.client.Client:
    """Authenticate with Google Sheets using Service Account credentials from Streamlit Secrets."""
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], 
        scopes=SCOPES
    )

    # Patch: create authorized session manually to fix "_auth_request" errors
    import google.auth.transport.requests
    authed_session = google.auth.transport.requests.AuthorizedSession(creds)
    client = gspread.Client(auth=creds, session=authed_session)
    return client


# ---------------------------
# DATA INIT & UTILITIES
# ---------------------------
def init_sheets(client: gspread.Client, sheet_id: str):
    sh = client.open_by_key(sheet_id)

    # Budgets: each row is a category, each column is a "Check" (Check1..Check4) both Temporary & Post-Rental views
    budget_headers = ["Category",
                      "Check1_Temp", "Check2_Temp", "Check3_Temp", "Check4_Temp",
                      "Check1_Post", "Check2_Post", "Check3_Post", "Check4_Post",
                      "Monthly_Target"]  # optional target per category
    ws_budgets = open_or_create_worksheet(sh, "Budgets", budget_headers)

    # Daily Spending: transactional ledger
    daily_headers = ["Date", "Category", "Amount", "Memo"]
    ws_daily = open_or_create_worksheet(sh, "Daily_Spending", daily_headers)

    # Dashboard data: store key/value settings
    dash_headers = ["Key", "Value"]
    ws_dash = open_or_create_worksheet(sh, "Dashboard_Data", dash_headers)

    # Seed Budgets if empty
    current_vals = ws_budgets.get_all_values()
    if len(current_vals) <= 1:
        seed_rows = []
        for cat in CATEGORIES_ORDERED:
            seed_rows.append([cat, 0,0,0,0, 0,0,0,0, ""])
        ws_budgets.update(f"A2:J{len(seed_rows)+1}", seed_rows)

    # Seed Dashboard_Data
    dash_vals = ws_dash.get_all_values()
    if len(dash_vals) <= 1:
        ws_dash.update("A2:B10", [
            ["Monthly_Income", 0],
            ["Rental_Monthly", DEFAULT_RENTAL_MONTHLY],
            ["Tithe_Pct", DEFAULT_TITHE_PCT],
            ["Savings_Pct", DEFAULT_SAVINGS_PCT],
            ["Emergency_Target_Months", 3],
            ["Emergency_Current", 0],
            ["Mode", "Temporary"],  # or "Post-Rental"
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
        if row.empty:
            totals[cat] = 0.0
        else:
            totals[cat] = row[mode_cols].applymap(to_float).sum(axis=1).values[0]
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
        ws_dash.update_cell(
            int(dash_df.index[dash_df["Key"]=="Verse_Index"][0]) + 2, 2, idx
        )

def render_budget_table(ws_budgets, mode_cols: List[str], title: str):
    st.subheader(title)
    df = df_from_ws(ws_budgets).copy()
    display_cols = ["Category"] + mode_cols + ["Monthly_Target"]
    df_show = df[display_cols].copy()
    edited = st.data_editor(df_show, num_rows="dynamic", use_container_width=True, key=title)
    if st.button(f"Save changes to {title}"):
        # write back edited values to the corresponding columns
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

    # Filters
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
    start_date, end_date = date_filter
    if start_date: df = df[df["Date"] >= start_date]
    if end_date: df = df[df["Date"] <= end_date]
    if category_filter != "All":
        df = df[df["Category"] == category_filter]

    st.dataframe(df.sort_values("Date", ascending=False), use_container_width=True, height=360)

    # Running totals vs budget (by category)
    st.markdown("#### Category Totals vs Budget")
    totals = df.groupby("Category")["Amount"].sum().reset_index()
    # Build simple monthly budget sums from Budgets sheet (sum of all checks, chosen mode – here we compare against Temporary totals)
    temp_cols = ["Check1_Temp","Check2_Temp","Check3_Temp","Check4_Temp"]
    bdf = budget_df.copy()
    bdf["Budget_Total"] = bdf[temp_cols].applymap(to_float).sum(axis=1)
    merged = totals.merge(bdf[["Category","Budget_Total"]], on="Category", how="left").fillna(0)
    st.dataframe(merged, use_container_width=True)

    fig = px.bar(merged, x="Category", y=["Amount","Budget_Total"], barmode="group", title="Actual vs Budget (Temporary)")
    st.plotly_chart(fig, use_container_width=True, theme="streamlit")

def dashboard_view(ws_budgets, ws_daily, ws_dash):
    verse_header(ws_dash)

    dash_df = df_from_ws(ws_dash)
    monthly_income = to_float(dash_df.loc[dash_df["Key"]=="Monthly_Income","Value"].values[0])
    rental_monthly = to_float(dash_df.loc[dash_df["Key"]=="Rental_Monthly","Value"].values[0])
    tithe_pct = to_float(dash_df.loc[dash_df["Key"]=="Tithe_Pct","Value"].values[0])
    savings_pct = to_float(dash_df.loc[dash_df["Key"]=="Savings_Pct","Value"].values[0])
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

    # Totals
    budget_df = df_from_ws(ws_budgets)
    temp_cols = ["Check1_Temp","Check2_Temp","Check3_Temp","Check4_Temp"]
    post_cols = ["Check1_Post","Check2_Post","Check3_Post","Check4_Post"]
    cols = temp_cols if mode == "Temporary" else post_cols

    totals = compute_totals(budget_df, cols)

    # High-level rollups
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

    # Bars for 70-10-10-10 vs Actual (Temporary)
    st.markdown("#### 70–10–10–10 vs Actual")
    goal = pd.DataFrame({
        "Category": ["Tithe","Offerings","Savings","Living"],
        "GoalPct": [10,10,10,70],
        "Goal$": [monthly_income*0.10, monthly_income*0.10, monthly_income*0.10, monthly_income*0.70]
    })
    actual = pd.DataFrame({
        "Category": ["Tithe","Offerings","Savings","Living"],
        "Actual$": [tithe_total, 0.0 if mode=="Temporary" else monthly_income*0.10, savings_total, living_total]
    })
    merged = goal.merge(actual, on="Category", how="left").fillna(0)
    fig = px.bar(merged, x="Category", y=["Goal$","Actual$"], barmode="group", title="Goal vs Actual")
    st.plotly_chart(fig, use_container_width=True, theme="streamlit")

    # Rental Impact
    st.markdown("#### Rental Impact")
    rental_pct_income = (rental_monthly / monthly_income * 100.0) if monthly_income else 0.0
    st.progress(min(1.0, rental_pct_income/100.0), text=f"Rental absorbs {rental_pct_income:.1f}% of income")

    # Transactions summary
    st.markdown("#### Actuals This Month (Transactions)")
    daily_df = df_from_ws(ws_daily)
    if not daily_df.empty:
        daily_df["Amount"] = daily_df["Amount"].apply(to_float)
        by_cat = daily_df.groupby("Category")["Amount"].sum().reset_index().sort_values("Amount", ascending=False)
        st.dataframe(by_cat, use_container_width=True, height=260)
        fig2 = px.pie(by_cat, names="Category", values="Amount", title="Spending Breakdown (Actuals)")
        st.plotly_chart(fig2, use_container_width=True, theme="streamlit")
    else:
        st.info("No transactions logged yet. Head to Daily Spending to add some.")

def budgets_view(ws_budgets):
    st.markdown("### Budgets (Checks 1–4)")
    st.caption("Use the expanders below to edit Temporary vs Post-Rental amounts per check.")

    with st.expander("Temporary (Vacancy) — per Check"):
        render_budget_table(ws_budgets,
                            ["Check1_Temp","Check2_Temp","Check3_Temp","Check4_Temp"],
                            "Temporary Mode Editor")
    with st.expander("Post-Rental (Normal) — per Check"):
        render_budget_table(ws_budgets,
                            ["Check1_Post","Check2_Post","Check3_Post","Check4_Post"],
                            "Post-Rental Mode Editor")

def daily_view(ws_daily, ws_budgets):
    st.markdown("### Daily Spending Ledger")
    # Filters
    col1, col2, col3 = st.columns(3)
    start_date = col1.date_input("Start date", dt.date(dt.date.today().year, dt.date.today().month, 1))
    end_date = col2.date_input("End date", dt.date.today())
    budget_df = df_from_ws(ws_budgets)
    category_filter = col3.selectbox("Category filter", ["All"] + list(budget_df["Category"].unique()))
    render_daily_spending(ws_daily, budget_df, (start_date, end_date), category_filter)

# ---------------------------
# MAIN APP
# ---------------------------
@st.cache_resource(ttl=600)
def get_gspread_client_cached():
    """Create and cache the Google Sheets client for 10 minutes."""
    return get_gspread_client_oauth()

@st.cache_data(ttl=60)
def init_sheets_cached(_client, sheet_id: str):
    """Open all worksheets and cache references for 60 seconds."""
    sh = _client.open_by_key(sheet_id)
    ws_budgets = open_or_create_worksheet(sh, "Budgets")
    ws_daily = open_or_create_worksheet(sh, "Daily_Spending")
    ws_dash = open_or_create_worksheet(sh, "Dashboard_Data")
    return sh, ws_budgets, ws_daily, ws_dash

def main():
    st.set_page_config(page_title="Family Stewardship Dashboard", page_icon="📊", layout="wide")
    st.title("Family Stewardship Dashboard")
    st.caption("Modern neutrals • Faith-centered • Practical & clear")

    # --- GOOGLE SHEET CONNECTION SETUP ---
    st.subheader("🔗 Google Sheet Connection")

    # Use the ID from secrets; hide manual entry once verified
    sheet_id = st.secrets.get("GOOGLE_SHEET_ID", DEFAULT_SHEET_ID)
    if not sheet_id:
        st.error("❌ No Google Sheet ID found in Streamlit secrets. Please add it under 'Settings → Secrets'.")
        st.stop()
    else:
        st.success("✅ Connected to Google Sheet successfully.")
        st.caption(f"📄 Connected Sheet ID: `{sheet_id}`")

    # --- GOOGLE SHEETS CONNECTION (with caching) ---
    try:
        client = get_gspread_client_cached()
        sh, ws_budgets, ws_daily, ws_dash = init_sheets_cached(client, sheet_id)
    except Exception as e:
        st.error(f"Google auth / sheet error: {e}")
        st.stop()

    # --- TABS (render on success) ---
    tab1, tab2, tab3 = st.tabs(["📈 Dashboard", "📋 Budgets", "🧾 Daily Spending"])

    with tab1:
        dashboard_view(ws_budgets, ws_daily, ws_dash)
    with tab2:
        budgets_view(ws_budgets)
    with tab3:
        daily_view(ws_daily, ws_budgets)

if __name__ == "__main__":
    main()
