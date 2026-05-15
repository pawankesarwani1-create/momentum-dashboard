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
    Full hardcoded US universe: S&P 500 + Nasdaq 100 + high-growth stocks.
    ~530 stocks. No external fetch needed — immune to Wikipedia 403 blocks.
    """
    print("  Loading US universe (S&P500 + Nasdaq100 + Growth)...", flush=True)
    stocks = [
        # ── MEGA CAP TECH ──────────────────────────────────────────────
        ("AAPL","Apple","Technology"),
        ("MSFT","Microsoft","Technology"),
        ("NVDA","NVIDIA","Semiconductors"),
        ("GOOGL","Alphabet A","Technology"),
        ("GOOG","Alphabet C","Technology"),
        ("AMZN","Amazon","Consumer Discretionary"),
        ("META","Meta Platforms","Technology"),
        ("TSLA","Tesla","Consumer Discretionary"),
        ("NFLX","Netflix","Communication"),
        ("ADBE","Adobe","Technology"),
        # ── SEMICONDUCTORS ────────────────────────────────────────────
        ("AMD","Advanced Micro Devices","Semiconductors"),
        ("INTC","Intel","Semiconductors"),
        ("QCOM","Qualcomm","Semiconductors"),
        ("AVGO","Broadcom","Semiconductors"),
        ("TXN","Texas Instruments","Semiconductors"),
        ("AMAT","Applied Materials","Semiconductor Equip"),
        ("LRCX","Lam Research","Semiconductor Equip"),
        ("KLAC","KLA Corporation","Semiconductor Equip"),
        ("MU","Micron Technology","Semiconductors"),
        ("MRVL","Marvell Technology","Semiconductors"),
        ("ASML","ASML Holding","Semiconductor Equip"),
        ("SNPS","Synopsys","EDA Software"),
        ("CDNS","Cadence Design","EDA Software"),
        ("ARM","Arm Holdings","Semiconductors"),
        ("SMCI","Super Micro Computer","Servers"),
        ("ON","ON Semiconductor","Semiconductors"),
        ("MPWR","Monolithic Power","Semiconductors"),
        ("AMBA","Ambarella","AI Chips"),
        ("ALGM","Allegro MicroSystems","Semiconductors"),
        ("PI","Impinj","RFID Chips"),
        ("SITM","SiTime Corporation","Semiconductors"),
        # ── CLOUD & SAAS ──────────────────────────────────────────────
        ("CRM","Salesforce","Technology"),
        ("NOW","ServiceNow","Technology"),
        ("WDAY","Workday","Technology"),
        ("SNOW","Snowflake","Technology"),
        ("DDOG","Datadog","Technology"),
        ("TEAM","Atlassian","Technology"),
        ("MDB","MongoDB","Technology"),
        ("ORCL","Oracle","Technology"),
        ("INTU","Intuit","Technology"),
        ("HUBS","HubSpot","Technology"),
        ("GTLB","GitLab","Technology"),
        ("BILL","Bill.com","Technology"),
        ("PCTY","Paylocity","Technology"),
        ("PAYC","Paycom Software","Technology"),
        ("ZI","ZoomInfo","Technology"),
        ("BRZE","Braze","Technology"),
        ("TTD","The Trade Desk","Technology"),
        ("APP","AppLovin","Technology"),
        ("MNDY","Monday.com","Technology"),
        ("ASAN","Asana","Technology"),
        ("PATH","UiPath","Technology"),
        ("ZM","Zoom Video","Technology"),
        ("CVLT","Commvault Systems","Technology"),
        ("ALTR","Altair Engineering","Technology"),
        ("APPF","AppFolio","Technology"),
        ("VEEV","Veeva Systems","Healthcare Technology"),
        # ── CYBERSECURITY ─────────────────────────────────────────────
        ("PANW","Palo Alto Networks","Cybersecurity"),
        ("CRWD","CrowdStrike","Cybersecurity"),
        ("ZS","Zscaler","Cybersecurity"),
        ("FTNT","Fortinet","Cybersecurity"),
        ("OKTA","Okta","Cybersecurity"),
        ("NET","Cloudflare","Cybersecurity"),
        ("S","SentinelOne","Cybersecurity"),
        ("TENB","Tenable Holdings","Cybersecurity"),
        ("QLYS","Qualys","Cybersecurity"),
        ("VRNS","Varonis Systems","Cybersecurity"),
        # ── FINANCIALS & BANKS ────────────────────────────────────────
        ("JPM","JPMorgan Chase","Financials"),
        ("BAC","Bank of America","Financials"),
        ("WFC","Wells Fargo","Financials"),
        ("GS","Goldman Sachs","Financials"),
        ("MS","Morgan Stanley","Financials"),
        ("C","Citigroup","Financials"),
        ("AXP","American Express","Financials"),
        ("V","Visa","Financials"),
        ("MA","Mastercard","Financials"),
        ("BLK","BlackRock","Financials"),
        ("SPGI","S&P Global","Financials"),
        ("ICE","Intercontinental Exchange","Financials"),
        ("CME","CME Group","Financials"),
        ("CB","Chubb","Financials"),
        ("PGR","Progressive","Financials"),
        ("AFL","Aflac","Financials"),
        ("MET","MetLife","Financials"),
        ("PRU","Prudential Financial","Financials"),
        ("USB","US Bancorp","Financials"),
        ("TFC","Truist Financial","Financials"),
        ("PNC","PNC Financial","Financials"),
        ("SCHW","Charles Schwab","Financials"),
        ("COF","Capital One","Financials"),
        ("DFS","Discover Financial","Financials"),
        ("SYF","Synchrony Financial","Financials"),
        # ── FINTECH ───────────────────────────────────────────────────
        ("PYPL","PayPal","Fintech"),
        ("SQ","Block Inc","Fintech"),
        ("COIN","Coinbase","Fintech"),
        ("HOOD","Robinhood","Fintech"),
        ("SOFI","SoFi Technologies","Fintech"),
        ("AFRM","Affirm Holdings","Fintech"),
        ("UPST","Upstart Holdings","Fintech"),
        ("FOUR","Shift4 Payments","Fintech"),
        ("MQ","Marqeta","Fintech"),
        ("RELY","Remitly Global","Fintech"),
        ("LMND","Lemonade","Fintech"),
        # ── HEALTHCARE & BIOTECH ──────────────────────────────────────
        ("UNH","UnitedHealth Group","Healthcare"),
        ("JNJ","Johnson & Johnson","Healthcare"),
        ("LLY","Eli Lilly","Healthcare"),
        ("ABBV","AbbVie","Healthcare"),
        ("MRK","Merck","Healthcare"),
        ("TMO","Thermo Fisher","Healthcare"),
        ("ABT","Abbott Laboratories","Healthcare"),
        ("DHR","Danaher","Healthcare"),
        ("BMY","Bristol-Myers Squibb","Healthcare"),
        ("AMGN","Amgen","Biotech"),
        ("GILD","Gilead Sciences","Biotech"),
        ("BIIB","Biogen","Biotech"),
        ("REGN","Regeneron Pharma","Biotech"),
        ("VRTX","Vertex Pharma","Biotech"),
        ("MRNA","Moderna","Biotech"),
        ("ILMN","Illumina","Genomics"),
        ("IDXX","IDEXX Laboratories","Healthcare"),
        ("ISRG","Intuitive Surgical","Healthcare"),
        ("DXCM","DexCom","Healthcare"),
        ("ALGN","Align Technology","Healthcare"),
        ("HOLX","Hologic","Healthcare"),
        ("NTRA","Natera","Healthcare"),
        ("EXAS","Exact Sciences","Healthcare"),
        ("HIMS","Hims Hers Health","Telehealth"),
        ("TDOC","Teladoc Health","Telehealth"),
        ("CERT","Certara","Healthcare"),
        ("RXRX","Recursion Pharma","Healthcare"),
        ("ALNY","Alnylam Pharma","Biotech"),
        ("IONS","Ionis Pharma","Biotech"),
        ("BEAM","Beam Therapeutics","Biotech"),
        ("CRSP","CRISPR Therapeutics","Biotech"),
        # ── CONSUMER DISCRETIONARY ────────────────────────────────────
        ("AMZN","Amazon","Consumer Discretionary"),
        ("TSLA","Tesla","Consumer Discretionary"),
        ("HD","Home Depot","Consumer Discretionary"),
        ("MCD","McDonald's","Consumer Discretionary"),
        ("NKE","Nike","Consumer Discretionary"),
        ("SBUX","Starbucks","Consumer Discretionary"),
        ("LOW","Lowe's","Consumer Discretionary"),
        ("TJX","TJX Companies","Consumer Discretionary"),
        ("BKNG","Booking Holdings","Consumer Discretionary"),
        ("ABNB","Airbnb","Consumer Discretionary"),
        ("EXPE","Expedia Group","Consumer Discretionary"),
        ("UBER","Uber Technologies","Consumer Discretionary"),
        ("LYFT","Lyft","Consumer Discretionary"),
        ("DASH","DoorDash","Consumer Discretionary"),
        ("MELI","MercadoLibre","Consumer Discretionary"),
        ("SHOP","Shopify","Consumer Discretionary"),
        ("ETSY","Etsy","Consumer Discretionary"),
        ("EBAY","eBay","Consumer Discretionary"),
        ("CHWY","Chewy","Consumer Discretionary"),
        ("W","Wayfair","Consumer Discretionary"),
        ("DKNG","DraftKings","Consumer Discretionary"),
        ("CART","Instacart Maplebear","Consumer Discretionary"),
        ("RH","RH Restoration Hardware","Consumer Discretionary"),
        ("GLBE","Global-E Online","Consumer Discretionary"),
        ("GRAB","Grab Holdings","Consumer Discretionary"),
        ("SE","Sea Limited","Consumer Discretionary"),
        # ── CONSUMER STAPLES ──────────────────────────────────────────
        ("PG","Procter & Gamble","Consumer Staples"),
        ("KO","Coca-Cola","Consumer Staples"),
        ("PEP","PepsiCo","Consumer Staples"),
        ("COST","Costco","Consumer Staples"),
        ("WMT","Walmart","Consumer Staples"),
        ("PM","Philip Morris","Consumer Staples"),
        ("MO","Altria Group","Consumer Staples"),
        ("CL","Colgate-Palmolive","Consumer Staples"),
        ("KMB","Kimberly-Clark","Consumer Staples"),
        ("GIS","General Mills","Consumer Staples"),
        ("K","Kellogg","Consumer Staples"),
        ("CAG","Conagra Brands","Consumer Staples"),
        ("HRL","Hormel Foods","Consumer Staples"),
        ("SJM","J.M. Smucker","Consumer Staples"),
        # ── ENERGY ────────────────────────────────────────────────────
        ("XOM","Exxon Mobil","Energy"),
        ("CVX","Chevron","Energy"),
        ("COP","ConocoPhillips","Energy"),
        ("EOG","EOG Resources","Energy"),
        ("SLB","Schlumberger","Energy"),
        ("MPC","Marathon Petroleum","Energy"),
        ("PSX","Phillips 66","Energy"),
        ("VLO","Valero Energy","Energy"),
        ("HAL","Halliburton","Energy"),
        ("BKR","Baker Hughes","Energy"),
        ("OXY","Occidental Petroleum","Energy"),
        ("DVN","Devon Energy","Energy"),
        ("FANG","Diamondback Energy","Energy"),
        ("ENPH","Enphase Energy","Clean Energy"),
        ("FSLR","First Solar","Clean Energy"),
        ("PLUG","Plug Power","Clean Energy"),
        ("CHPT","ChargePoint Holdings","Clean Energy"),
        ("EVGO","EVgo","Clean Energy"),
        ("FLNC","Fluence Energy","Clean Energy"),
        # ── INDUSTRIALS ───────────────────────────────────────────────
        ("CAT","Caterpillar","Industrials"),
        ("DE","Deere & Company","Industrials"),
        ("HON","Honeywell","Industrials"),
        ("UNP","Union Pacific","Industrials"),
        ("GE","GE Aerospace","Industrials"),
        ("RTX","RTX Corporation","Industrials"),
        ("LMT","Lockheed Martin","Industrials"),
        ("NOC","Northrop Grumman","Industrials"),
        ("BA","Boeing","Industrials"),
        ("GD","General Dynamics","Industrials"),
        ("MMM","3M Company","Industrials"),
        ("EMR","Emerson Electric","Industrials"),
        ("ETN","Eaton Corporation","Industrials"),
        ("PH","Parker-Hannifin","Industrials"),
        ("ROK","Rockwell Automation","Industrials"),
        ("ODFL","Old Dominion Freight","Industrials"),
        ("SAIA","Saia Inc","Industrials"),
        ("XPO","XPO Logistics","Industrials"),
        ("CPRT","Copart","Industrials"),
        ("FAST","Fastenal","Industrials"),
        ("KTOS","Kratos Defense","Industrials"),
        ("AVAV","AeroVironment","Industrials"),
        ("LDOS","Leidos Holdings","Industrials"),
        # ── REAL ESTATE ───────────────────────────────────────────────
        ("PLD","Prologis","Real Estate"),
        ("AMT","American Tower","Real Estate"),
        ("EQIX","Equinix","Real Estate"),
        ("CCI","Crown Castle","Real Estate"),
        ("SPG","Simon Property Group","Real Estate"),
        ("O","Realty Income","Real Estate"),
        ("WELL","Welltower","Real Estate"),
        ("DLR","Digital Realty","Real Estate"),
        ("PSA","Public Storage","Real Estate"),
        ("AVB","AvalonBay Communities","Real Estate"),
        ("CSGP","CoStar Group","Real Estate"),
        ("OPEN","Opendoor Technologies","Real Estate"),
        # ── MATERIALS ─────────────────────────────────────────────────
        ("LIN","Linde","Materials"),
        ("APD","Air Products","Materials"),
        ("SHW","Sherwin-Williams","Materials"),
        ("ECL","Ecolab","Materials"),
        ("NEM","Newmont Corporation","Materials"),
        ("FCX","Freeport-McMoRan","Materials"),
        ("NUE","Nucor Corporation","Materials"),
        ("CF","CF Industries","Materials"),
        ("MOS","Mosaic Company","Materials"),
        # ── UTILITIES ─────────────────────────────────────────────────
        ("NEE","NextEra Energy","Utilities"),
        ("DUK","Duke Energy","Utilities"),
        ("SO","Southern Company","Utilities"),
        ("D","Dominion Energy","Utilities"),
        ("AEP","American Electric Power","Utilities"),
        ("EXC","Exelon","Utilities"),
        ("SRE","Sempra Energy","Utilities"),
        ("PCG","PG&E Corporation","Utilities"),
        ("XEL","Xcel Energy","Utilities"),
        ("WEC","WEC Energy Group","Utilities"),
        # ── COMMUNICATION ─────────────────────────────────────────────
        ("T","AT&T","Communication"),
        ("VZ","Verizon","Communication"),
        ("TMUS","T-Mobile US","Communication"),
        ("SPOT","Spotify","Communication"),
        ("PINS","Pinterest","Communication"),
        ("SNAP","Snap Inc","Communication"),
        ("BMBL","Bumble","Communication"),
        ("MTCH","Match Group","Communication"),
        ("ROKU","Roku","Communication"),
        ("WBD","Warner Bros Discovery","Communication"),
        ("PARA","Paramount Global","Communication"),
        # ── AI & NEXT GEN ─────────────────────────────────────────────
        ("PLTR","Palantir Technologies","AI Analytics"),
        ("AI","C3.ai","AI Software"),
        ("SOUN","SoundHound AI","Voice AI"),
        ("IONQ","IonQ","Quantum Computing"),
        ("RGTI","Rigetti Computing","Quantum Computing"),
        ("RBLX","Roblox","Gaming Metaverse"),
        ("U","Unity Software","Game Engine"),
        ("TTWO","Take-Two Interactive","Gaming"),
        ("EA","Electronic Arts","Gaming"),
    ]
    # Deduplicate preserving order
    seen = set()
    unique = []
    for s in stocks:
        if s[0] not in seen:
            seen.add(s[0])
            unique.append(s)
    print(f"  ✅ US universe: {len(unique)} stocks loaded", flush=True)
    return unique


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


# ─────────────────────────────────────────────────────────────────────────────
# EMAIL DELIVERY via Gmail SMTP
# ─────────────────────────────────────────────────────────────────────────────

def send_email(results: dict, cfg_raw: dict):
    """
    Sends HTML alert email via Gmail SMTP.
    Reads credentials from environment variables (GitHub Secrets):
      GMAIL_USER         = sender Gmail address
      GMAIL_APP_PASSWORD = 16-char Gmail App Password
    Alert email address read from config.json → strategy.alert_email
    Only sends if there are actionable signals (buys or sells).
    """
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    gmail_user = os.environ.get("GMAIL_USER", "")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "")
    alert_to   = cfg_raw.get("strategy", {}).get("alert_email", gmail_user)

    if not gmail_user or not gmail_pass:
        print("  ⚠️ Email skipped — GMAIL_USER or GMAIL_APP_PASSWORD not set in GitHub Secrets", flush=True)
        return

    # Count signals across both markets
    india  = results.get("india", {})
    us     = results.get("us", {})
    buys   = (india.get("buys", []) + us.get("buys", []))
    sells  = (india.get("sells", []) + us.get("sells", []))
    floors = (india.get("floors", []) + us.get("floors", []))
    total  = len(buys) + len(sells) + len(floors)

    if total == 0:
        print("  No signals — email skipped", flush=True)
        return

    # Build subject line
    parts = []
    if sells:  parts.append(f"🔴 SELL({len(sells)})")
    if buys:   parts.append(f"🟢 BUY({len(buys)})")
    if floors: parts.append(f"🔄 FLOOR({len(floors)})")
    subject = f"[Momentum] {' | '.join(parts)} — {now_ist()}"

    # ── Build HTML body ──────────────────────────────────────────────
    def card(bg, border, heading, rows, action, action_color):
        row_html = "".join(
            f"<tr style='background:{'#1e0a0a' if i%2==0 else '#1a0808' if 'sell' in bg else '#0f2016' if 'buy' in bg else '#1a1000'}'>"
            + "".join(f"<td style='padding:8px 12px;color:{vc};font-family:monospace;font-size:12px'>{v}</td>" for v, vc in r)
            + "</tr>"
            for i, r in enumerate(rows)
        )
        return f"""
        <div style='margin-bottom:24px;background:{bg};border:1px solid {border};border-radius:12px;overflow:hidden'>
          <div style='padding:14px 18px;border-bottom:1px solid {border}'>
            <span style='font-size:16px;font-weight:700;color:#e0e7f1'>{heading}</span>
          </div>
          <table style='width:100%;border-collapse:collapse'>{row_html}</table>
          <div style='padding:10px 16px;border-top:1px solid {border};font-size:12px;color:{action_color}'>{action}</div>
        </div>"""

    sections = ""

    if sells:
        rows = [[(s["symbol"], "#f04e6a"), (s["name"][:22], "#c8c8c8"),
                 (f"Entry: ₹{s['entry_price']}" if "₹" not in str(s.get("currency","")) else f"Entry: {s['entry_price']}", "#c8c8c8"),
                 (f"Floor: {s['floor_price']}", "#f04e6a"),
                 (f"⚡ Current: {s['current_price']}", "#ff6b6b"),
                 (f"P&L: {s['pnl_pct']}%", "#f04e6a" if s['pnl_pct'] < 0 else "#10d48e")]
                for s in sells]
        sections += card("rgba(240,78,106,0.08)", "rgba(240,78,106,0.3)",
                         f"🔴 SELL — Stop Loss Breached ({len(sells)} stock{'s' if len(sells)>1 else ''})",
                         rows, "⚠️ Sell immediately in demat → Mark as SOLD in portfolio.json", "#ffcccc")

    if buys:
        rows = [[(b["symbol"], "#10d48e"), (b["name"][:22], "#c8e6c9"),
                 (f"Price: {b['current_price']}", "#e0e7f1"),
                 (f"52WH: {b['high52w']}", "#6b7fa3"),
                 (f"Floor: {b['suggested_floor']}", "#f04e6a"),
                 (f"Qty: {b['suggested_qty']}", "#e0e7f1")]
                for b in buys]
        sections += card("rgba(16,212,142,0.08)", "rgba(16,212,142,0.3)",
                         f"🟢 BUY — {buys[0].get('entry_mode',100)}% ATH Signal ({len(buys)} stock{'s' if len(buys)>1 else ''})",
                         rows, "📋 Buy in demat → Set TSL at floor → Add to portfolio.json", "#c8e6c9")

    if floors:
        rows = [[(f["symbol"], "#f5a623"), (f["name"][:22], "#e0e7f1"),
                 (f"Current: {f['current_price']}", "#e0e7f1"),
                 (f"Old floor: {f['old_floor']}", "#6b7fa3"),
                 (f"⬆ New floor: {f['new_floor']}", "#f5a623"),
                 (f"+{f['floor_change_pct']}%", "#10d48e")]
                for f in floors]
        sections += card("rgba(245,166,35,0.08)", "rgba(245,166,35,0.3)",
                         f"🔄 FLOOR UPDATE — Trailing Stop Moved Up ({len(floors)} stock{'s' if len(floors)>1 else ''})",
                         rows, "📋 Update stop-loss orders in demat to new floor prices", "#ffe0b2")

    dashboard_url = "https://pawankesarwani1-create.github.io/momentum-dashboard"
    html = f"""<!DOCTYPE html><html><body style='background:#05080f;font-family:Outfit,Arial,sans-serif;padding:20px;margin:0'>
    <div style='max-width:900px;margin:0 auto;background:#0b1120;border:1px solid #1a2540;border-radius:14px;padding:28px'>
      <h1 style='font-size:20px;font-weight:800;color:#e0e7f1;margin:0 0 6px'>📊 Momentum Strategy Alert</h1>
      <p style='color:#6b7fa3;font-size:13px;margin:0 0 24px'>{now_ist()} &nbsp;·&nbsp;
         <a href='{dashboard_url}' style='color:#5b6ef5'>Open Dashboard</a></p>
      {sections}
      <p style='color:#3d5078;font-size:11px;margin-top:24px;padding-top:16px;border-top:1px solid #1a2540'>
        Auto-generated by Momentum Scanner · Only demat execution is manual</p>
    </div></body></html>"""

    # ── Send via Gmail SMTP SSL ──────────────────────────────────────
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = gmail_user
        msg["To"]      = alert_to
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, alert_to, msg.as_string())

        print(f"  ✅ Email sent to {alert_to} — '{subject}'", flush=True)
    except Exception as e:
        print(f"  ❌ Email failed: {e}", flush=True)


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

    # Send email alert
    print("\n📧 Sending email alert...", flush=True)
    send_email(results, cfg_raw)

    return 0


if __name__ == "__main__":
    sys.exit(main())
