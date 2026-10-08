"""Join weekly sold inventory with the vehicle sales report."""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from io import BytesIO

import pandas as pd

EXCEL_EPOCH = datetime(1899, 12, 30)


def stock_key(value) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip().upper()


def _blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip() == "" or str(value).strip().lower() == "nan"


def _whole(value):
    number = num(value) if not isinstance(value, (int, float)) else value
    if number is None or (isinstance(number, float) and math.isnan(number)):
        return None
    if float(number).is_integer():
        return int(number)
    return number


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
            "mileage": _whole(num(_pick(row, ["mileage", "odometer"]))),
            "exterior": str(_pick(row, ["exterior color", "exterior", "ext color"])).strip(),
            "interior": str(_pick(row, ["interior color", "interior", "int color"])).strip(),
            "web_price": num(_pick(row, ["web price"])),
            "retail": num(_pick(row, ["retail price", "retail"])),
            "age": age_days(_pick(row, ["age"])),
        }
        if item["stock"] or item["vin"] or item["make"]:
            mapped.append(item)
    return mapped


SALESPEOPLE = {
    "1": "Joe Gorbecki",
    "6": "Johnny Monell",
    "7": "Mike Bowe",
    "8": "House",
    "11": "Jeff Ferry",
    "15": "Miriam Rodriguez",
    "16": "Jim Bozsar",
    "21": "Miguel Luevano",
    "36": "Alex Pierre",
    "54": "Thery Sanon",
    "67": "Daniel D Regan",
    "78": "Antonia Clark",
    "90": "Christopher Foody",
    "162": "Eric Wilson",
    "179": "Corey Regalado",
    "267": "Ryan Lawson",
    "272": "David",
    "278": "Nicole L",
    "288": "Steve Magura",
    "380": "Kile Coty",
    "412": "Micheal Matos",
    "421": "Marcus Anderson",
    "423": "ABW423",
    "425": "Amy Castiello",
    "426": "Michael Eliasson",
    "431": "Frederick Hayden",
    "456": "Andre",
    "479": "Kent Kuzmech",
    "489": "Alexander V Vilanova",
    "498": "Eric Lindahl",
    "507": "Nicholas Demers",
    "511": "Benjamin Diaz",
    "537": "Diana Maione",
    "557": "Henry Reyes",
    "565": "Andy Inginac",
    "579": "Anna Gill",
    "582": "Paulo Pelosi",
    "607": "Mona Orsulich",
    "608": "Mat Datin",
    "612": "Steeve Francois",
    "613": "Sarah Rouillard",
    "614": "Nora C Delavega",
    "624": "Oscar Coriza",
    "627": "Fredro",
    "629": "Luis M Vega",
    "630": "Rachel Seavey",
    "631": "Margarita Tejada Cor",
    "635": "Marci Rosenbaum",
    "636": "Danankah Jones",
    "639": "Briana Brown",
    "641": "Cristobal Millan Jr",
    "647": "Joshua Rippe",
    "648": "Jeffrey Laroche",
    "650": "Aung T Phyo",
    "652": "Jean Pierre",
    "661": "Jeremiah Green",
    "662": "Eliani Hoyt",
    "665": "Miguel Blanchette",
    "667": "Paul Ciocca",
    "668": "Emmanuel Nanadoum",
    "669": "Fabio",
    "670": "Stevens Rodney",
    "671": "Tanisha Waller",
    "672": "Nicole Brown",
    "673": "Yarisbeth Cotto",
    "675": "Steve Malave",
    "680": "Jessica Colon",
    "694": "Jael Cordero",
    "696": "Paul",
    "697": "Michaelangelo Casano",
    "698": "Matthew Datin",
    "701": "Daxx Hemod",
    "707": "Charmesha Satawhite",
    "708": "George Rodriguez",
    "709": "Freddie Calderon",
    "718": "Robert Cullen",
    "731": "Meggan Tardiff",
    "732": "Atenea Santana Hevia",
    "733": "Thomas Tramazzo",
    "734": "Honorata Pustelny",
    "739": "Freedom Miller",
    "741": "David Garcia",
    "743": "Gregory West",
    "744": "Matthew Johnson",
    "748": "Matt King",
    "750": "Anna Rose Maresca",
    "759": "Christian Rosario",
    "767": "Patricia Oddon",
    "768": "Brianna Grant",
    "789": "Christian Pacheco",
    "796": "Elvis Miha",
    "815": "M.Lee Bulluss",
    "823": "Phillip Donofrio",
    "830": "Nicole H Lago",
    "836": "Andre Salazar",
    "837": "David Esangbedo",
    "842": "Sahill Gafar",
    "848": "Jerry Kamilani",
    "854": "Kai Dowling",
    "855": "Patrick Brophy",
    "868": "David Bechta",
    "871": "Shawn Milburn",
    "874": "Rocardo Ocegueria",
    "881": "Steve Papadakos",
    "884": "Jaidon Beaudwin",
    "885": "Johny Monell 3",
    "894": "Varese Larue",
    "897": "Dylan Breutzmann",
    "900": "Emmanuel Nanadoum",
    "901": "Richie Hoyt",
    "903": "Eric Gonzalez",
    "907": "Dionis Castro",
    "909": "Joe Pralta",
    "916": "Raul Valdovinos",
    "917": "Ohanis Bonilla",
    "923": "Jeribeth Lopez",
    "931": "Lucas Cavaleanti",
    "932": "Joe Scott",
    "935": "Jeffrey Thayar",
    "936": "Elida Flores",
    "938": "Dylan Gagnon",
    "939": "Andrae Maitland",
    "940": "Ollie Civil",
    "942": "Eddie Colon",
    "948": "Sage Edwards",
    "950": "Ricardo Galiciaperra",
    "953": "Samuel Alvardo",
    "957": "Eric Crosby Williams",
    "959": "Angel Delossantos",
    "963": "Sara Xavier",
    "965": "Ryan Olphonce",
    "966": "Daniel Davy",
    "970": "Nestor Gonzalez",
    "974": "Anthony Estrella",
    "975": "Edel Ramirez",
    "978": "Conner Graham",
    "979": "Andrew Malak",
    "980": "William Tripp 111",
    "982": "Kristi Collaku",
    "983": "Rachel England",
}



def salesperson_name(value) -> str:
    text = str(value or "").strip()
    if not text or text.lower() == "none":
        return ""
    key = text.lstrip("0") or "0"
    if key in SALESPEOPLE:
        return SALESPEOPLE[key]
    if text.isdigit():
        return text
    return text


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
                "salesperson": salesperson_name(_pick(row, ["primary salespers", "primary salesperson", "salesperson"])),
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
