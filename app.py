import os

import pandas as pd
import streamlit as st

from sold_list import rows_from_uploads, salesperson_name
from storage import archived_lists, current_list, publish

st.set_page_config(page_title="Super Helpful Sold List", layout="wide")

st.markdown(
    """
    <style>
      html, body, .stApp, [data-testid="stMarkdown"], [data-testid="stCaption"], h1, h2, h3 {
        font-family: "Century Gothic Pro", "Century Gothic", "CenturyGothic", "AppleGothic", sans-serif !important;
      }
      .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"],
      [data-testid="stBottom"], section.main, .stAppViewBlockContainer {
        background: #f7f5f4 !important;
        color: #231f20 !important;
      }
      header[data-testid="stHeader"] { height: 0 !important; background: transparent !important; }
      .block-container { padding-top: 2.6rem !important; }
      .app-title {
        text-align: center;
        color: #231f20;
        font-size: 2rem;
        font-weight: 700;
        letter-spacing: 0.02em;
        line-height: 1.35;
        margin: 0;
        padding: 0.6rem 1rem 0.15rem;
        overflow: visible;
        white-space: normal;
      }
      .app-sub {
        text-align: center;
        color: #626262;
        margin: 0 0 1rem;
      }
      .app-rule {
        width: 72px;
        height: 4px;
        background: #fd8b15;
        margin: 0 auto 1rem;
        border-radius: 2px;
      }
      div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e1e1e1;
        border-top: 3px solid #fd8b15;
        border-radius: 10px;
        padding: 0.6rem 0.8rem;
      }
      div[data-testid="stMetric"] label, div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #231f20 !important;
      }
      .make-bar {
        background: #231f20;
        color: #fefefe;
        border-left: 6px solid #fd8b15;
        border-radius: 6px;
        padding: 0.4rem 0.75rem;
        font-weight: 700;
        margin: 0.8rem 0 0.3rem;
      }
      .stTabs [data-baseweb="tab-list"] { justify-content: center; }
      .stTabs [data-baseweb="tab"] { color: #231f20; }
      .stTabs [aria-selected="true"] { color: #231f20; border-bottom-color: #fd8b15 !important; }
      button[data-testid="stBaseButton-primary"] {
        background: #fd8b15 !important;
        color: #231f20 !important;
        border: none !important;
      }
      [data-testid="stFileUploader"] { max-width: 560px; }
      [data-testid="stFileUploader"] button {
        min-width: 8.5rem !important;
        width: auto !important;
        white-space: nowrap !important;
        overflow: visible !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def upload_password() -> str:
    try:
        return str(st.secrets["UPLOAD_PASSWORD"])
    except Exception:
        return os.environ.get("UPLOAD_PASSWORD", "")


def money(value) -> str:
    if value is None or value == "" or (isinstance(value, float) and pd.isna(value)):
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if pd.isna(number):
        return ""
    return f"{'-' if number < 0 else ''}${abs(number):,.2f}"


def as_frame(rows: list[dict], show_buyer: bool) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    rename = {
        "stock": "Stock",
        "vin": "VIN",
        "year": "Year",
        "make": "Make",
        "model": "Model",
        "trim": "Trim",
        "type": "Type",
        "mileage": "Mileage",
        "exterior": "Exterior",
        "interior": "Interior",
        "web_price": "Web Price",
        "retail": "Retail Price",
        "age": "Age",
        "comm": "Comm Gross",
        "house": "House Gross",
        "finance": "Finance Gross",
        "sale_date": "Sale Date",
        "buyer": "Buyer",
        "salesperson": "Salesperson",
    }
    frame = frame.rename(columns=rename)
    keep = [
        "Stock",
        "VIN",
        "Year",
        "Make",
        "Model",
        "Trim",
        "Type",
        "Mileage",
        "Exterior",
        "Interior",
        "Web Price",
        "Retail Price",
        "Age",
        "Comm Gross",
        "House Gross",
        "Finance Gross",
    ]
    if show_buyer:
        keep += ["Sale Date", "Buyer"]
    keep += ["Salesperson"]
    out = frame[[column for column in keep if column in frame.columns]].copy()
    if "Mileage" in out.columns:
        out["Mileage"] = pd.to_numeric(out["Mileage"], errors="coerce").round().astype("Int64")
    return out


AVG_COLS = ["Mileage", "Web Price", "Retail Price", "Age", "Comm Gross", "House Gross", "Finance Gross"]


def average_row(group: pd.DataFrame) -> dict:
    row = {column: None if column in ("Web Price", "Retail Price", "Mileage", "Age", "Comm Gross", "House Gross", "Finance Gross") else "" for column in group.columns}
    row["Stock"] = "Average"
    for column in AVG_COLS:
        if column not in group.columns:
            continue
        values = pd.to_numeric(group[column], errors="coerce")
        row[column] = float(values.mean()) if values.notna().any() else None
    return row


def miles_text(value) -> str:
    if value is None or value == "" or (isinstance(value, float) and pd.isna(value)):
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if pd.isna(number):
        return ""
    return f"{int(round(number)):,}"


def age_text(value) -> str:
    if value is None or value == "" or (isinstance(value, float) and pd.isna(value)):
        return ""
    number = float(value)
    return f"{int(number)}" if number.is_integer() else f"{number:,.1f}"


def clear_filters():
    st.session_state["sold_search"] = ""
    st.session_state["sold_make"] = "All makes"
    st.session_state["sold_model"] = "All models"
    st.session_state["sold_match"] = "All vehicles"
    st.session_state["sold_person"] = "All salespeople"


def show_sheet(payload: dict):
    rows = payload.get("rows") or []
    if not rows:
        st.info("No list yet. The upload tab is where a new week gets published.")
        return
    rows = [{**row, "salesperson": salesperson_name(row.get("salesperson"))} for row in rows]

    frame = as_frame(rows, st.session_state.get("show_buyer", True))
    matched = [row for row in rows if row.get("matched")]
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Vehicles", f"{len(rows):,}")
    c2.metric("Makes", f"{frame['Make'].nunique():,}")
    c3.metric("Matched sales", f"{len(matched):,}")
    c4.metric("Comm gross", money(sum(row.get("comm") or 0 for row in matched)))
    c5.metric("House gross", money(sum(row.get("house") or 0 for row in matched)))
    c6.metric("Finance gross", money(sum(row.get("finance") or 0 for row in matched)))

    saved = str(payload.get("saved_at") or "").replace("T", " ")
    files = " · ".join(part for part in [payload.get("inventory_file"), payload.get("sales_file")] if part)
    st.caption(f"Saved {saved}" + (f" from {files}" if files else ""))

    left, make_col, model_col, person_col, right = st.columns([1.6, 1, 1, 1.4, 1.1])
    query = left.text_input("Search", placeholder="Stock, VIN, make, model, buyer, salesperson", key="sold_search")
    makes = ["All makes"] + sorted({row.get("make") or "" for row in rows if row.get("make")})
    make = make_col.selectbox("Make", makes, key="sold_make")
    model_rows = rows if make == "All makes" else [row for row in rows if row.get("make") == make]
    models = ["All models"] + sorted({str(row.get("model") or "").strip() for row in model_rows if str(row.get("model") or "").strip()})
    if st.session_state.get("sold_model") not in models:
        st.session_state["sold_model"] = "All models"
    model = model_col.selectbox("Model", models, key="sold_model")
    people = ["All salespeople"] + sorted({row.get("salesperson") or "" for row in rows if row.get("salesperson")})
    if st.session_state.get("sold_person") not in people:
        st.session_state["sold_person"] = "All salespeople"
    person = person_col.selectbox("Salesperson", people, key="sold_person")
    match = right.selectbox("Sales match", ["All vehicles", "Matched to a sale", "Not on sales report"], key="sold_match")
    right.button("Clear filters", on_click=clear_filters)
    show_buyer = st.checkbox("Buyer / sale date", value=True, key="show_buyer")
    frame = as_frame(rows, show_buyer)

    needle = query.strip().lower()
    if needle:
        blob = frame.astype(str).apply(lambda column: column.str.lower()).agg(" ".join, axis=1)
        frame = frame[blob.str.contains(needle, regex=False)]
    if make != "All makes":
        frame = frame[frame["Make"] == make]
    if model != "All models":
        frame = frame[frame["Model"] == model]
    if person != "All salespeople" and "Salesperson" in frame.columns:
        frame = frame[frame["Salesperson"] == person]
    if match == "Matched to a sale":
        frame = frame[frame["Stock"].isin({row["stock"] for row in rows if row.get("matched")})]
    elif match == "Not on sales report":
        frame = frame[frame["Stock"].isin({row["stock"] for row in rows if not row.get("matched")})]

    miles_avg = pd.to_numeric(frame["Mileage"], errors="coerce").mean() if "Mileage" in frame.columns else None
    web_avg = pd.to_numeric(frame["Web Price"], errors="coerce").mean() if "Web Price" in frame.columns else None
    retail_avg = pd.to_numeric(frame["Retail Price"], errors="coerce").mean() if "Retail Price" in frame.columns else None
    age_avg = pd.to_numeric(frame["Age"], errors="coerce").mean() if "Age" in frame.columns else None
    comm_avg = pd.to_numeric(frame["Comm Gross"], errors="coerce").mean() if "Comm Gross" in frame.columns else None
    house_avg = pd.to_numeric(frame["House Gross"], errors="coerce").mean() if "House Gross" in frame.columns else None
    finance_avg = pd.to_numeric(frame["Finance Gross"], errors="coerce").mean() if "Finance Gross" in frame.columns else None
    web_txt = (money(web_avg) or "—").replace("$", "\\$")
    retail_txt = (money(retail_avg) or "—").replace("$", "\\$")
    comm_txt = (money(comm_avg) or "—").replace("$", "\\$")
    house_txt = (money(house_avg) or "—").replace("$", "\\$")
    finance_txt = (money(finance_avg) or "—").replace("$", "\\$")
    scope = " · ".join(part for part in [make if make != "All makes" else "", model if model != "All models" else "", person if person != "All salespeople" else ""] if part)
    st.caption(
        "Recap"
        + (f" · {scope}" if scope else "")
        + f" · {len(frame):,} vehicles · avg mileage {miles_text(miles_avg) or '—'} · avg web {web_txt} · avg retail {retail_txt} · avg age {age_text(age_avg) or '—'} · avg comm {comm_txt} · avg house {house_txt} · avg finance {finance_txt}"
    )

    money_cols = [column for column in ["Web Price", "Retail Price", "Comm Gross", "House Gross", "Finance Gross"] if column in frame.columns]
    formats = {column: money for column in money_cols}
    if "Age" in frame.columns:
        formats["Age"] = age_text
    if "Mileage" in frame.columns:
        formats["Mileage"] = miles_text

    def paint(value):
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value < 0:
            return "color: #9b2c2c"
        return ""

    def emphasize(row):
        if row.get("Stock") == "Average":
            return ["font-weight: 700"] * len(row)
        return [""] * len(row)

    if frame.empty:
        st.info("Nothing matches that filter.")
    for make_name, group in frame.groupby("Make", sort=False):
        sold = int(group["Finance Gross"].notna().sum()) if "Finance Gross" in group.columns else 0
        st.markdown(
            f'<div class="make-bar">Make: {make_name} · Count: {len(group)}'
            + (f" · {sold} with sales" if sold else "")
            + "</div>",
            unsafe_allow_html=True,
        )
        shown = pd.concat([group, pd.DataFrame([average_row(group)])], ignore_index=True)
        styled = shown.style.format(formats, na_rep="").map(paint, subset=money_cols).apply(emphasize, axis=1)
        st.dataframe(styled, hide_index=True, use_container_width=True)

    st.download_button(
        "Download this view",
        data=frame.to_csv(index=False).encode(),
        file_name="super-helpful-sold-list.csv",
        mime="text/csv",
    )


def list_tab():
    current = current_list()
    archives = archived_lists()
    choices = []
    if current:
        choices.append(("current", f"Current · {str(current.get('saved_at', ''))[:16].replace('T', ' ')}"))
    for sheet in archives:
        choices.append((sheet["id"], f"Archive · {str(sheet.get('saved_at', sheet['id']))[:16].replace('T', ' ')}"))
    if not choices:
        st.info("No list has been published yet.")
        return
    if len(choices) > 1:
        labels = [item[1] for item in choices]
        label = st.selectbox("Week", labels)
        picked = choices[labels.index(label)][0]
    else:
        picked = choices[0][0]
    payload = current if picked == "current" else next(sheet for sheet in archives if sheet["id"] == picked)
    show_sheet(payload)


def upload_tab():
    password = upload_password()
    if password:
        entered = st.text_input("Upload password", type="password")
        if entered != password:
            st.caption("This tab is just for publishing a new week. Everyone else can stay on Sold list.")
            if entered:
                st.error("Wrong password.")
            return
    else:
        st.warning("No upload password is set. Add UPLOAD_PASSWORD in Streamlit secrets before you share this app.")

    st.write("Inventory is the master file. The sales report replaces retail and adds commission, house, and finance gross.")
    inventory = st.file_uploader("Sold inventory", type=["csv", "xlsx", "xls"])
    sales = st.file_uploader("Vehicle sales report", type=["csv", "xlsx", "xls"])
    if st.button("Publish week", type="primary", disabled=not (inventory and sales)):
        try:
            rows, inventory_count, sales_count = rows_from_uploads(inventory.getvalue(), inventory.name, sales.getvalue(), sales.name)
        except Exception as error:
            st.error(str(error))
            return
        had_current = current_list() is not None
        publish(rows, inventory.name, sales.name)
        matched = sum(1 for row in rows if row.get("matched"))
        if had_current:
            st.success(f"Published {inventory_count} vehicles, {matched} matched to {sales_count} sales. The previous week is in the archive.")
        else:
            st.success(f"Published {inventory_count} vehicles, {matched} matched to {sales_count} sales.")
        st.rerun()


st.markdown(
    """
    <div class="app-title">Super Helpful Sold List</div>
    <div class="app-rule"></div>
    <div class="app-sub">Inventory is the master list. A matching stock number replaces retail and adds commission, house, and finance gross.</div>
    """,
    unsafe_allow_html=True,
)
sold_tab, new_tab = st.tabs(["Sold list", "Upload"])
with sold_tab:
    list_tab()
with new_tab:
    upload_tab()
