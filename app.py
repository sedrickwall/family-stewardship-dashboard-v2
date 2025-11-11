import os
import random
import datetime as dt
from typing import List, Dict

import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials as UserCredentials

# ---------------------------
# CONFIG
# ---------------------------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
DEFAULT_RENTAL_MONTHLY = 2500.0
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

# ---------------------------
# GOOGLE AUTH
# ---------------------------
def get_gspread_client() -> gspread.client.Client:
    """Authenticate user interactively via OAuth."""
    if os.path.exists("token.json"):
        creds = UserCredentials.from_authorized_user_file("token.json", SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
        creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return gspread.authorize(creds)

def open_or_create_worksheet(sh, title: str, headers: List[str] = None):
    try:
        ws = sh.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=1000, cols=50)
        if headers:
            ws.update("A1", [headers])
    return ws

def df_from_ws(ws):
    vals = ws.get_all_values()
    if not vals:
        return pd.DataFrame()
    return pd.DataFrame(vals[1:], columns=vals[0])

def to_float(x):
    try:
        return float(str(x).replace("$", "").replace(",", ""))
    except:
        return 0.0

# ---------------------------
# UI HELPERS
# ---------------------------
def verse_header():
    ref, text = random.choice(SCRIPTURE)
    st.markdown(f"### “{text}”  \n*— {ref}*")

def dashboard_view(ws_budgets, ws_daily, ws_dash):
    st.markdown("## 📈 Dashboard Overview")
    verse_header()

    dash_df = df_from_ws(ws_dash)
    if dash_df.empty:
        st.info("No dashboard data found yet.")
        return

    monthly_income = to_float(dash_df.loc[dash_df["Key"] == "Monthly_Income", "Value"].values[0])
    rental_monthly = to_float(dash_df.loc[dash_df["Key"] == "Rental_Monthly", "Value"].values[0])
    mode = dash_df.loc[dash_df["Key"] == "Mode", "Value"].values[0]

    st.metric("Monthly Income", f"${monthly_income:,.0f}")
    st.metric("Rental (Vacancy)", f"${rental_monthly:,.0f}")

def budgets_view(ws_budgets):
    st.markdown("## 📋 Budgets")
    df = df_from_ws(ws_budgets)
    if df.empty:
        st.warning("No budgets yet.")
    else:
        st.dataframe(df, use_container_width=True)

def daily_view(ws_daily):
    st.markdown("## 🧾 Daily Spending")

    with st.form("add_txn", clear_on_submit=True):
        date = st.date_input("Date", dt.date.today())
        category = st.text_input("Category")
        amount = st.number_input("Amount", min_value=0.0, step=1.0)
        memo = st.text_input("Memo (optional)")
        if st.form_submit_button("Add"):
            ws_daily.append_row([str(date), category, amount, memo])
            st.success("Transaction added.")

    df = df_from_ws(ws_daily)
    if not df.empty:
        st.dataframe(df.sort_values("Date", ascending=False), use_container_width=True)
    else:
        st.info("No transactions logged yet.")

# ---------------------------
# MAIN APP
# ---------------------------
def main():
    st.set_page_config(page_title="Family Stewardship Dashboard", page_icon="📊", layout="wide")
    st.title("Family Stewardship Dashboard")

    sheet_id = st.text_input("Enter your Google Sheet ID:")
    if not sheet_id:
        st.stop()

    st.write("Authenticate with Google — this will open a sign-in window.")
    if st.button("Authenticate"):
        st.session_state["client"] = get_gspread_client()

    if "client" not in st.session_state:
        st.info("Click 'Authenticate' to connect to Google Sheets.")
        return

    client = st.session_state["client"]
    sh = client.open_by_key(sheet_id)

    ws_budgets = open_or_create_worksheet(sh, "Budgets", ["Category", "Check1", "Check2", "Check3", "Check4"])
    ws_daily = open_or_create_worksheet(sh, "Daily_Spending", ["Date", "Category", "Amount", "Memo"])
    ws_dash = open_or_create_worksheet(sh, "Dashboard_Data", ["Key", "Value"])

    tab1, tab2, tab3 = st.tabs(["📈 Dashboard", "📋 Budgets", "🧾 Daily Spending"])
    with tab1:
        dashboard_view(ws_budgets, ws_daily, ws_dash)
    with tab2:
        budgets_view(ws_budgets)
    with tab3:
        daily_view(ws_daily)

if __name__ == "__main__":
    main()
