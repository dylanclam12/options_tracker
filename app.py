import os, pandas as pd
import plotly.express as px
import streamlit as st
from notion_client import Client

# ---------- Config / Secrets ----------
# On Streamlit Cloud, put these in Secrets (Settings → Secrets):
# NOTION_TOKEN, NOTION_DATABASE_ID
NOTION_TOKEN = st.secrets.get("NOTION_TOKEN", os.getenv("NOTION_TOKEN"))
DB_ID = st.secrets.get("PROFIT_LOSS", os.getenv("PROFIT_LOSS"))

notion = Client(auth=NOTION_TOKEN)

# ---------- Notion helpers ----------
def _plain_text(rich):
    return "".join([t.get("plain_text","") for t in (rich or [])])

def _get_prop_val(p):
    t = p["type"]; v = p[t]
    if t in ("title","rich_text"): return _plain_text(v)
    if t == "number": return v
    if t == "select": return v["name"] if v else None
    if t == "date": return v["start"] if v else None
    if t == "formula":
        for k in ("number","string","date","boolean"):
            if k in v: return v[k]
    return v

def fetch_notion_df(database_id: str) -> pd.DataFrame:
    rows, cursor = [], None
    while True:
        resp = notion.databases.query(database_id=database_id, start_cursor=cursor, page_size=100)
        for page in resp["results"]:
            props = page["properties"]; row = {}
            for k, val in props.items(): row[k] = _get_prop_val(val)
            rows.append(row)
        if not resp.get("has_more"): break
        cursor = resp.get("next_cursor")
    return pd.DataFrame(rows)

# ---------- UI ----------
st.set_page_config(page_title="Profit/Loss by Expiration", layout="wide")
st.title("📈 Weekly Profit and Loss")

with st.sidebar:
    st.caption("Data source: Notion")
    db_id_input = st.text_input("Database ID", value=DB_ID or "", help="32-char Notion DB ID")
    refresh = st.button("Refresh")

if not db_id_input or not NOTION_TOKEN:
    st.warning("Add NOTION_TOKEN and NOTION_DATABASE_ID in Secrets (or fill Database ID above).")
    st.stop()

# fetch data
try:
    pnl_df = fetch_notion_df(db_id_input)
except Exception as e:
    st.error(f"Failed to read Notion DB: {e}")
    st.stop()

if pnl_df.empty:
    st.info("No rows yet. Add items to your Notion database.")
    st.stop()

# Try to coerce relevant columns
if "Expiration" in pnl_df.columns:
    pnl_df["Expiration"] = pd.to_datetime(pnl_df["Expiration"], errors="coerce")
if "Profit/Loss" in pnl_df.columns and pnl_df["Profit/Loss"].dtype == object:
    pnl_df["Profit/Loss"] = pd.to_numeric(
        pnl_df["Profit/Loss"].astype(str).str.replace(",", "", regex=False).str.replace("$", "", regex=False),
        errors="coerce",
    )

# Aggregate Profit/Loss by Expiration and plot
if {"Expiration", "Profit/Loss"}.issubset(pnl_df.columns):
    agg_by_exp = (
        pnl_df.dropna(subset=["Expiration"])
              .groupby("Expiration", as_index=False)["Profit/Loss"].sum()
              .sort_values("Expiration")
    )

    # Format Profit/Loss as $ string for annotation
    agg_by_exp["Profit/Loss $"] = agg_by_exp["Profit/Loss"].apply(
        lambda x: "${:,.2f}".format(x) if pd.notnull(x) else ""
    )

    fig = px.line(
        agg_by_exp,
        x="Expiration",
        y="Profit/Loss",
        markers=True,
        title="Weekly Profit and Loss",
    )
    fig.update_layout(xaxis_title="Expiration", yaxis_title="Total Profit/Loss")

    # Add annotations above each point
    for i, row in agg_by_exp.iterrows():
        fig.add_annotation(
            x=row["Expiration"],
            y=row["Profit/Loss"],
            text=row["Profit/Loss $"],
            showarrow=False,
            yshift=12,
            font=dict(size=12, color="black"),
        )

    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("This database needs columns named **Expiration** (Date) and **Profit/Loss** (Number).")