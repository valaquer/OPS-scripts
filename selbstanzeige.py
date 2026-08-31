#!/usr/bin/env python3
"""Acorn KAPitan -- FIFO recalculation engine + tax calculation for Selbstanzeige.

Replicates meinKAPitan.de output from DEGIRO CSV exports, then calculates
total tax liability (Mehrsteuern + Zinsen + Soli) for the Selbstanzeige.
All config from Bear notes, all output to Bear.
"""

import csv
import math
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path

# ── Module 0: Bear Reader/Writer ──

IMAC_SSH_OPTS = [
    "ssh", "-o", "ControlMaster=auto",
    "-o", "ControlPath=/tmp/bear-watcher-ssh",
    "-o", "ControlPersist=300",
    "-o", "ConnectTimeout=3",
    "-o", "BatchMode=yes",
    "imac",
]
IMAC_BEAR_DB = r"~/Library/Group\ Containers/9K33E3U3T4.net.shinyfrog.bear/Application\ Data/database.sqlite"


def bear_ssh_query(sql: str) -> str:
    result = subprocess.run(
        IMAC_SSH_OPTS + [f"sqlite3 -separator '|' {IMAC_BEAR_DB} \"{sql}\""],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Bear query failed: {result.stderr.strip()}")
    return result.stdout


def read_bear_note(title: str) -> str:
    safe_title = title.replace("'", "''")
    sql = f"SELECT ZTEXT FROM ZSFNOTE WHERE ZTITLE = '{safe_title}' AND ZTRASHED = 0"
    output = bear_ssh_query(sql)
    if not output.strip():
        raise ValueError(f"Bear config note not found: '{title}'")
    return output.strip()


def parse_bear_table(text: str) -> list[dict]:
    lines = text.strip().split("\n")
    table_lines = []
    for line in lines:
        stripped = line.strip()
        if "|" in stripped and not re.match(r"^\s*\|[\s\-:|]+\|\s*$", stripped):
            table_lines.append(stripped)
    if len(table_lines) < 2:
        return []
    header = [c.strip() for c in table_lines[0].split("|") if c.strip()]
    rows = []
    for line in table_lines[1:]:
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) >= len(header):
            rows.append(dict(zip(header, cells[:len(header)])))
    return rows


def _parse_date(s: str) -> str:
    s = s.strip()
    if re.match(r"\d{2}\.\d{2}\.\d{4}", s):
        d, m, y = s.split(".")
        return f"{y}-{m}-{d}"
    return s


def parse_bear_kv(text: str) -> dict:
    result = {}
    for match in re.finditer(r"\*\*(.+?):\*\*\s*(.+)", text):
        result[match.group(1).strip()] = match.group(2).strip()
    return result


def find_bear_note_id(title: str, tag: str) -> "str | None":
    safe_title = title.replace("'", "''")
    tag_leaf = tag.rstrip("#").split("/")[-1]
    safe_tag = tag_leaf.replace("'", "''")
    sql = (
        f"SELECT n.ZUNIQUEIDENTIFIER FROM ZSFNOTE n "
        f"JOIN Z_5TAGS nt ON n.Z_PK = nt.Z_5NOTES "
        f"JOIN ZSFNOTETAG t ON t.Z_PK = nt.Z_13TAGS "
        f"WHERE n.ZTITLE = '{safe_title}' AND t.ZTITLE LIKE '%{safe_tag}%' "
        f"AND n.ZTRASHED = 0 LIMIT 1"
    )
    try:
        result = bear_ssh_query(sql)
        uid = result.strip()
        return uid if uid else None
    except Exception:
        return None


def bear_write_note(title: str, body: str, tag: str):
    encoded_title = urllib.parse.quote(title)
    encoded_tag = urllib.parse.quote(tag)
    encoded_body = urllib.parse.quote(body)
    existing_id = find_bear_note_id(title, tag)
    if existing_id:
        write_url = f"bear://x-callback-url/add-text?id={existing_id}&text={encoded_body}&mode=replace_all&open_note=no"
    else:
        create_url = f"bear://x-callback-url/create?title={encoded_title}&tags={encoded_tag}&open_note=no"
        subprocess.run(
            IMAC_SSH_OPTS + [f"open -g '{create_url}'"],
            capture_output=True, text=True, timeout=10,
        )
        time.sleep(0.5)
        write_url = f"bear://x-callback-url/add-text?title={encoded_title}&text={encoded_body}&mode=replace_all&open_note=no"
    subprocess.run(
        IMAC_SSH_OPTS + [f"open -g '{write_url}'"],
        capture_output=True, text=True, timeout=10,
    )


# ── Module 1: Configuration from Bear ──

FELIX_DIR = Path(os.path.expanduser("~/honeybloom/felix/postal-mail"))
TRANSACTIONS_CSV = FELIX_DIR / "Degiro Transactions.csv"
ACCOUNT_CSV = FELIX_DIR / "Degiro Account.csv"
ECB_RATES_CACHE = FELIX_DIR / "ecb-eurusd-daily.csv"

ECB_URL = "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?format=csvdata"


def load_bear_config():
    cfg = {}

    note = read_bear_note("Acorn Config -- ISIN Classifications")
    rows = parse_bear_table(note)
    fund_isins = {}
    for r in rows:
        isin = r.get("ISIN", "")
        if isin:
            fund_isins[isin] = {
                "name": r.get("Name", ""),
                "type": r.get("Type", "other"),
                "tf": float(r.get("TF", "0")),
            }
    cfg["fund_isins"] = fund_isins

    note = read_bear_note("Acorn Config -- Fund Parameters")
    kv = parse_bear_kv(note)
    basiszins = {}
    for key, val in kv.items():
        m = re.match(r"Basiszins (\d{4})", key)
        if m:
            basiszins[int(m.group(1))] = float(val.replace("%", "")) / 100
    cfg["basiszins"] = basiszins

    rows = parse_bear_table(note)
    vp_data = {}
    fd_data = {}
    old_invstg = {}
    for r in rows:
        section = r.get("Section", "")
        if section == "VP":
            year = int(r["Year"])
            isin = r["ISIN"]
            if year not in vp_data:
                vp_data[year] = {}
            vp_data[year][isin] = {
                "jan1_value_eur": float(r["Jan1Value"]),
                "distributions_eur": float(r["Distributions"]),
            }
        elif section == "FD":
            isin = r["ISIN"]
            fd_data[isin] = {
                "qty": float(r["Qty"]),
                "market_value_eur": float(r["MarketValue"]),
            }
        elif section == "OLD":
            isin = r["ISIN"]
            old_invstg[isin] = {
                "name": r.get("Name", ""),
                "qty": float(r["Qty"]),
                "cost_eur": float(r["Cost"]),
                "dec31_value_eur": float(r["Dec31Value"]),
            }
    cfg["vp_data"] = vp_data
    cfg["fictional_disposal"] = fd_data
    cfg["old_invstg"] = old_invstg

    note = read_bear_note("Acorn Config -- Interest and Surcharges")
    kv = parse_bear_kv(note)
    cfg["rate_233a"] = float(kv.get("§233a Rate", "1.8")) / 100
    cfg["rate_235"] = float(kv.get("§235 Rate", "6.0")) / 100
    cfg["dba_rate_us"] = float(kv.get("DBA US Rate", "15")) / 100
    cfg["dba_rate_india"] = float(kv.get("DBA India Rate", "10")) / 100

    karenz_rows = parse_bear_table(note)
    karenzzeiten = {}
    for r in karenz_rows:
        if "Year" in r and "Zinslaufbeginn" in r:
            try:
                karenzzeiten[int(r["Year"])] = r["Zinslaufbeginn"]
            except ValueError:
                pass
    cfg["karenzzeiten"] = karenzzeiten

    surcharge_brackets = []
    for key, val in kv.items():
        m = re.match(r"Surcharge (\d+)", key)
        if m:
            surcharge_brackets.append({
                "threshold": float(m.group(1)),
                "rate": float(val.replace("%", "")) / 100,
            })
    cfg["surcharge_brackets"] = surcharge_brackets

    kv2 = parse_bear_kv(note)
    cfg["payment_date"] = kv2.get("Payment Date", "2026-10-01")

    note = read_bear_note("Acorn Config -- Tax Formulas")
    tax_rows = parse_bear_table(note)
    tariffs = {}
    soli_freigrenze = {}
    sparer_pb = {}
    milderungszone = {}
    for r in tax_rows:
        if "GF" in r and "Year" in r:
            year = int(r["Year"])
            tariffs[year] = {
                "gf": float(r["GF"]),
                "z2e": float(r["Z2E"]),
                "z3e": float(r["Z3E"]),
                "z4e": float(r["Z4E"]),
                "a": float(r["a"]),
                "b": float(r["b"]),
                "c": float(r["c"]),
                "d": float(r["d"]),
                "e": float(r["e"]),
                "r1": float(r["r1"]),
                "f1": float(r["f1"]),
                "r2": float(r["r2"]),
                "f2": float(r["f2"]),
            }
        if "SoliFreigrenze" in r and "Year" in r:
            year = int(r["Year"])
            soli_freigrenze[year] = float(r["SoliFreigrenze"])
        if "SparerPB" in r and "Year" in r:
            year = int(r["Year"])
            sparer_pb[year] = float(r["SparerPB"])
        if "Milderungszone" in r and "Year" in r:
            year = int(r["Year"])
            milderungszone[year] = float(r["Milderungszone"]) / 100
    cfg["tariffs"] = tariffs
    cfg["soli_freigrenze"] = soli_freigrenze
    cfg["sparer_pb"] = sparer_pb
    cfg["milderungszone"] = milderungszone

    note = read_bear_note("Acorn Config -- Bescheid Baselines")
    bescheid_rows = parse_bear_table(note)
    bescheide = {}
    for r in bescheid_rows:
        year = int(r["Year"])
        bescheide[year] = {
            "zve": float(r.get("zvE", "0").replace(",", "")),
            "est": float(r.get("ESt", "0").replace(",", "")),
            "soli": float(r.get("Soli", "0").replace(",", "")),
            "tarif": r.get("Tarif", "Splittingtarif"),
            "erlassdatum": _parse_date(r.get("Erlassdatum", "")),
        }
    cfg["bescheide"] = bescheide

    note = read_bear_note("Acorn Config -- India Interest")
    india_rows = parse_bear_table(note)
    india = {}
    for r in india_rows:
        if "Year" in r:
            year = int(r["Year"])
            india[year] = {
                "interest_eur": float(r.get("Interest EUR", "0")),
                "tds_eur": float(r.get("TDS EUR", "0")),
            }
    cfg["india"] = india

    return cfg


# ── Module 2: Data Normalization ──

def parse_date(s: str) -> str:
    parts = s.strip().split("-")
    if len(parts[0]) == 2:
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return s


def parse_decimal(s: str) -> float:
    if not s or not s.strip():
        return 0.0
    s = s.strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def load_transactions(path: Path) -> list[dict]:
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            if len(row) < 17:
                continue
            date = parse_date(row[0])
            isin = row[3].strip()
            qty = parse_decimal(row[6])
            price = parse_decimal(row[7])
            price_ccy = row[8].strip()
            local_value = parse_decimal(row[9])
            local_ccy = row[10].strip()
            value_eur = parse_decimal(row[11])
            fx_rate = parse_decimal(row[12])
            autofx_fee = parse_decimal(row[13])
            fees_eur = parse_decimal(row[14])
            total_eur = parse_decimal(row[15])
            rows.append({
                "date": date, "isin": isin, "qty": qty,
                "price": price, "price_ccy": price_ccy or local_ccy,
                "local_value": local_value, "value_eur": value_eur,
                "fx_rate": fx_rate, "autofx_fee": autofx_fee,
                "fees_eur": fees_eur, "total_eur": total_eur,
            })
    rows.sort(key=lambda r: r["date"])
    return rows


def load_account(path: Path) -> list[dict]:
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            if len(row) < 10:
                continue
            date = parse_date(row[0])
            product = row[3].strip()
            isin = row[4].strip()
            desc = row[5].strip()
            change_ccy = row[7].strip()
            change_amt = parse_decimal(row[8])
            rows.append({
                "date": date, "product": product, "isin": isin,
                "desc": desc, "change": change_amt, "ccy": change_ccy,
            })
    rows.sort(key=lambda r: r["date"])
    return rows


# ── Module 3: ECB Daily Rates ──

def download_ecb_rates(cache_path: Path) -> dict[str, float]:
    if cache_path.exists():
        age_hours = (datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)).total_seconds() / 3600
        if age_hours < 24 * 7:
            return _parse_ecb_csv(cache_path.read_text())

    print("Downloading ECB EUR/USD daily rates...", file=sys.stderr)
    req = urllib.request.urlopen(ECB_URL, timeout=30)
    data = req.read().decode("utf-8")
    cache_path.write_text(data)
    return _parse_ecb_csv(data)


def _parse_ecb_csv(data: str) -> dict[str, float]:
    rates = {}
    reader = csv.DictReader(StringIO(data))
    for row in reader:
        date_str = row.get("TIME_PERIOD", "").strip()
        value_str = row.get("OBS_VALUE", "").strip()
        if date_str and value_str:
            try:
                rates[date_str] = float(value_str)
            except ValueError:
                pass
    return rates


def get_ecb_rate(rates: dict[str, float], date_str: str) -> float:
    d = datetime.strptime(date_str, "%Y-%m-%d")
    for _ in range(10):
        key = d.strftime("%Y-%m-%d")
        if key in rates:
            return rates[key]
        d -= timedelta(days=1)
    raise ValueError(f"No ECB rate found near {date_str}")


def convert_to_eur(amount_usd: float, ecb_rates: dict[str, float], date: str) -> float:
    rate = get_ecb_rate(ecb_rates, date)
    return amount_usd / rate


# ── Module 4: ISIN Classification ──

CFG = {}  # populated by load_bear_config() in main


def is_fund(isin: str) -> bool:
    info = CFG.get("fund_isins", {}).get(isin)
    return info is not None and info.get("type") == "fund"


def get_teilfreistellung(isin: str) -> float:
    info = CFG.get("fund_isins", {}).get(isin)
    if info and info.get("type") == "fund":
        return info["tf"]
    return 0.0


def asset_category(isin: str) -> str:
    info = CFG.get("fund_isins", {}).get(isin)
    if info and info.get("type") == "fund":
        return "fund"
    return "stock"


# ── Module 5: FIFO Engine ──

class FIFOQueue:
    def __init__(self):
        self.tranches: list[dict] = []

    def buy(self, date: str, qty: float, cost_eur: float, fees_eur: float):
        cost_per_unit = (abs(cost_eur) + abs(fees_eur)) / abs(qty) if qty != 0 else 0
        self.tranches.append({
            "date": date, "qty": abs(qty), "cost_per_unit": cost_per_unit,
        })

    def sell(self, date: str, qty: float, proceeds_eur: float, fees_eur: float) -> list[dict]:
        sell_qty = abs(qty)
        net_proceeds = abs(proceeds_eur) - abs(fees_eur)
        proceeds_per_unit = net_proceeds / sell_qty if sell_qty > 0 else 0

        gains = []
        remaining = sell_qty
        while remaining > 0.0001 and self.tranches:
            tranche = self.tranches[0]
            consumed = min(remaining, tranche["qty"])
            gain = (proceeds_per_unit - tranche["cost_per_unit"]) * consumed
            gains.append({
                "buy_date": tranche["date"], "sell_date": date,
                "qty": consumed, "cost": tranche["cost_per_unit"] * consumed,
                "proceeds": proceeds_per_unit * consumed, "gain": gain,
            })
            tranche["qty"] -= consumed
            remaining -= consumed
            if tranche["qty"] < 0.0001:
                self.tranches.pop(0)
        return gains

    def holdings(self) -> float:
        return sum(t["qty"] for t in self.tranches)

    def cost_basis(self) -> float:
        return sum(t["qty"] * t["cost_per_unit"] for t in self.tranches)

    def split(self, ratio: float):
        for t in self.tranches:
            t["qty"] *= ratio
            t["cost_per_unit"] /= ratio


def is_stock_split(txns: list[dict], idx: int) -> tuple[bool, int]:
    if idx + 1 >= len(txns):
        return False, 0
    t1, t2 = txns[idx], txns[idx + 1]
    if t1["isin"] != t2["isin"] or t1["date"] != t2["date"]:
        return False, 0
    sell, buy = None, None
    if t1["qty"] < 0 and t2["qty"] > 0:
        sell, buy = t1, t2
    elif t1["qty"] > 0 and t2["qty"] < 0:
        sell, buy = t2, t1
    else:
        return False, 0
    sell_val = abs(sell["value_eur"])
    buy_val = abs(buy["value_eur"])
    if sell_val > 0 and abs(sell_val - buy_val) / sell_val < 0.01:
        ratio = abs(buy["qty"]) / abs(sell["qty"])
        if ratio > 1.5:
            return True, ratio
    return False, 0


# ── Module 6: InvStG Transition ──

def compute_2017_old_invstg() -> dict:
    results = {}
    for isin, data in CFG.get("old_invstg", {}).items():
        value_increase = data["dec31_value_eur"] - data["cost_eur"]
        pauschal_70pct = max(0, value_increase * 0.70)
        pauschal_6pct = data["dec31_value_eur"] * 0.06
        taxable = max(pauschal_70pct, pauschal_6pct)
        results[isin] = {
            "name": data["name"],
            "cost": data["cost_eur"],
            "dec31_value": data["dec31_value_eur"],
            "value_increase": round(value_increase, 2),
            "pauschal_70pct": round(pauschal_70pct, 2),
            "pauschal_6pct": round(pauschal_6pct, 2),
            "taxable": round(taxable, 2),
        }
    return results


def compute_vorabpauschale(year: int) -> float:
    bz = CFG.get("basiszins", {}).get(year, 0)
    if bz <= 0:
        return 0.0
    vp_data = CFG.get("vp_data", {}).get(year, {})
    if not vp_data:
        return 0.0
    total_vp = 0.0
    for isin, d in vp_data.items():
        basisertrag = d["jan1_value_eur"] * bz * 0.7
        vp = max(0, basisertrag - d["distributions_eur"])
        tf = get_teilfreistellung(isin)
        total_vp += vp * (1 - tf)
    return round(total_vp, 2)


# ── Module 7: Annual KAP Calculations ──

def extract_dividends(account_rows: list[dict], ecb_rates: dict[str, float]) -> list[dict]:
    divs = []
    div_map = {}
    tax_map = {}

    for row in account_rows:
        if "Dividend" in row["desc"] and "Tax" not in row["desc"]:
            key = (row["date"], row["isin"])
            div_map[key] = row
        elif "Dividend Tax" in row["desc"]:
            key = (row["date"], row["isin"])
            tax_map[key] = row

    for key, div_row in div_map.items():
        date, isin = key
        gross_amt = abs(div_row["change"])
        ccy = div_row["ccy"]
        tax_row = tax_map.get(key)
        wht_amt = abs(tax_row["change"]) if tax_row else 0.0

        if ccy == "USD":
            gross_eur = convert_to_eur(gross_amt, ecb_rates, date)
            wht_eur = convert_to_eur(wht_amt, ecb_rates, date)
        else:
            gross_eur = gross_amt
            wht_eur = wht_amt

        dba_rate = CFG.get("dba_rate_us", 0.15)
        creditable_wht = min(wht_eur, dba_rate * gross_eur)
        year = int(date[:4])
        tf = get_teilfreistellung(isin) if is_fund(isin) else 0.0

        divs.append({
            "date": date, "year": year, "isin": isin,
            "gross_eur": round(gross_eur, 2),
            "wht_eur": round(wht_eur, 2),
            "creditable_wht_eur": round(creditable_wht, 2),
            "teilfreistellung": tf,
            "taxable_eur": round(gross_eur * (1 - tf), 2),
            "category": asset_category(isin),
        })

    divs.sort(key=lambda d: d["date"])
    return divs


def compute_annual_summary(all_gains: list[dict], dividends: list[dict], year: int) -> dict:
    year_gains = [g for g in all_gains if int(g["sell_date"][:4]) == year]
    year_divs = [d for d in dividends if d["year"] == year]

    stock_gain_items = [g for g in year_gains if asset_category(g.get("isin", "")) == "stock" and g["gain"] >= 0]
    stock_loss_items = [g for g in year_gains if asset_category(g.get("isin", "")) == "stock" and g["gain"] < 0]

    stock_gains_total = sum(g["gain"] for g in stock_gain_items)
    stock_losses_total = sum(g["gain"] for g in stock_loss_items)

    stock_divs = [d for d in year_divs if d["category"] == "stock"]
    fund_divs = [d for d in year_divs if d["category"] == "fund"]

    stock_div_gross = sum(d["gross_eur"] for d in stock_divs)
    stock_div_wht = sum(d["creditable_wht_eur"] for d in stock_divs)
    fund_div_gross = sum(d["gross_eur"] for d in fund_divs)
    fund_div_taxable = sum(d["taxable_eur"] for d in fund_divs)
    fund_div_wht = sum(d["creditable_wht_eur"] for d in fund_divs)

    fund_gain_items = [g for g in year_gains if asset_category(g.get("isin", "")) == "fund"]
    fund_gains_raw = sum(g["gain"] for g in fund_gain_items)
    fund_tf_applied = {}
    for g in fund_gain_items:
        isin = g.get("isin", "")
        tf = get_teilfreistellung(isin)
        if isin not in fund_tf_applied:
            fund_tf_applied[isin] = {"gain_raw": 0, "tf": tf}
        fund_tf_applied[isin]["gain_raw"] += g["gain"]

    fund_gains_after_tf = sum(v["gain_raw"] * (1 - v["tf"]) for v in fund_tf_applied.values())

    vp = compute_vorabpauschale(year)

    return {
        "year": year,
        "stock_gains": round(stock_gains_total, 2),
        "stock_losses": round(stock_losses_total, 2),
        "stock_net": round(stock_gains_total + stock_losses_total, 2),
        "stock_div_gross": round(stock_div_gross, 2),
        "stock_div_wht_creditable": round(stock_div_wht, 2),
        "fund_gains_raw": round(fund_gains_raw, 2),
        "fund_gains_after_tf": round(fund_gains_after_tf, 2),
        "fund_div_gross": round(fund_div_gross, 2),
        "fund_div_taxable": round(fund_div_taxable, 2),
        "fund_div_wht_creditable": round(fund_div_wht, 2),
        "vorabpauschale": vp,
        "stock_taxable": round(stock_gains_total + stock_losses_total + stock_div_gross, 2),
        "fund_taxable": round(fund_gains_after_tf + fund_div_taxable + vp, 2),
    }


# ── Module 8: Tax Calculation ──

def compute_est_32a(zve: float, year: int, tarif: str = "Splittingtarif") -> float:
    t = CFG.get("tariffs", {}).get(year)
    if not t:
        raise ValueError(f"No §32a tariff parameters for {year}")

    if tarif == "Splittingtarif":
        return 2 * _est_grundtarif(zve / 2, t)
    return _est_grundtarif(zve, t)


def _est_grundtarif(zve: float, t: dict) -> float:
    zve = math.floor(zve)
    if zve <= t["gf"]:
        return 0.0
    elif zve <= t["z2e"]:
        y = (zve - t["gf"]) / 10000
        return math.floor((t["a"] * y + t["b"]) * y)
    elif zve <= t["z3e"]:
        z = (zve - t["z2e"]) / 10000
        return math.floor((t["c"] * z + t["d"]) * z + t["e"])
    elif zve <= t["z4e"]:
        return math.floor(t["r1"] * zve - t["f1"])
    else:
        return math.floor(t["r2"] * zve - t["f2"])


def compute_soli(est: float, year: int, tarif: str = "Splittingtarif") -> float:
    freigrenze = CFG.get("soli_freigrenze", {}).get(year, 0)
    if freigrenze > 0:
        if tarif == "Splittingtarif":
            freigrenze *= 2
        if est <= freigrenze:
            return 0.0
        mz_rate = CFG.get("milderungszone", {}).get(year, 0.119)
        milderung = (est - freigrenze) * mz_rate
        voll = est * 0.055
        return round(min(voll, milderung), 2)
    return round(est * 0.055, 2)


def compute_abgeltungssteuer(kapitalertraege: float, sparer_pb: float) -> dict:
    taxable = max(0, kapitalertraege - sparer_pb)
    est_anteil = round(taxable * 0.25, 2)
    soli_anteil = round(est_anteil * 0.055, 2)
    total = round(est_anteil + soli_anteil, 2)
    return {
        "kapitalertraege": round(kapitalertraege, 2),
        "sparer_pb": sparer_pb,
        "taxable_base": round(taxable, 2),
        "est": est_anteil,
        "soli": soli_anteil,
        "total": total,
        "effective_rate": 0.26375,
    }


def compute_guenstigerpruefung(
    kapitalertraege: float,
    bescheid_zve: float,
    bescheid_est: float,
    year: int,
    tarif: str,
    sparer_pb: float,
) -> dict:
    taxable_kap = max(0, kapitalertraege - sparer_pb)
    new_zve = bescheid_zve + taxable_kap
    new_est = compute_est_32a(new_zve, year, tarif)
    additional_est = new_est - bescheid_est
    new_soli = compute_soli(new_est, year, tarif)
    old_soli = compute_soli(bescheid_est, year, tarif)
    additional_soli = new_soli - old_soli
    total = round(additional_est + additional_soli, 2)
    return {
        "bescheid_zve": bescheid_zve,
        "bescheid_est": bescheid_est,
        "taxable_kap": round(taxable_kap, 2),
        "new_zve": round(new_zve, 2),
        "new_est": new_est,
        "additional_est": round(additional_est, 2),
        "old_soli": old_soli,
        "new_soli": new_soli,
        "additional_soli": round(additional_soli, 2),
        "total": total,
    }


def compute_tax_for_year(year: int, kap_summary: dict) -> dict:
    bescheid = CFG.get("bescheide", {}).get(year)
    if not bescheid:
        return {"year": year, "error": f"No Bescheid baseline for {year}"}

    tarif = bescheid.get("tarif", "Splittingtarif")

    stock_for_tax = max(0, kap_summary["stock_taxable"])
    stock_loss_carryforward = min(0, kap_summary["stock_taxable"])
    total_kapitalertraege = stock_for_tax + kap_summary["fund_taxable"]

    india_data = CFG.get("india", {}).get(year, {})
    india_interest = india_data.get("interest_eur", 0)
    india_tds = india_data.get("tds_eur", 0)
    total_kapitalertraege += india_interest

    sparer_pb = CFG.get("sparer_pb", {}).get(year, 0)

    abgelt = compute_abgeltungssteuer(total_kapitalertraege, sparer_pb)
    guenstiger = compute_guenstigerpruefung(
        total_kapitalertraege, bescheid["zve"], bescheid["est"],
        year, tarif, sparer_pb,
    )

    if guenstiger["total"] < abgelt["total"] and guenstiger["total"] >= 0:
        chosen_path = "guenstigerpruefung"
        mehrsteuern_est = guenstiger["additional_est"]
        mehrsteuern_soli = guenstiger["additional_soli"]
        mehrsteuern_total = guenstiger["total"]
        reasoning = (
            f"Günstigerprüfung chosen: EUR {guenstiger['total']:.2f} < "
            f"Abgeltungssteuer EUR {abgelt['total']:.2f}. "
            f"Marginal rate on KapErträge is below 26.375%."
        )
    else:
        chosen_path = "abgeltungssteuer"
        mehrsteuern_est = abgelt["est"]
        mehrsteuern_soli = abgelt["soli"]
        mehrsteuern_total = abgelt["total"]
        reasoning = (
            f"Abgeltungssteuer chosen: EUR {abgelt['total']:.2f} ≤ "
            f"Günstigerprüfung EUR {guenstiger['total']:.2f}. "
            f"Marginal rate exceeds 26.375% at zvE EUR {bescheid['zve']:,.0f}."
        )

    total_wht_creditable = kap_summary["stock_div_wht_creditable"] + kap_summary["fund_div_wht_creditable"]
    india_dba_credit = min(india_tds, india_interest * abgelt["effective_rate"])
    total_wht_creditable += india_dba_credit

    return {
        "year": year,
        "tarif": tarif,
        "kapitalertraege": round(total_kapitalertraege, 2),
        "india_interest": round(india_interest, 2),
        "india_tds": round(india_tds, 2),
        "india_dba_credit": round(india_dba_credit, 2),
        "sparer_pb": sparer_pb,
        "abgelt": abgelt,
        "guenstiger": guenstiger,
        "chosen_path": chosen_path,
        "reasoning": reasoning,
        "mehrsteuern_est": round(mehrsteuern_est, 2),
        "mehrsteuern_soli": round(mehrsteuern_soli, 2),
        "mehrsteuern_total": round(mehrsteuern_total, 2),
        "wht_creditable": round(total_wht_creditable, 2),
        "net_mehrsteuern": round(mehrsteuern_total - total_wht_creditable, 2),
        "bescheid": bescheid,
    }


# ── Module 9: Interest Calculation ──

def months_between(start_str: str, end_str: str) -> int:
    start = datetime.strptime(start_str, "%Y-%m-%d")
    end = datetime.strptime(end_str, "%Y-%m-%d")
    return max(0, (end.year - start.year) * 12 + (end.month - start.month))


def compute_233a_zinsen(mehrsteuern: float, year: int) -> dict:
    zinslaufbeginn = CFG.get("karenzzeiten", {}).get(year, "")
    payment_date = CFG.get("payment_date", "2026-10-01")
    if not zinslaufbeginn:
        return {"zinsen": 0, "months": 0, "note": f"No Karenzzeit for {year}"}
    months = months_between(zinslaufbeginn, payment_date)
    rate_monthly = CFG.get("rate_233a", 0.018) / 12
    zinsen = round(mehrsteuern * rate_monthly * months, 2)
    return {
        "zinsen": zinsen,
        "months": months,
        "zinslaufbeginn": zinslaufbeginn,
        "payment_date": payment_date,
        "rate_pa": CFG.get("rate_233a", 0.018),
        "rate_monthly": round(rate_monthly, 6),
    }


def compute_235_zinsen(mehrsteuern: float, year: int) -> dict:
    bescheid = CFG.get("bescheide", {}).get(year, {})
    erlassdatum = bescheid.get("erlassdatum", "")
    payment_date = CFG.get("payment_date", "2026-10-01")
    if not erlassdatum:
        return {"zinsen": 0, "months": 0, "note": f"No Erlassdatum for {year}"}
    months = months_between(erlassdatum, payment_date)
    rate_monthly = CFG.get("rate_235", 0.06) / 12
    zinsen = round(mehrsteuern * rate_monthly * months, 2)
    return {
        "zinsen": zinsen,
        "months": months,
        "erlassdatum": erlassdatum,
        "payment_date": payment_date,
        "rate_pa": CFG.get("rate_235", 0.06),
        "rate_monthly": round(rate_monthly, 6),
    }


def apply_235_4_credit(zinsen_233a: dict, zinsen_235: dict) -> dict:
    z233a = zinsen_233a.get("zinsen", 0)
    z235 = zinsen_235.get("zinsen", 0)
    credited = min(z233a, z235)
    net_235 = z235 - credited
    total = z233a + net_235
    return {
        "zinsen_233a_gross": z233a,
        "zinsen_235_gross": z235,
        "credited_233a": credited,
        "zinsen_235_net": net_235,
        "total_interest": round(total, 2),
        "explanation": (
            f"§235(4) credit: §233a EUR {z233a:.2f} credited against §235 EUR {z235:.2f}. "
            f"Net §235: EUR {net_235:.2f}. Total interest burden: EUR {total:.2f} "
            f"(capped at §235 rate of {zinsen_235.get('rate_pa', 0.06) * 100:.1f}% p.a. during overlap)."
        ),
    }


def check_398a(hinterzogene_steuer: float) -> dict:
    brackets = CFG.get("surcharge_brackets", [])
    if hinterzogene_steuer <= 25000:
        return {
            "applies": False,
            "surcharge": 0,
            "note": f"EUR {hinterzogene_steuer:,.2f} ≤ EUR 25,000 threshold. §371 strafbefreiende Selbstanzeige applies (full criminal immunity).",
        }
    rate = 0.10
    for bracket in sorted(brackets, key=lambda b: b["threshold"]):
        if hinterzogene_steuer <= bracket["threshold"]:
            break
        rate = bracket["rate"]
    surcharge = round(hinterzogene_steuer * rate, 2)
    return {
        "applies": True,
        "surcharge": surcharge,
        "rate": rate,
        "note": (
            f"EUR {hinterzogene_steuer:,.2f} > EUR 25,000. §398a applies. "
            f"Surcharge: {rate * 100:.0f}% × EUR {hinterzogene_steuer:,.2f} = EUR {surcharge:,.2f}."
        ),
    }


def compute_year_total(year: int, kap_summary: dict) -> dict:
    tax = compute_tax_for_year(year, kap_summary)
    if "error" in tax:
        return tax

    mehrsteuern = max(0, tax["net_mehrsteuern"])
    z233a = compute_233a_zinsen(mehrsteuern, year)
    z235 = compute_235_zinsen(mehrsteuern, year)
    credit = apply_235_4_credit(z233a, z235)
    s398a = check_398a(mehrsteuern)

    year_total = mehrsteuern + credit["total_interest"] + s398a["surcharge"]

    return {
        **tax,
        "zinsen_233a": z233a,
        "zinsen_235": z235,
        "zinsen_credit": credit,
        "s398a": s398a,
        "year_total": round(year_total, 2),
    }


# ── Module 10: Bear Output Writer ──

OUTPUT_TAG = "acorn/selbstanzeige/supplementary tax filing"


def write_year_note(year_result: dict):
    year = year_result["year"]
    title = f"Tax Calculation {year}"

    lines = []
    lines.append(f"### Tax Year {year}")
    lines.append("")

    if "error" in year_result:
        lines.append(f"**Error:** {year_result['error']}")
        bear_write_note(title, "\n".join(lines), OUTPUT_TAG)
        return

    b = year_result["bescheid"]
    lines.append("#### Original Bescheid")
    lines.append(f"**Tarif:** {year_result['tarif']}")
    lines.append(f"**zvE:** EUR {b['zve']:,.2f}")
    lines.append(f"**ESt:** EUR {b['est']:,.2f}")
    lines.append(f"**Soli:** EUR {b['soli']:,.2f}")
    if b.get("erlassdatum"):
        lines.append(f"**Erlassdatum:** {b['erlassdatum']}")
    lines.append("")

    lines.append("#### Added Kapitalertraege")
    lines.append(f"**Total Kapitalertraege:** EUR {year_result['kapitalertraege']:,.2f}")
    if year_result.get("india_interest", 0) > 0:
        lines.append(f"  of which India interest: EUR {year_result['india_interest']:,.2f} "
                      f"(TDS EUR {year_result['india_tds']:,.2f}, DBA credit EUR {year_result['india_dba_credit']:,.2f})")
    lines.append(f"**Sparerpauschbetrag:** EUR {year_result['sparer_pb']:,.2f}")
    lines.append("")

    lines.append("#### Path Comparison")
    a = year_result["abgelt"]
    lines.append(f"**Abgeltungssteuer:** EUR {a['total']:,.2f}")
    lines.append(f"  Taxable base: EUR {a['taxable_base']:,.2f} x 26.375% = EUR {a['total']:,.2f}")
    lines.append(f"  (25% ESt EUR {a['est']:,.2f} + 5.5% Soli EUR {a['soli']:,.2f})")
    lines.append("")

    g = year_result["guenstiger"]
    lines.append(f"**Guenstigerpruefung:** EUR {g['total']:,.2f}")
    lines.append(f"  Original zvE EUR {g['bescheid_zve']:,.2f} + KapErtraege EUR {g['taxable_kap']:,.2f} = new zvE EUR {g['new_zve']:,.2f}")
    lines.append(f"  New ESt: EUR {g['new_est']:,.2f} (was EUR {g['bescheid_est']:,.2f})")
    lines.append(f"  Additional ESt: EUR {g['additional_est']:,.2f}")
    lines.append(f"  Soli: EUR {g['new_soli']:,.2f} (was EUR {g['old_soli']:,.2f}), additional: EUR {g['additional_soli']:,.2f}")
    lines.append("")

    lines.append(f"**Chosen:** {year_result['reasoning']}")
    lines.append("")

    lines.append("#### Mehrsteuern")
    lines.append(f"**Additional ESt:** EUR {year_result['mehrsteuern_est']:,.2f}")
    lines.append(f"**Additional Soli:** EUR {year_result['mehrsteuern_soli']:,.2f}")
    lines.append(f"**Gross Mehrsteuern:** EUR {year_result['mehrsteuern_total']:,.2f}")
    lines.append(f"**WHT credited:** EUR {year_result['wht_creditable']:,.2f}")
    lines.append(f"**Net Mehrsteuern:** EUR {year_result['net_mehrsteuern']:,.2f}")
    lines.append("")

    z233a = year_result["zinsen_233a"]
    lines.append("#### §233a Nachzahlungszinsen")
    lines.append(f"**Rate:** {z233a.get('rate_pa', 0) * 100:.1f}% p.a. ({z233a.get('rate_monthly', 0) * 100:.4f}%/month)")
    lines.append(f"**Zinslaufbeginn:** {z233a.get('zinslaufbeginn', 'N/A')}")
    lines.append(f"**Payment date:** {z233a.get('payment_date', 'N/A')}")
    lines.append(f"**Months:** {z233a.get('months', 0)}")
    lines.append(f"**Zinsen:** EUR {z233a.get('zinsen', 0):,.2f}")
    lines.append("")

    z235 = year_result["zinsen_235"]
    lines.append("#### §235 Hinterziehungszinsen")
    lines.append(f"**Rate:** {z235.get('rate_pa', 0) * 100:.1f}% p.a. ({z235.get('rate_monthly', 0) * 100:.4f}%/month)")
    lines.append(f"**Erlassdatum (interest start):** {z235.get('erlassdatum', 'N/A')}")
    lines.append(f"**Payment date:** {z235.get('payment_date', 'N/A')}")
    lines.append(f"**Months:** {z235.get('months', 0)}")
    lines.append(f"**Zinsen:** EUR {z235.get('zinsen', 0):,.2f}")
    lines.append("")

    credit = year_result["zinsen_credit"]
    lines.append("#### §235(4) Credit")
    lines.append(credit["explanation"])
    lines.append("")

    s398a = year_result["s398a"]
    lines.append("#### §398a Check")
    lines.append(s398a["note"])
    lines.append("")

    lines.append("#### Year Total")
    lines.append(f"**Net Mehrsteuern:** EUR {max(0, year_result['net_mehrsteuern']):,.2f}")
    lines.append(f"**Interest (net):** EUR {credit['total_interest']:,.2f}")
    lines.append(f"**§398a surcharge:** EUR {s398a['surcharge']:,.2f}")
    lines.append(f"**Year total:** EUR {year_result['year_total']:,.2f}")

    bear_write_note(title, "\n".join(lines), OUTPUT_TAG)
    print(f"  Bear note written: {title}", file=sys.stderr)


def write_summary_note(year_results: list[dict]):
    title = "Tax Calculation -- Summary"
    lines = []
    lines.append("### Selbstanzeige -- Total Tax Liability")
    lines.append("")
    lines.append("| Year | Mehrsteuern | Interest | §398a | Year Total |")
    lines.append("|------|-----------|----------|-------|-----------|")

    grand_total = 0
    for yr in year_results:
        if "error" in yr:
            lines.append(f"| {yr['year']} | ERROR | -- | -- | -- |")
            continue
        mt = max(0, yr["net_mehrsteuern"])
        interest = yr["zinsen_credit"]["total_interest"]
        surcharge = yr["s398a"]["surcharge"]
        yt = yr["year_total"]
        grand_total += yt
        lines.append(f"| {yr['year']} | EUR {mt:,.2f} | EUR {interest:,.2f} | EUR {surcharge:,.2f} | EUR {yt:,.2f} |")

    lines.append(f"| **Total** | | | | **EUR {grand_total:,.2f}** |")
    lines.append("")
    lines.append(f"**Grand total payable:** EUR {grand_total:,.2f}")
    lines.append("")
    lines.append("This is the amount required to qualify for strafbefreiende Selbstanzeige under §371 AO "
                  "(or Absehen von Verfolgung under §398a if any single year exceeds EUR 25,000).")
    lines.append("")
    lines.append(f"**Payment date used:** {CFG.get('payment_date', 'N/A')}")
    lines.append("")
    lines.append("**Sources:** All figures traceable to DEGIRO CSVs (FIFO engine), ECB daily rates, "
                  "scanned Bescheide, and Bear config notes under #acorn/selbstanzeige/config#.")

    bear_write_note(title, "\n".join(lines), OUTPUT_TAG)
    print(f"  Bear note written: {title}", file=sys.stderr)


def write_input_data_note(all_gains: list[dict], dividends: list[dict], ecb_rates_used: set):
    title = "Input Data -- DEGIRO Transactions"
    lines = []
    lines.append("### DEGIRO Transaction Summary")
    lines.append("")
    lines.append(f"**Total trades processed:** {len(all_gains)}")
    lines.append(f"**Dividend events:** {len(dividends)}")
    lines.append(f"**ECB rates used:** {len(ecb_rates_used)} dates")
    lines.append("")
    lines.append("See selbstanzeige.py stdout output for full per-year Anlage KAP/KAP-INV figures.")
    bear_write_note(title, "\n".join(lines), OUTPUT_TAG)
    print(f"  Bear note written: {title}", file=sys.stderr)


# ── Main ──

def main():
    global CFG

    print("=" * 70)
    print("  Acorn KAPitan -- FIFO Recalculation + Tax Calculation Engine")
    print("=" * 70)
    print()

    print("Loading Bear config...", file=sys.stderr)
    try:
        CFG = load_bear_config()
        print(f"  Config loaded: {len(CFG.get('fund_isins', {}))} ISINs, "
              f"{len(CFG.get('tariffs', {}))} tariff years, "
              f"{len(CFG.get('bescheide', {}))} Bescheide", file=sys.stderr)
    except Exception as e:
        print(f"ERROR: Failed to load Bear config: {e}", file=sys.stderr)
        print("Ensure all Acorn Config notes exist in Bear under #acorn/selbstanzeige/config#", file=sys.stderr)
        sys.exit(1)

    txns = load_transactions(TRANSACTIONS_CSV)
    print(f"Loaded {len(txns)} transactions from {TRANSACTIONS_CSV.name}")

    account = load_account(ACCOUNT_CSV)
    print(f"Loaded {len(account)} account rows from {ACCOUNT_CSV.name}")

    ecb_rates = download_ecb_rates(ECB_RATES_CACHE)
    print(f"ECB rates: {len(ecb_rates)} daily rates loaded")
    print()

    queues: dict[str, FIFOQueue] = defaultdict(FIFOQueue)
    all_gains: list[dict] = []

    transition_done = False
    skip_next = False
    for i, txn in enumerate(txns):
        if skip_next:
            skip_next = False
            continue

        isin = txn["isin"]
        if not isin:
            continue

        if not transition_done and txn["date"] > "2017-12-31":
            transition_done = True
            for fd_isin, fd_data in CFG.get("fictional_disposal", {}).items():
                if fd_isin in queues and is_fund(fd_isin):
                    old_cost = queues[fd_isin].cost_basis()
                    new_cost_per_unit = fd_data["market_value_eur"] / fd_data["qty"]
                    queues[fd_isin].tranches.clear()
                    queues[fd_isin].tranches.append({
                        "date": "2017-12-31", "qty": fd_data["qty"],
                        "cost_per_unit": new_cost_per_unit,
                    })
                    print(f"  InvStG transition: {fd_isin} cost basis reset "
                          f"EUR {old_cost:.2f} -> EUR {fd_data['market_value_eur']:.2f}")

        split_detected, split_ratio = is_stock_split(txns, i)
        if split_detected:
            queues[isin].split(split_ratio)
            print(f"  Split detected: {isin} ratio {split_ratio:.0f}:1 on {txn['date']}")
            skip_next = True
            continue

        qty = txn["qty"]
        value_eur = txn["value_eur"]
        fees_eur = txn["fees_eur"]

        if value_eur == 0 and txn["price_ccy"] == "USD" and txn["local_value"] != 0:
            value_eur = convert_to_eur(abs(txn["local_value"]), ecb_rates, txn["date"])

        if qty > 0:
            queues[isin].buy(txn["date"], qty, value_eur, fees_eur)
        elif qty < 0:
            gains = queues[isin].sell(txn["date"], qty, value_eur, fees_eur)
            for g in gains:
                g["isin"] = isin
            all_gains.extend(gains)

    dividends = extract_dividends(account, ecb_rates)
    print(f"Extracted {len(dividends)} dividend events")
    print()

    # ── Anlage KAP / KAP-INV output (existing) ──

    print("-" * 70)
    print("  2017 -- Old InvStG §6 Pauschalbesteuerung")
    print("-" * 70)
    old_invstg = compute_2017_old_invstg()
    for isin, r in old_invstg.items():
        print(f"  {r['name']} ({isin})")
        print(f"    Purchase cost:         EUR {r['cost']:>10.2f}")
        print(f"    Dec 31, 2017 value:    EUR {r['dec31_value']:>10.2f}")
        print(f"    Value increase:        EUR {r['value_increase']:>10.2f}")
        print(f"    70% of increase:       EUR {r['pauschal_70pct']:>10.2f}")
        print(f"    6% of Dec 31 value:    EUR {r['pauschal_6pct']:>10.2f}")
        print(f"    Taxable (higher of):   EUR {r['taxable']:>10.2f}")
    print()

    years = sorted(set(int(g["sell_date"][:4]) for g in all_gains) | set(d["year"] for d in dividends))
    if old_invstg:
        years = sorted(set(years) | {2017})
    years = [y for y in years if 2017 <= y <= 2024]

    kap_summaries = {}
    for year in years:
        summary = compute_annual_summary(all_gains, dividends, year)
        if year == 2017 and old_invstg:
            old_invstg_total = sum(r["taxable"] for r in old_invstg.values())
            summary["fund_taxable"] = round(summary["fund_taxable"] + old_invstg_total, 2)
        kap_summaries[year] = summary
        print("-" * 70)
        print(f"  {year} -- Anlage KAP / KAP-INV Summary")
        print("-" * 70)

        print(f"  STOCKS (Anlage KAP):")
        print(f"    Realized gains:        EUR {summary['stock_gains']:>10.2f}")
        print(f"    Realized losses:       EUR {summary['stock_losses']:>10.2f}")
        print(f"    Net stock gain/loss:   EUR {summary['stock_net']:>10.2f}")
        print(f"    Dividends (gross):     EUR {summary['stock_div_gross']:>10.2f}")
        print(f"    WHT creditable:        EUR {summary['stock_div_wht_creditable']:>10.2f}")
        print(f"  STOCK BUCKET (Aktienverlusttopf):  EUR {summary['stock_taxable']:>10.2f}")
        if summary["stock_taxable"] < 0:
            print(f"    -> Stock loss carryforward (no cross-bucket offset)")
        print(f"  FUNDS (Anlage KAP-INV):")
        print(f"    Realized gains (raw):  EUR {summary['fund_gains_raw']:>10.2f}")
        print(f"    After Teilfreistellung:EUR {summary['fund_gains_after_tf']:>10.2f}")
        print(f"    Dividends (gross):     EUR {summary['fund_div_gross']:>10.2f}")
        print(f"    Dividends (taxable):   EUR {summary['fund_div_taxable']:>10.2f}")
        print(f"    WHT creditable:        EUR {summary['fund_div_wht_creditable']:>10.2f}")
        print(f"    Vorabpauschale:        EUR {summary['vorabpauschale']:>10.2f}")
        print(f"  FUND/OTHER BUCKET (taxable):       EUR {summary['fund_taxable']:>10.2f}")
        print()

    # ── Tax Calculation ──

    print("=" * 70)
    print("  Tax Calculation -- Selbstanzeige 2017-2024")
    print("=" * 70)
    print()

    year_results = []
    for year in years:
        if year not in kap_summaries:
            continue
        result = compute_year_total(year, kap_summaries[year])
        year_results.append(result)

        if "error" in result:
            print(f"  {year}: {result['error']}")
            continue

        print(f"  {year}: Mehrsteuern EUR {max(0, result['net_mehrsteuern']):>8.2f} | "
              f"Interest EUR {result['zinsen_credit']['total_interest']:>8.2f} | "
              f"§398a EUR {result['s398a']['surcharge']:>8.2f} | "
              f"Total EUR {result['year_total']:>8.2f}  [{result['chosen_path']}]")

    grand_total = sum(r.get("year_total", 0) for r in year_results if "error" not in r)
    print()
    print(f"  GRAND TOTAL: EUR {grand_total:,.2f}")
    print()

    # ── Write to Bear ──

    print("Writing Bear output notes...", file=sys.stderr)
    ecb_dates_used = set()
    for g in all_gains:
        ecb_dates_used.add(g.get("sell_date", ""))
        ecb_dates_used.add(g.get("buy_date", ""))

    write_input_data_note(all_gains, dividends, ecb_dates_used)
    for result in year_results:
        write_year_note(result)
    write_summary_note(year_results)

    print()
    print("=" * 70)
    print("  Notes:")
    print("  - FX rates: ECB daily reference rates (nearest prior business day)")
    print("  - FIFO: per ISIN, §20 Abs. 4 S. 7 EStG")
    print("  - Stock losses offset stock gains only (no cross-bucket)")
    print("  - 2017: old InvStG §6 Pauschalbesteuerung (intransparenter Fonds)")
    print("  - All config from Bear notes under #acorn/selbstanzeige/config#")
    print("  - Results written to Bear under #acorn/selbstanzeige/supplementary tax filing#")
    print("=" * 70)


if __name__ == "__main__":
    main()
