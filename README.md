# Family Stewardship Dashboard (v2)
Faith-centered family budgeting tool using Streamlit + Google Sheets.

A faith-centered budget & spending app with three tabs:

- **Dashboard**: KPIs, 70–10–10–10 vs Actual, rental impact, scripture header
- **Budgets**: Edit per-check budgets for both **Temporary** (vacancy) and **Post-Rental**
- **Daily Spending**: Log transactions, filter by date/category, and compare Actual vs Budget

## Setup

1) Install requirements
```
pip install -r requirements.txt
```

2) Create a Google Cloud OAuth client and download `client_secret.json` into the same folder as `app.py`.

3) Create or identify your Google Sheet and copy its Sheet ID (the long ID in the URL).

4) Run the app
```
streamlit run app.py
```

5) On first auth, a browser window will open to grant access. A `token.json` file will be created for future runs.

## Notes

- Put your Sheet ID into Streamlit **Secrets** or the text box at the top of the app.
- The app creates three worksheets if missing: `Budgets`, `Daily_Spending`, `Dashboard_Data`.
- In **Budgets**, each category is a row. Checks 1–4 are columns for both Temporary and Post-Rental views.
- The **Dashboard** reads whichever mode you choose to summarize totals.
- **Daily Spending** compares Actuals vs the **Temporary** budget totals by category.

## Optional

- You can seed initial values by editing the `Budgets` and `Dashboard_Data` sheets directly.
- To rotate scripture, click **New verse** on the Dashboard.
