#!/usr/bin/env python3
"""
Momentum Strategy Scanner v2.1
================================
- India  : Full Nifty 500 — fetched live from NSE official source
- US     : Top 500 US stocks — S&P 500 + Nasdaq 100 (deduplicated, ~600 unique)
- Entry  : 90% / 100% / 110% of 52-week high (configurable per market)
- Exit   : 20% trailing stop loss from peak
- Fix    : auto_adjust=False to get real market prices (not dividend-adjusted)
"""

import json, os, sys, time, io
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import yfinance as yf
    import pytz
    import requests
    import pandas as pd
except ImportError:
    os.system("pip install yfinance pytz requests pandas -q")
    import yfinance as yf
    import pytz
    import requests
    import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# UNIVERSE FETCHERS
# ─────────────────────────────────────────────────────────────────────────────

def fetch_nifty500_from_nse() -> list:
    """
    Downloads official Nifty 500 constituent list from NSE India.
    Returns list of (symbol, company_name, sector) tuples.
    Falls back to hardcoded top-100 if NSE is unreachable.
    """
    print("  Fetching Nifty 500 list from NSE...", flush=True)
    try:
        url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.nseindia.com/",
        }
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        # NSE CSV columns: Company Name, Industry, Symbol, Series, ISIN Code
        df.columns = df.columns.str.strip()
        stocks = []
        for _, row in df.iterrows():
            sym = str(row.get("Symbol", "")).strip()
            name = str(row.get("Company Name", sym)).strip()
            sector = str(row.get("Industry", "Unknown")).strip()
            if sym and sym != "nan":
                stocks.append((sym, name, sector))
        print(f"  ✅ Nifty 500: {len(stocks)} stocks fetched from NSE", flush=True)
        return stocks
    except Exception as e:
        print(f"  ⚠️ NSE fetch failed ({e}) — using fallback list", flush=True)
        return get_nifty500_fallback()


def fetch_us500_universe() -> list:
    """
    Fetches S&P 500 from Wikipedia + Nasdaq 100 from Wikipedia.
    Combined and deduplicated = ~600 top US stocks by market cap.
    Returns list of (symbol, company_name, sector) tuples.
    """
    print("  Fetching US universe (S&P 500 + Nasdaq 100)...", flush=True)
    stocks_dict = {}  # symbol -> (name, sector)

    # ── S&P 500 from Wikipedia ──────────────────────────────────────
    try:
        sp500_url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        tables = pd.read_html(sp500_url, header=0)
        df = tables[0]
        df.columns = df.columns.str.strip()
        sym_col  = [c for c in df.columns if "Symbol" in c or "Ticker" in c][0]
        name_col = [c for c in df.columns if "Security" in c or "Name" in c][0]
        sec_col  = [c for c in df.columns if "GICS Sector" in c or "Sector" in c][0]
        for _, row in df.iterrows():
            sym = str(row[sym_col]).strip().replace(".", "-")
            if sym and sym != "nan":
                stocks_dict[sym] = (str(row[name_col]).strip(), str(row[sec_col]).strip())
        print(f"  S&P 500: {len(stocks_dict)} loaded", flush=True)
    except Exception as e:
        print(f"  ⚠️ S&P 500 fetch failed: {e}", flush=True)

    # ── Nasdaq 100 from Wikipedia ────────────────────────────────────
    try:
        ndx_url = "https://en.wikipedia.org/wiki/Nasdaq-100"
        tables = pd.read_html(ndx_url, header=0)
        # Find the table with ticker symbols
        for tbl in tables:
            cols = [str(c).lower() for c in tbl.columns]
            if any("ticker" in c or "symbol" in c for c in cols):
                sym_col  = tbl.columns[[i for i, c in enumerate(cols) if "ticker" in c or "symbol" in c][0]]
                name_col = tbl.columns[[i for i, c in enumerate(cols) if "company" in c or "name" in c][0]] if any("company" in c or "name" in c for c in cols) else sym_col
                for _, row in tbl.iterrows():
                    sym = str(row[sym_col]).strip().replace(".", "-")
                    if sym and sym != "nan" and len(sym) <= 6:
                        name = str(row[name_col]).strip() if name_col != sym_col else sym
                        stocks_dict.setdefault(sym, (name, "Technology"))
                print(f"  Nasdaq 100 added. Total US: {len(stocks_dict)}", flush=True)
                break
    except Exception as e:
        print(f"  ⚠️ Nasdaq 100 fetch failed: {e}", flush=True)

    # ── Extra high-conviction tech/AI stocks not in above lists ──────
    extra = [
        ("NVDA","NVIDIA","Semiconductors"), ("META","Meta Platforms","Technology"),
        ("TSLA","Tesla","Consumer Discretionary"), ("NFLX","Netflix","Communication"),
        ("PLTR","Palantir","Technology"), ("CRWD","CrowdStrike","Technology"),
        ("DDOG","Datadog","Technology"), ("SNOW","Snowflake","Technology"),
        ("NET","Cloudflare","Technology"), ("PANW","Palo Alto Networks","Technology"),
        ("ZS","Zscaler","Technology"), ("COIN","Coinbase","Financials"),
        ("HOOD","Robinhood","Financials"), ("SOFI","SoFi Technologies","Financials"),
        ("RBLX","Roblox","Communication"), ("UBER","Uber","Industrials"),
        ("ABNB","Airbnb","Consumer Discretionary"), ("DASH","DoorDash","Consumer Discretionary"),
        ("MELI","MercadoLibre","Consumer Discretionary"), ("SE","Sea Limited","Technology"),
        ("SHOP","Shopify","Technology"), ("GTLB","GitLab","Technology"),
        ("MDB","MongoDB","Technology"), ("TEAM","Atlassian","Technology"),
        ("MNDY","Monday.com","Technology"), ("PATH","UiPath","Technology"),
        ("S","SentinelOne","Technology"), ("CYBR","CyberArk","Technology"),
        ("IONQ","IonQ","Technology"), ("RGTI","Rigetti","Technology"),
        ("APP","AppLovin","Technology"), ("TTD","Trade Desk","Technology"),
        ("ENPH","Enphase Energy","Utilities"), ("FSLR","First Solar","Utilities"),
    ]
    for sym, name, sec in extra:
        stocks_dict.setdefault(sym, (name, sec))

    result = [(sym, info[0], info[1]) for sym, info in stocks_dict.items()]

    if not result:
        print("  ⚠️ All US fetches failed — using fallback", flush=True)
        return get_us500_fallback()

    print(f"  ✅ US universe: {len(result)} stocks total", flush=True)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# FALLBACK LISTS (used only if live fetch fails)
# ─────────────────────────────────────────────────────────────────────────────

def get_nifty500_fallback() -> list:
    """Top 150 Nifty 500 stocks as fallback if NSE is unreachable."""
    return [
        ("HDFCBANK","HDFC Bank","Banking"), ("ICICIBANK","ICICI Bank","Banking"),
        ("RELIANCE","Reliance Industries","Oil & Gas"), ("INFY","Infosys","IT"),
        ("TCS","Tata Consultancy Services","IT"), ("SBIN","State Bank of India","PSU Banking"),
        ("KOTAKBANK","Kotak Mahindra Bank","Banking"), ("AXISBANK","Axis Bank","Banking"),
        ("LT","Larsen & Toubro","Infrastructure"), ("BAJFINANCE","Bajaj Finance","NBFC"),
        ("HINDUNILVR","Hindustan Unilever","FMCG"), ("ITC","ITC","FMCG"),
        ("BHARTIARTL","Bharti Airtel","Telecom"), ("HCLTECH","HCL Technologies","IT"),
        ("WIPRO","Wipro","IT"), ("ADANIPORTS","Adani Ports","Ports"),
        ("MARUTI","Maruti Suzuki","Auto"), ("TATAMOTORS","Tata Motors","Auto"),
        ("M&M","Mahindra & Mahindra","Auto"), ("SUNPHARMA","Sun Pharmaceutical","Pharma"),
        ("DRREDDY","Dr Reddys Labs","Pharma"), ("CIPLA","Cipla","Pharma"),
        ("NTPC","NTPC","PSU Power"), ("POWERGRID","Power Grid Corp","PSU Power"),
        ("ONGC","ONGC","PSU Energy"), ("COALINDIA","Coal India","PSU Mining"),
        ("BAJAJ-AUTO","Bajaj Auto","Two Wheeler"), ("HEROMOTOCO","Hero MotoCorp","Two Wheeler"),
        ("EICHERMOT","Eicher Motors","Two Wheeler"), ("TITAN","Titan Company","Jewellery"),
        ("NESTLEIND","Nestle India","FMCG"), ("BRITANNIA","Britannia Industries","FMCG"),
        ("TATASTEEL","Tata Steel","Steel"), ("JSWSTEEL","JSW Steel","Steel"),
        ("HINDALCO","Hindalco Industries","Aluminium"), ("VEDL","Vedanta","Metals"),
        ("ULTRACEMCO","UltraTech Cement","Cement"), ("SHREECEM","Shree Cement","Cement"),
        ("AMBUJACEM","Ambuja Cements","Cement"), ("DLF","DLF","Real Estate"),
        ("GODREJPROP","Godrej Properties","Real Estate"), ("ADANIGREEN","Adani Green","Renewable"),
        ("ADANIENT","Adani Enterprises","Diversified"), ("TATAPOWER","Tata Power","Power"),
        ("PERSISTENT","Persistent Systems","IT"), ("LTIM","LTIMindtree","IT"),
        ("COFORGE","Coforge","IT"), ("KPITTECH","KPIT Technologies","IT"),
        ("ZOMATO","Zomato","Internet"), ("NYKAA","Nykaa","Internet"),
        ("INDIAMART","IndiaMART","B2B Internet"), ("POLICYBZR","PB Fintech","Insurtech"),
        ("TRENT","Trent","Retail"), ("DMART","Avenue Supermarts","Retail"),
        ("APOLLOHOSP","Apollo Hospitals","Healthcare"), ("MAXHEALTH","Max Healthcare","Healthcare"),
        ("HDFCLIFE","HDFC Life Insurance","Insurance"), ("SBILIFE","SBI Life Insurance","Insurance"),
        ("BAJAJFINSV","Bajaj Finserv","NBFC"), ("PFC","Power Finance Corp","PSU Finance"),
        ("RECLTD","REC Limited","PSU Finance"), ("IRFC","IRFC","PSU Finance"),
        ("HAL","Hindustan Aeronautics","Defence"), ("BEL","Bharat Electronics","Defence"),
        ("MAZDOCK","Mazagon Dock","Defence"), ("SIEMENS","Siemens India","Capital Goods"),
        ("ABB","ABB India","Capital Goods"), ("CUMMINSIND","Cummins India","Industrial"),
        ("GRASIM","Grasim Industries","Diversified"), ("PIDILITIND","Pidilite","Adhesives"),
        ("SRF","SRF Limited","Specialty Chem"), ("DEEPAKNTR","Deepak Nitrite","Specialty Chem"),
        ("DIVISLAB","Divis Laboratories","Pharma"), ("BIOCON","Biocon","Biotech"),
        ("CHOLAFIN","Cholamandalam Finance","NBFC"), ("MUTHOOTFIN","Muthoot Finance","NBFC"),
        ("BANKBARODA","Bank of Baroda","PSU Banking"), ("PNB","Punjab National Bank","PSU Banking"),
        ("CANBK","Canara Bank","PSU Banking"), ("IGL","Indraprastha Gas","City Gas"),
        ("MGL","Mahanagar Gas","City Gas"), ("GAIL","GAIL India","PSU Gas"),
        ("IOC","Indian Oil Corp","PSU Oil"), ("BPCL","BPCL","PSU Oil"),
        ("HINDPETRO","Hindustan Petroleum","PSU Oil"), ("NMDC","NMDC","PSU Mining"),
        ("HINDZINC","Hindustan Zinc","Zinc"), ("APOLLOTYRE","Apollo Tyres","Tyres"),
        ("MRF","MRF","Tyres"), ("BALKRISIND","Balkrishna Industries","Specialty Tyres"),
        ("EXIDEIND","Exide Industries","Batteries"), ("POLYCAB","Polycab India","Cables"),
        ("HAVELLS","Havells India","Electricals"), ("VOLTAS","Voltas","Consumer Durables"),
        ("DIXON","Dixon Technologies","EMS"), ("KAYNES","Kaynes Technology","EMS"),
        ("IRCTC","IRCTC","PSU Travel"), ("CONCOR","Container Corp","Logistics"),
        ("DELHIVERY","Delhivery","Logistics"), ("INTERGLOBE","IndiGo","Aviation"),
        ("KALYANKJIL","Kalyan Jewellers","Jewellery"), ("VBL","Varun Beverages","Beverages"),
        ("DABUR","Dabur India","FMCG"), ("MARICO","Marico","FMCG"),
        ("GODREJCP","Godrej Consumer","FMCG"), ("COLPAL","Colgate-Palmolive","FMCG"),
        ("EMAMILTD","Emami","FMCG"), ("TATACONSUM","Tata Consumer","FMCG"),
        ("JUBLFOOD","Jubilant Foodworks","QSR"), ("DEVYANI","Devyani International","QSR"),
        ("PAGEIND","Page Industries","Garments"), ("MPHASIS","Mphasis","IT"),
        ("TATAELXSI","Tata Elxsi","IT"), ("HAPPSTMNDS","Happiest Minds","IT"),
        ("CDSL","CDSL","Depository"), ("MCX","MCX","Exchange"),
        ("ANGELONE","Angel One","Broking"), ("HDFCAMC","HDFC AMC","Asset Management"),
        ("360ONE","360 ONE WAM","Wealth Management"), ("IREDA","IREDA","Green Finance"),
        ("HUDCO","HUDCO","PSU Finance"), ("SUZLON","Suzlon Energy","Wind Energy"),
        ("JSWENERGY","JSW Energy","Power"), ("NHPC","NHPC","PSU Hydro"),
        ("SJVN","SJVN","PSU Hydro"), ("TORNTPOWER","Torrent Power","Power"),
        ("JINDALSTEE","Jindal Steel","Steel"), ("NATIONALUM","National Aluminium","Aluminium"),
        ("RATNAMANI","Ratnamani Metals","Steel Pipes"), ("APL","APL Apollo Tubes","Steel"),
        ("NAVINFLUOR","Navin Fluorine","Fluorochemicals"), ("ASTRAL","Astral","Pipes"),
        ("SUPREMEIND","Supreme Industries","Plastic Pipes"), ("KEI","KEI Industries","Cables"),
        ("ULTRACEMCO","UltraTech Cement","Cement"), ("JKCEMENT","JK Cement","Cement"),
        ("DALMIA","Dalmia Bharat","Cement"), ("OBEROIRLTY","Oberoi Realty","Real Estate"),
        ("LODHA","Macrotech Developers","Real Estate"), ("PHOENIXLTD","Phoenix Mills","REIT"),
        ("BRIGADE","Brigade Enterprises","Real Estate"), ("SOBHA","Sobha","Real Estate"),
        ("BHARTIARTL","Bharti Airtel","Telecom"), ("INDUSTOWER","Indus Towers","Telecom Infra"),
        ("STLTECH","Sterlite Technologies","Optical Fiber"), ("SAREGAMA","Saregama","Music"),
        ("KPRMILL","KPR Mill","Textiles"), ("VARDHMAN","Vardhman Textiles","Textiles"),
        ("BALRAMCHIN","Balrampur Chini","Sugar"), ("CHAMBAL","Chambal Fertilizers","Fertilizers"),
        ("COROMANDEL","Coromandel International","Agrochemicals"), ("UPL","UPL","Agrochemicals"),
    ]


def get_us500_fallback() -> list:
    """Top 100 US stocks as fallback."""
    return [
        ("AAPL","Apple","Technology"), ("MSFT","Microsoft","Technology"),
        ("NVDA","NVIDIA","Semiconductors"), ("GOOGL","Alphabet","Technology"),
        ("AMZN","Amazon","Consumer Discretionary"), ("META","Meta Platforms","Technology"),
        ("TSLA","Tesla","Consumer Discretionary"), ("BRK-B","Berkshire Hathaway","Financials"),
        ("LLY","Eli Lilly","Healthcare"), ("JPM","JPMorgan Chase","Financials"),
        ("V","Visa","Financials"), ("UNH","UnitedHealth","Healthcare"),
        ("XOM","Exxon Mobil","Energy"), ("MA","Mastercard","Financials"),
        ("AVGO","Broadcom","Semiconductors"), ("PG","Procter & Gamble","Consumer Staples"),
        ("JNJ","Johnson & Johnson","Healthcare"), ("HD","Home Depot","Consumer Discretionary"),
        ("COST","Costco","Consumer Staples"), ("ABBV","AbbVie","Healthcare"),
        ("MRK","Merck","Healthcare"), ("NFLX","Netflix","Communication"),
        ("CRM","Salesforce","Technology"), ("BAC","Bank of America","Financials"),
        ("ORCL","Oracle","Technology"), ("KO","Coca-Cola","Consumer Staples"),
        ("CVX","Chevron","Energy"), ("AMD","Advanced Micro Devices","Semiconductors"),
        ("WMT","Walmart","Consumer Staples"), ("PEP","PepsiCo","Consumer Staples"),
        ("TMO","Thermo Fisher","Healthcare"), ("ADBE","Adobe","Technology"),
        ("ACN","Accenture","Technology"), ("MCD","McDonald's","Consumer Discretionary"),
        ("NKE","Nike","Consumer Discretionary"), ("INTC","Intel","Semiconductors"),
        ("QCOM","Qualcomm","Semiconductors"), ("TXN","Texas Instruments","Semiconductors"),
        ("AMAT","Applied Materials","Semiconductors"), ("LRCX","Lam Research","Semiconductors"),
        ("NOW","ServiceNow","Technology"), ("INTU","Intuit","Technology"),
        ("PANW","Palo Alto Networks","Technology"), ("CRWD","CrowdStrike","Technology"),
        ("SNOW","Snowflake","Technology"), ("DDOG","Datadog","Technology"),
        ("NET","Cloudflare","Technology"), ("ZS","Zscaler","Technology"),
        ("PLTR","Palantir","Technology"), ("COIN","Coinbase","Financials"),
        ("ABNB","Airbnb","Consumer Discretionary"), ("UBER","Uber","Industrials"),
        ("DASH","DoorDash","Consumer Discretionary"), ("MELI","MercadoLibre","Consumer Discretionary"),
        ("SHOP","Shopify","Technology"), ("BKNG","Booking Holdings","Consumer Discretionary"),
        ("AMGN","Amgen","Healthcare"), ("GILD","Gilead Sciences","Healthcare"),
        ("REGN","Regeneron","Healthcare"), ("VRTX","Vertex Pharma","Healthcare"),
        ("ISRG","Intuitive Surgical","Healthcare"), ("SQ","Block","Financials"),
        ("PYPL","PayPal","Financials"), ("MU","Micron","Semiconductors"),
        ("MRVL","Marvell Technology","Semiconductors"), ("KLAC","KLA Corp","Semiconductors"),
        ("SNPS","Synopsys","Technology"), ("CDNS","Cadence Design","Technology"),
        ("ARM","Arm Holdings","Semiconductors"), ("WDAY","Workday","Technology"),
        ("TEAM","Atlassian","Technology"), ("MDB","MongoDB","Technology"),
        ("GTLB","GitLab","Technology"), ("TTD","Trade Desk","Technology"),
        ("APP","AppLovin","Technology"), ("ENPH","Enphase Energy","Utilities"),
        ("FSLR","First Solar","Utilities"), ("GS","Goldman Sachs","Financials"),
        ("MS","Morgan Stanley","Financials"), ("BLK","BlackRock","Financials"),
        ("SPGI","S&P Global","Financials"), ("ICE","Intercontinental Exchange","Financials"),
        ("CME","CME Group","Financials"), ("CB","Chubb","Financials"),
        ("AXP","American Express","Financials"), ("CAT","Caterpillar","Industrials"),
        ("DE","Deere","Industrials"), ("UNP","Union Pacific","Industrials"),
        ("RTX","Raytheon","Industrials"), ("HON","Honeywell","Industrials"),
        ("LMT","Lockheed Martin","Industrials"), ("GE","GE Aerospace","Industrials"),
        ("PLD","Prologis","Real Estate"), ("AMT","American Tower","Real Estate"),
        ("EQIX","Equinix","Real Estate"), ("CCI","Crown Castle","Real Estate"),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# PRICE FETCHER — fixed auto_adjust=False for real market prices
# ─────────────────────────────────────────────────────────────────────────────

def fetch_prices_batch(tickers: list, suffix: str = "") -> dict:
    """
    Fetches 1-year daily prices.
    auto_adjust=False — returns actual market prices, not dividend-adjusted.
    Uses regularMarketPrice from meta as the current price (most accurate).
    """
    yf_tickers = [t + suffix for t in tickers]
    results = {}
    try:
        raw = yf.download(
            tickers=yf_tickers,
            period="1y",
            interval="1d",
            group_by="ticker",
            auto_adjust=False,       # ← KEY FIX: real prices, not adjusted
            progress=False,
            threads=True,
        )
        for sym, yf_sym in zip(tickers, yf_tickers):
            try:
                if len(tickers) == 1:
                    df = raw
                else:
                    if yf_sym not in raw.columns.get_level_values(0):
                        continue
                    df = raw[yf_sym]

                if df is None or df.empty:
                    continue

                # Use "Close" (unadjusted) for history, meta for current price
                close_col = "Close" if "Close" in df.columns else df.columns[0]
                df_clean = df[[close_col, "High"]].dropna()
                if len(df_clean) < 30:
                    continue

                closes = df_clean[close_col].values
                highs  = df[["High"]].dropna()["High"].values if "High" in df.columns else closes

                # Current price: use last close (most reliable with batch)
                cur_price = float(closes[-1])
                high52w   = float(highs.max())
                low52w    = float(closes.min())
                prev      = float(closes[-2]) if len(closes) > 1 else cur_price

                results[sym] = {
                    "price":   round(cur_price, 2),
                    "high52w": round(high52w, 2),
                    "low52w":  round(low52w, 2),
                    "prev":    round(prev, 2),
                }
            except Exception:
                continue
    except Exception as e:
        print(f"  Batch fetch error: {e}", flush=True)
    return results


def fetch_prices_chunked(universe: list, suffix: str, chunk_size: int = 50) -> dict:
    """Parallel chunked fetching — 4 workers, 50 stocks per chunk."""
    tickers = [s[0] for s in universe]
    chunks  = [tickers[i:i+chunk_size] for i in range(0, len(tickers), chunk_size)]
    all_prices = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(fetch_prices_batch, chunk, suffix): chunk for chunk in chunks}
        for fut in as_completed(futures):
            try:
                all_prices.update(fut.result())
            except Exception as e:
                print(f"  Chunk error: {e}", flush=True)
    return all_prices


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def now_ist() -> str:
    ist = pytz.timezone("Asia/Kolkata")
    return datetime.now(ist).strftime("%d-%b-%Y %H:%M") + " IST"

def is_weekend() -> bool:
    return datetime.utcnow().weekday() >= 5

def load_json(path, default=None):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default if default is not None else {}

def save_json(path, data):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def pct(a, b) -> float:
    return ((a - b) / b * 100) if b else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def check_portfolio(holdings, prices, cfg) -> tuple:
    trailing = cfg.get("trailing_stop_pct", 20) / 100
    threshold = cfg.get("floor_alert_threshold_pct", 2)
    sells, floors, updated = [], [], []

    for h in holdings:
        if h.get("status") == "SOLD":
            updated.append(h)
            continue
        sym = h["symbol"]
        p   = prices.get(sym)
        if not p:
            updated.append(h)
            continue

        cur      = p["price"]
        peak     = h.get("peak_price", h["entry_price"])
        floor    = h.get("floor_price", h["entry_price"] * (1 - trailing))
        invested = h["entry_price"] * h["qty"]
        pnl_pct  = pct(cur, h["entry_price"])

        h = {**h, "current_price": cur,
             "current_value": round(cur * h["qty"], 2),
             "pnl": round(cur * h["qty"] - invested, 2),
             "pnl_pct": round(pnl_pct, 2)}

        if cur <= floor:
            sells.append({
                "symbol": sym, "name": h.get("name", sym),
                "sector": h.get("sector", ""),
                "entry_price": h["entry_price"],
                "peak_price": round(peak, 2),
                "floor_price": round(floor, 2),
                "current_price": cur, "qty": h["qty"],
                "invested": round(invested, 2),
                "pnl_pct": round(pnl_pct, 2),
            })
            h["status"] = "STOP HIT"
        else:
            new_peak  = max(peak, cur)
            new_floor = round(new_peak * (1 - trailing), 2)
            floor_chg = pct(new_floor, floor)
            if floor_chg >= threshold:
                floors.append({
                    "symbol": sym, "name": h.get("name", sym),
                    "sector": h.get("sector", ""),
                    "current_price": cur,
                    "new_peak": round(new_peak, 2),
                    "old_floor": round(floor, 2),
                    "new_floor": new_floor,
                    "floor_change_pct": round(floor_chg, 2),
                })
            h["peak_price"]  = round(new_peak, 2)
            h["floor_price"] = new_floor

        updated.append(h)
    return updated, sells, floors


def scan_for_signals(universe, prices, portfolio_syms, cfg, portfolio_value, currency) -> list:
    entry_mode    = cfg.get("entry_mode", 100)
    position_size = portfolio_value * cfg.get("position_pct", 5) / 100
    trailing      = cfg.get("trailing_stop_pct", 20) / 100
    buys = []

    for sym, name, sector in universe:
        if sym in portfolio_syms:
            continue
        p = prices.get(sym)
        if not p:
            continue
        cur      = p["price"]
        high52w  = p["high52w"]
        target   = high52w * (entry_mode / 100)
        if cur >= target:
            qty   = max(1, int(position_size / cur))
            floor = round(cur * (1 - trailing), 2)
            buys.append({
                "symbol": sym, "name": name, "sector": sector,
                "current_price": cur, "high52w": high52w,
                "low52w": p["low52w"], "ath_target": round(target, 2),
                "entry_mode": entry_mode,
                "pct_from_high": round(pct(cur, high52w), 2),
                "suggested_floor": floor,
                "suggested_qty": qty,
                "suggested_amount": round(qty * cur, 2),
                "currency": currency,
            })

    buys.sort(key=lambda x: x["pct_from_high"], reverse=True)
    return buys


# ─────────────────────────────────────────────────────────────────────────────
# MAIN SCAN
# ─────────────────────────────────────────────────────────────────────────────

def run_scan(market, universe, suffix, portfolio, cfg, pf_value, currency) -> dict:
    t0 = time.time()
    print(f"\n{'='*60}", flush=True)
    print(f"  {market} | Entry: {cfg.get('entry_mode',100)}% ATH | {len(universe)} stocks", flush=True)
    print(f"{'='*60}", flush=True)

    prices = fetch_prices_chunked(universe, suffix)
    print(f"  Prices fetched: {len(prices)}/{len(universe)}", flush=True)

    active  = [h for h in portfolio if h.get("status") == "ACTIVE"]
    pf_syms = {h["symbol"] for h in active}
    slots   = max(0, cfg.get("max_stocks", 20) - len(active))

    updated, sells, floors = check_portfolio(active, prices, cfg)
    buys = scan_for_signals(universe, prices, pf_syms, cfg, pf_value, currency)[:slots] if slots > 0 else []

    elapsed = round(time.time() - t0, 1)
    print(f"  BUY: {len(buys)} | SELL: {len(sells)} | FLOOR: {len(floors)} | {elapsed}s", flush=True)

    return {
        "buys": buys, "sells": sells, "floors": floors,
        "portfolio": updated,
        "stats": {
            "scanned": len(prices), "universe": len(universe),
            "buy_signals": len(buys), "sell_signals": len(sells),
            "floor_updates": len(floors), "slots_free": slots,
            "scan_seconds": elapsed,
        },
        "scan_time_ist": now_ist(),
    }


def main():
    print(f"\n🔍 MOMENTUM SCANNER v2.1 — {now_ist()}", flush=True)

    cfg_raw   = load_json("config.json", {})
    strategy  = cfg_raw.get("strategy", {})
    india_cfg = strategy.get("india", {})
    us_cfg    = strategy.get("us", {})
    usd_inr   = strategy.get("usd_inr_rate", 84.5)
    pf_raw    = load_json("portfolio.json", {"india": [], "us": []})

    scan_market = os.environ.get("SCAN_MARKET", "both").lower()
    results = {}

    # Fetch universes (live from NSE/Wikipedia, fallback to hardcoded)
    if scan_market in ("india", "both"):
        nifty500 = fetch_nifty500_from_nse()
        results["india"] = run_scan(
            "🇮🇳 India Nifty 500", nifty500, ".NS",
            pf_raw.get("india", []), india_cfg,
            india_cfg.get("portfolio_value_inr", 1000000), "₹"
        )
        pf_raw["india"] = results["india"]["portfolio"]

    if scan_market in ("us", "both"):
        us500 = fetch_us500_universe()
        results["us"] = run_scan(
            "🇺🇸 US Top 500", us500, "",
            pf_raw.get("us", []), us_cfg,
            us_cfg.get("portfolio_value_usd", 10000), "$"
        )
        pf_raw["us"] = results["us"]["portfolio"]

    # Save updated portfolio and signals
    save_json("portfolio.json", pf_raw)

    existing = load_json("data/signals.json", {})
    signals = {
        "last_scan_ist": now_ist(),
        "last_india_scan_ist": results.get("india", {}).get("scan_time_ist", existing.get("last_india_scan_ist", "Never")),
        "last_us_scan_ist":    results.get("us",    {}).get("scan_time_ist", existing.get("last_us_scan_ist",    "Never")),
        "usd_inr": usd_inr,
        "india":   results.get("india", existing.get("india", {})),
        "us":      results.get("us",    existing.get("us",    {})),
    }
    save_json("data/signals.json", signals)

    total = sum(len(results.get(m, {}).get(k, [])) for m in ("india","us") for k in ("buys","sells"))
    print(f"\n✅ Done — {now_ist()} | Actionable signals: {total}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
