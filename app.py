"""Super Helpful Sold List. One file for Streamlit.

Install once:
    pip install streamlit pandas openpyxl

Run:
    streamlit run super-helpful-sold-list.py
"""

import json
import math
import os
import re
import sqlite3
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st


EXCEL_EPOCH = datetime(1899, 12, 30)


def stock_key(value) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip().upper()


def _blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip() == "" or str(value).strip().lower() == "nan"


def num(value):
    if _blank(value):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = str(value).replace("$", "").replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def age_days(value):
    if _blank(value):
        return None
    if isinstance(value, datetime):
        return None
    match = re.search(r"-?\d+", str(value))
    return int(match.group(0)) if match else None


def excel_date(value) -> str:
    if _blank(value):
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return (EXCEL_EPOCH + timedelta(days=float(value))).date().isoformat()
        except (OverflowError, ValueError):
            return ""
    text = str(value).strip()
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.notna(parsed) and len(text) > 6:
        return parsed.date().isoformat()
    return text[:10]


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", str(name).strip().lower())


def _pick(row: dict, names: list[str]):
    mapped = {_norm(key): value for key, value in row.items()}
    for name in names:
        value = mapped.get(name)
        if not _blank(value):
            return value
    return ""


def read_upload(raw: bytes, filename: str) -> list[dict]:
    name = filename.lower()
    if name.endswith(".csv"):
        frame = pd.read_csv(BytesIO(raw), dtype=str, keep_default_na=False)
    else:
        frame = pd.read_excel(BytesIO(raw))
    frame = frame.where(pd.notna(frame), "")
    return frame.to_dict(orient="records")


def map_inventory(rows: list[dict]) -> list[dict]:
    mapped = []
    for row in rows:
        item = {
            "stock": str(_pick(row, ["stock", "stock number", "stock #"])).strip(),
            "vin": str(_pick(row, ["vin"])).strip(),
            "year": _pick(row, ["year"]),
            "make": str(_pick(row, ["make"])).strip(),
            "model": str(_pick(row, ["model"])).strip(),
            "trim": str(_pick(row, ["trim"])).strip(),
            "type": str(_pick(row, ["type"])).strip(),
            "mileage": num(_pick(row, ["mileage", "odometer"])),
            "exterior": str(_pick(row, ["exterior color", "exterior", "ext color"])).strip(),
            "interior": str(_pick(row, ["interior color", "interior", "int color"])).strip(),
            "web_price": num(_pick(row, ["web price"])),
            "retail": num(_pick(row, ["retail price", "retail"])),
            "age": age_days(_pick(row, ["age"])),
        }
        if item["stock"] or item["vin"] or item["make"]:
            mapped.append(item)
    return mapped


def map_sales(rows: list[dict]) -> list[dict]:
    mapped = []
    for row in rows:
        stock = str(_pick(row, ["stock number", "stock", "stock #"])).strip()
        if not stock_key(stock) or stock_key(stock) == "NAN":
            continue
        mapped.append(
            {
                "stock": stock,
                "sale_date": excel_date(_pick(row, ["sale date"])),
                "salesperson": str(_pick(row, ["primary salespers", "primary salesperson", "salesperson"])).strip(),
                "buyer": str(_pick(row, ["full name", "buyer", "customer"])).strip(),
                "retail": num(_pick(row, ["retail price", "retail"])),
                "comm": num(_pick(row, ["comm gross", "comm. gross", "commission gross"])),
                "house": num(_pick(row, ["house gross"])),
                "apr": num(_pick(row, ["apr"])),
                "term": num(_pick(row, ["term"])),
            }
        )
    return mapped


def _latest_sales(rows: list[dict]) -> dict[str, dict]:
    by_stock: dict[str, dict] = {}
    for row in rows:
        key = stock_key(row["stock"])
        prev = by_stock.get(key)
        if prev is None or row["sale_date"] >= prev["sale_date"]:
            by_stock[key] = row
    return by_stock


def build_list(inventory: list[dict], sales: list[dict]) -> list[dict]:
    by_stock = _latest_sales(sales)
    listed = []
    for inv in inventory:
        sale = by_stock.get(stock_key(inv["stock"]))
        matched = sale is not None
        retail = sale["retail"] if matched and sale["retail"] is not None else inv["retail"]
        comm = sale["comm"] if matched else None
        house = sale["house"] if matched else None
        if not matched or (house is None and comm is None):
            finance = None
        else:
            finance = float(house or 0) - float(comm or 0)
        listed.append(
            {
                **inv,
                "retail": retail,
                "retail_source": "sales report" if matched and sale["retail"] is not None else "inventory",
                "matched": matched,
                "comm": comm,
                "house": house,
                "finance": finance,
                "sale_date": sale["sale_date"] if matched else "",
                "salesperson": sale["salesperson"] if matched else "",
                "buyer": sale["buyer"] if matched else "",
            }
        )
    listed.sort(key=lambda row: (row["make"].casefold(), row["model"].casefold(), row["stock"]))
    return listed


def rows_from_uploads(inventory_bytes: bytes, inventory_name: str, sales_bytes: bytes, sales_name: str):
    inventory = map_inventory(read_upload(inventory_bytes, inventory_name))
    sales = map_sales(read_upload(sales_bytes, sales_name))
    if not inventory:
        raise ValueError("No vehicle rows found in the inventory file.")
    if not sales:
        raise ValueError("No stock numbers found in the sales report.")
    return build_list(inventory, sales), len(inventory), len(sales)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DB = DATA / "sold_list.db"


def connect() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS weeks (
            id INTEGER PRIMARY KEY,
            saved_at TEXT,
            inventory_file TEXT,
            sales_file TEXT,
            vehicle_count INTEGER,
            rows_json TEXT,
            is_current INTEGER
        )
        """
    )
    conn.commit()
    return conn


def _payload(row) -> dict:
    return {
        "id": str(row[0]),
        "saved_at": row[1],
        "inventory_file": row[2],
        "sales_file": row[3],
        "vehicle_count": row[4],
        "rows": json.loads(row[5] or "[]"),
    }


def current_list() -> dict | None:
    conn = connect()
    row = conn.execute(
        "SELECT id, saved_at, inventory_file, sales_file, vehicle_count, rows_json FROM weeks WHERE is_current = 1 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return _payload(row) if row else None


def archived_lists() -> list[dict]:
    conn = connect()
    rows = conn.execute(
        "SELECT id, saved_at, inventory_file, sales_file, vehicle_count, rows_json FROM weeks WHERE is_current = 0 ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return [_payload(row) for row in rows]


def publish(rows: list[dict], inventory_file: str, sales_file: str) -> dict:
    saved_at = datetime.now().isoformat(timespec="seconds")
    conn = connect()
    conn.execute("UPDATE weeks SET is_current = 0 WHERE is_current = 1")
    conn.execute(
        "INSERT INTO weeks (saved_at, inventory_file, sales_file, vehicle_count, rows_json, is_current) VALUES (?, ?, ?, ?, ?, 1)",
        (saved_at, inventory_file, sales_file, len(rows), json.dumps(rows)),
    )
    conn.commit()
    conn.close()
    return {
        "saved_at": saved_at,
        "inventory_file": inventory_file,
        "sales_file": sales_file,
        "vehicle_count": len(rows),
        "rows": rows,
    }

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
        keep += ["Sale Date", "Buyer", "Salesperson"]
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


def show_sheet(payload: dict):
    rows = payload.get("rows") or []
    if not rows:
        st.info("No list yet. The upload tab is where a new week gets published.")
        return

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

    left, make_col, model_col, right = st.columns([2, 1, 1, 1])
    query = left.text_input("Search", placeholder="Stock, VIN, make, model, buyer", key="sold_search")
    makes = ["All makes"] + sorted({row.get("make") or "" for row in rows if row.get("make")})
    make = make_col.selectbox("Make", makes, key="sold_make")
    model_rows = rows if make == "All makes" else [row for row in rows if row.get("make") == make]
    models = ["All models"] + sorted({str(row.get("model") or "").strip() for row in model_rows if str(row.get("model") or "").strip()})
    if st.session_state.get("sold_model") not in models:
        st.session_state["sold_model"] = "All models"
    model = model_col.selectbox("Model", models, key="sold_model")
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
    scope = " · ".join(part for part in [make if make != "All makes" else "", model if model != "All models" else ""] if part)
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
