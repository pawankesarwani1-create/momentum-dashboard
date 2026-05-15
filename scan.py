#!/usr/bin/env python3
"""
Momentum Strategy Scanner
=========================
Scans Nifty 500 (India) + Nasdaq 500 (US) for momentum signals.
- Entry: 90% / 100% / 110% of 52-week high (configurable per market)
- Exit:  20% trailing stop loss from peak
- Floor alert: only when floor moves >2% from last recorded level

Runs via GitHub Actions. Results written to data/signals.json.
No laptop needed — GitHub's servers execute this on schedule.
"""

import json
import os
import time
import sys
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

try:
    import yfinance as yf
    import pytz
except ImportError:
    print("Installing dependencies...")
    os.system("pip install yfinance pytz -q")
    import yfinance as yf
    import pytz

# ─────────────────────────────────────────────────────────────────────────────
# STOCK UNIVERSES
# ─────────────────────────────────────────────────────────────────────────────

NIFTY500 = [
    # Banking & Finance
    ("HDFCBANK","HDFC Bank","Banking"),
    ("ICICIBANK","ICICI Bank","Banking"),
    ("SBIN","State Bank of India","PSU Banking"),
    ("KOTAKBANK","Kotak Mahindra Bank","Banking"),
    ("AXISBANK","Axis Bank","Banking"),
    ("INDUSINDBK","IndusInd Bank","Banking"),
    ("BANKBARODA","Bank of Baroda","PSU Banking"),
    ("PNB","Punjab National Bank","PSU Banking"),
    ("CANBK","Canara Bank","PSU Banking"),
    ("UNIONBANK","Union Bank","PSU Banking"),
    ("INDIANB","Indian Bank","PSU Banking"),
    ("BANKINDIA","Bank of India","PSU Banking"),
    ("MAHABANK","Bank of Maharashtra","PSU Banking"),
    ("FEDERALBNK","Federal Bank","Banking"),
    ("IDFCFIRSTB","IDFC First Bank","Banking"),
    ("AUBANK","AU Small Finance Bank","Banking"),
    ("BANDHANBNK","Bandhan Bank","Banking"),
    ("KARURVYSYA","Karur Vysya Bank","Banking"),
    ("DCBBANK","DCB Bank","Banking"),
    ("EQUITASBNK","Equitas Small Finance","Banking"),
    ("UJJIVANSFB","Ujjivan Small Finance","Banking"),
    ("HDFCLIFE","HDFC Life Insurance","Insurance"),
    ("SBILIFE","SBI Life Insurance","Insurance"),
    ("ICICIGI","ICICI Lombard GI","Insurance"),
    ("LICI","LIC India","Insurance"),
    ("GICRE","GIC Re","Insurance"),
    ("NIACL","New India Assurance","Insurance"),
    ("BAJFINANCE","Bajaj Finance","NBFC"),
    ("BAJAJFINSV","Bajaj Finserv","NBFC"),
    ("CHOLAFIN","Cholamandalam Finance","NBFC"),
    ("MUTHOOTFIN","Muthoot Finance","NBFC"),
    ("MANAPPURAM","Manappuram Finance","NBFC"),
    ("PFC","Power Finance Corp","PSU Finance"),
    ("RECLTD","REC Limited","PSU Finance"),
    ("SHRIRAMFIN","Shriram Finance","NBFC"),
    ("IRFC","Indian Railway Finance","PSU Finance"),
    ("HUDCO","HUDCO","PSU Finance"),
    ("IREDA","IREDA","Green Finance"),
    ("HDFCAMC","HDFC AMC","Asset Management"),
    ("NAM-INDIA","Nippon Life India AMC","Asset Management"),
    ("360ONE","360 ONE WAM","Wealth Management"),
    ("ANGEL","Angel One","Broking"),
    ("BSE","BSE Ltd","Exchange"),
    ("CDSL","Central Depository","Depository"),
    ("MCX","Multi Commodity Exchange","Exchange"),
    ("CAMS","Computer Age Management","Fintech"),
    ("KFINTECH","KFin Technologies","Fintech"),
    ("POLICYBZR","PB Fintech","Insurtech"),
    ("STARHEALTH","Star Health Insurance","Insurance"),
    ("MFSL","Max Financial Services","Insurance"),
    ("ABCAPITAL","Aditya Birla Capital","Diversified Finance"),
    ("CREDITACC","CreditAccess Grameen","MFI"),
    ("AAVAS","Aavas Financiers","Housing Finance"),
    ("CANFINHOME","Can Fin Homes","Housing Finance"),
    # IT & Technology
    ("TCS","Tata Consultancy Services","IT"),
    ("INFY","Infosys","IT"),
    ("HCLTECH","HCL Technologies","IT"),
    ("WIPRO","Wipro","IT"),
    ("TECHM","Tech Mahindra","IT"),
    ("LTIM","LTIMindtree","IT"),
    ("MPHASIS","Mphasis","IT"),
    ("PERSISTENT","Persistent Systems","IT"),
    ("COFORGE","Coforge","IT"),
    ("OFSS","Oracle Financial Services","IT"),
    ("KPITTECH","KPIT Technologies","IT"),
    ("TATAELXSI","Tata Elxsi","IT Design"),
    ("MASTEK","Mastek","IT"),
    ("ZENSAR","Zensar Technologies","IT"),
    ("CYIENT","Cyient","IT Engineering"),
    ("BIRLASOFT","Birlasoft","IT"),
    ("ECLERX","eClerx Services","BPO"),
    ("HAPPSTMNDS","Happiest Minds","IT"),
    ("INTELLECT","Intellect Design Arena","Fintech IT"),
    ("NAUKRI","Info Edge India","Internet"),
    ("ZOMATO","Zomato","Internet"),
    ("NYKAA","Nykaa","Internet"),
    ("INDIAMART","IndiaMART","B2B Internet"),
    ("AFFLE","Affle India","Adtech"),
    ("MAPMYINDIA","MapmyIndia","Maps Tech"),
    ("RATEGAIN","RateGain Travel Tech","IT Travel"),
    ("NAZARA","Nazara Technologies","Gaming"),
    ("NEWGEN","Newgen Software","IT"),
    ("TANLA","Tanla Platforms","CPaaS"),
    # Oil, Gas & Energy
    ("RELIANCE","Reliance Industries","Oil & Gas"),
    ("ONGC","ONGC","PSU Energy"),
    ("COALINDIA","Coal India","PSU Mining"),
    ("NTPC","NTPC","PSU Power"),
    ("POWERGRID","Power Grid Corp","PSU Power"),
    ("IOC","Indian Oil Corp","PSU Oil"),
    ("BPCL","BPCL","PSU Oil"),
    ("GAIL","GAIL India","PSU Gas"),
    ("HINDPETRO","Hindustan Petroleum","PSU Oil"),
    ("OIL","Oil India","PSU Oil"),
    ("PETRONET","Petronet LNG","LNG"),
    ("IGL","Indraprastha Gas","City Gas"),
    ("MGL","Mahanagar Gas","City Gas"),
    ("GUJGASLTD","Gujarat Gas","City Gas"),
    ("ADANIPOWER","Adani Power","Power"),
    ("ADANIGREEN","Adani Green Energy","Renewable"),
    ("ADANIPORTS","Adani Ports","Ports"),
    ("ADANIENT","Adani Enterprises","Diversified"),
    ("ADANITRANS","Adani Transmission","Power Transmission"),
    ("TATAPOWER","Tata Power","Power"),
    ("TORNTPOWER","Torrent Power","Power"),
    ("CESC","CESC","Power"),
    ("NHPC","NHPC","PSU Hydro"),
    ("SJVN","SJVN","PSU Hydro"),
    ("SUZLON","Suzlon Energy","Wind Energy"),
    ("JSWENERGY","JSW Energy","Power"),
    ("KEC","KEC International","Power Transmission"),
    ("KALPATPOWR","Kalpataru Power","Power Infra"),
    # Consumer & FMCG
    ("HINDUNILVR","Hindustan Unilever","FMCG"),
    ("ITC","ITC","FMCG"),
    ("NESTLEIND","Nestle India","FMCG"),
    ("BRITANNIA","Britannia Industries","FMCG"),
    ("DABUR","Dabur India","FMCG"),
    ("MARICO","Marico","FMCG"),
    ("GODREJCP","Godrej Consumer Products","FMCG"),
    ("COLPAL","Colgate-Palmolive India","FMCG"),
    ("VBL","Varun Beverages","Beverages"),
    ("TATACONSUM","Tata Consumer Products","FMCG"),
    ("EMAMILTD","Emami","FMCG"),
    ("RADICO","Radico Khaitan","Spirits"),
    ("UBL","United Breweries","Beer"),
    ("JYOTHYLAB","Jyothy Labs","FMCG"),
    ("TITAN","Titan Company","Jewellery Watches"),
    ("KALYANKJIL","Kalyan Jewellers","Jewellery"),
    ("SENCO","Senco Gold","Jewellery"),
    ("TRENT","Trent","Retail"),
    ("DMART","Avenue Supermarts","Retail"),
    ("ABFRL","Aditya Birla Fashion","Retail"),
    ("JUBLFOOD","Jubilant Foodworks","QSR"),
    ("DEVYANI","Devyani International","QSR"),
    ("SAPPHIRE","Sapphire Foods","QSR"),
    ("WESTLIFE","Westlife Foodworld","QSR"),
    ("BIKAJI","Bikaji Foods","Snacks"),
    ("HONASA","Honasa Consumer","D2C Beauty"),
    ("VEDANT","Vedant Fashions","Ethnic Apparel"),
    ("DIXON","Dixon Technologies","EMS Electronics"),
    ("KAYNES","Kaynes Technology","EMS Electronics"),
    ("AMBER","Amber Enterprises","AC Components"),
    ("VGUARD","V-Guard Industries","Consumer Electronics"),
    ("VOLTAS","Voltas","Consumer Durables"),
    ("BLUESTAR","Blue Star","AC Refrigeration"),
    ("HAVELLS","Havells India","Electricals"),
    ("POLYCAB","Polycab India","Cables Wires"),
    ("KEI","KEI Industries","Cables Wires"),
    # Automobiles
    ("TATAMOTORS","Tata Motors","Auto"),
    ("M&M","Mahindra Mahindra","Auto"),
    ("MARUTI","Maruti Suzuki","Auto"),
    ("BAJAJ-AUTO","Bajaj Auto","Two Wheeler"),
    ("HEROMOTOCO","Hero MotoCorp","Two Wheeler"),
    ("EICHERMOT","Eicher Motors","Two Wheeler CV"),
    ("TVSMOTOR","TVS Motor","Two Wheeler"),
    ("ASHOKLEY","Ashok Leyland","Commercial Vehicle"),
    ("ESCORTS","Escorts Kubota","Tractors"),
    ("BOSCHLTD","Bosch India","Auto Ancillary"),
    ("MOTHERSON","Samvardhana Motherson","Auto Ancillary"),
    ("BHARATFORG","Bharat Forge","Forging"),
    ("SUNDRMFAST","Sundram Fasteners","Auto Ancillary"),
    ("TIINDIA","Tube Investments","Auto Ancillary"),
    ("APOLLOTYRE","Apollo Tyres","Tyres"),
    ("MRF","MRF","Tyres"),
    ("CEATLTD","CEAT","Tyres"),
    ("BALKRISIND","Balkrishna Industries","Specialty Tyres"),
    ("EXIDEIND","Exide Industries","Batteries"),
    ("AMARAJABAT","Amara Raja Energy","Batteries"),
    ("SONACOMS","Sona BLW Precision","Auto Ancillary"),
    ("ENDURANCE","Endurance Technologies","Auto Ancillary"),
    ("OLECTRA","Olectra Greentech","EV Buses"),
    ("JBMA","JBM Auto","EV Buses"),
    # Pharma & Healthcare
    ("SUNPHARMA","Sun Pharmaceutical","Pharma"),
    ("DRREDDY","Dr Reddys Labs","Pharma"),
    ("CIPLA","Cipla","Pharma"),
    ("DIVISLAB","Divis Laboratories","Pharma CDMO"),
    ("BIOCON","Biocon","Biotech"),
    ("LUPIN","Lupin","Pharma"),
    ("AUROPHARMA","Aurobindo Pharma","Pharma"),
    ("TORNTPHARM","Torrent Pharma","Pharma"),
    ("ALKEM","Alkem Laboratories","Pharma"),
    ("IPCA","Ipca Laboratories","Pharma"),
    ("GLAND","Gland Pharma","Injectables"),
    ("NATCOPHARM","Natco Pharma","Pharma"),
    ("GRANULES","Granules India","Pharma API"),
    ("LAURUSLABS","Laurus Labs","Pharma CDMO"),
    ("PFIZER","Pfizer India","MNC Pharma"),
    ("ABBOTINDIA","Abbott India","MNC Pharma"),
    ("LALPATHLAB","Dr Lal PathLabs","Diagnostics"),
    ("METROPOLIS","Metropolis Healthcare","Diagnostics"),
    ("APOLLOHOSP","Apollo Hospitals","Hospital"),
    ("MAXHEALTH","Max Healthcare","Hospital"),
    ("FORTIS","Fortis Healthcare","Hospital"),
    ("NARAYANHRU","Narayana Hrudayalaya","Hospital"),
    ("RAINBOW","Rainbow Childrens Medicare","Hospital"),
    ("ASTERDM","Aster DM Healthcare","Hospital"),
    ("POLYMED","Poly Medicure","Med Devices"),
    # Infrastructure, Capital Goods & Defence
    ("LT","Larsen Toubro","Infrastructure"),
    ("LTTS","L&T Technology Services","Engineering IT"),
    ("SIEMENS","Siemens India","Capital Goods"),
    ("ABB","ABB India","Capital Goods"),
    ("BHEL","BHEL","PSU Engineering"),
    ("HAL","Hindustan Aeronautics","Defence"),
    ("BEL","Bharat Electronics","Defence Electronics"),
    ("MAZDOCK","Mazagon Dock","Defence Shipbuilding"),
    ("GRSE","Garden Reach Shipbuilders","Defence Shipbuilding"),
    ("COCHINSHIP","Cochin Shipyard","Shipbuilding"),
    ("DATAPATTNS","Data Patterns India","Defence Electronics"),
    ("IDEAFORGE","Ideaforge Technology","Drones"),
    ("PARAS","Paras Defence","Defence"),
    ("BEML","BEML Limited","PSU Engineering"),
    ("IRCTC","IRCTC","PSU Travel"),
    ("CONCOR","Container Corp India","Rail Logistics"),
    ("DELHIVERY","Delhivery","Logistics"),
    ("BLUEDART","Blue Dart Express","Logistics"),
    ("JSWINFRA","JSW Infrastructure","Ports"),
    ("GMRINFRA","GMR Airports Infra","Airports"),
    ("INTERGLOBE","IndiGo","Aviation"),
    ("IRB","IRB Infrastructure","Roads"),
    ("KNR","KNR Constructions","Roads"),
    ("NCC","NCC Limited","Construction"),
    ("PNCINFRA","PNC Infratech","Infrastructure"),
    ("ASHOKA","Ashoka Buildcon","Roads"),
    ("THERMAX","Thermax","Industrial"),
    ("CUMMINSIND","Cummins India","Industrial Engines"),
    ("ELGIEQUIP","Elgi Equipments","Compressors"),
    ("AIAENG","AIA Engineering","Engineering"),
    ("GRINDWELL","Grindwell Norton","Abrasives"),
    # Metals & Mining
    ("TATASTEEL","Tata Steel","Steel"),
    ("JSWSTEEL","JSW Steel","Steel"),
    ("SAIL","Steel Authority India","PSU Steel"),
    ("HINDALCO","Hindalco Industries","Aluminium"),
    ("VEDL","Vedanta","Diversified Metals"),
    ("NATIONALUM","National Aluminium","PSU Aluminium"),
    ("NMDC","NMDC","PSU Iron Ore"),
    ("HINDZINC","Hindustan Zinc","Zinc"),
    ("JINDALSTEL","Jindal Steel Power","Steel"),
    ("APL","APL Apollo Tubes","Steel Products"),
    ("RATNAMANI","Ratnamani Metals","Steel Pipes"),
    ("WELCORP","Welspun Corp","Steel Pipes"),
    ("SHYAMMETL","Shyam Metalics","Metals"),
    ("HINDCOPPER","Hindustan Copper","PSU Copper"),
    ("MOIL","MOIL Limited","PSU Manganese"),
    # Specialty Chemicals
    ("PIDILITIND","Pidilite Industries","Adhesives"),
    ("SRF","SRF Limited","Specialty Chem"),
    ("DEEPAKNTR","Deepak Nitrite","Specialty Chem"),
    ("TATACHEM","Tata Chemicals","Chemicals"),
    ("COROMANDEL","Coromandel International","Agrochemicals"),
    ("UPL","UPL Limited","Agrochemicals"),
    ("NAVINFLUOR","Navin Fluorine","Fluorochemicals"),
    ("ALKYLAMINE","Alkyl Amines Chemicals","Specialty Chem"),
    ("VINATIORGA","Vinati Organics","Specialty Chem"),
    ("GALAXYSURF","Galaxy Surfactants","Surfactants"),
    ("CLEAN","Clean Science Technology","Specialty Chem"),
    ("FINEORG","Fine Organic Industries","Specialty Chem"),
    ("ROSSARI","Rossari Biotech","Specialty Chem"),
    ("ANUPAM","Anupam Rasayan","Specialty Chem"),
    ("NOCIL","NOCIL","Rubber Chemicals"),
    ("ATUL","Atul Limited","Diversified Chem"),
    ("ASTRAL","Astral Limited","Pipes Adhesives"),
    ("SUPREMEIND","Supreme Industries","Plastic Pipes"),
    ("FINOLEX","Finolex Industries","Pipes"),
    ("PRINCEPIPE","Prince Pipes","Pipes"),
    # Cement & Real Estate
    ("ULTRACEMCO","UltraTech Cement","Cement"),
    ("SHREECEM","Shree Cement","Cement"),
    ("AMBUJACEM","Ambuja Cements","Cement"),
    ("ACC","ACC Limited","Cement"),
    ("JKCEMENT","JK Cement","Cement"),
    ("RAMCOCEM","Ramco Cements","Cement"),
    ("DALMIA","Dalmia Bharat","Cement"),
    ("NUVOCO","Nuvoco Vistas","Cement"),
    ("DLF","DLF Limited","Real Estate"),
    ("GODREJPROP","Godrej Properties","Real Estate"),
    ("OBEROIRLTY","Oberoi Realty","Real Estate"),
    ("LODHA","Macrotech Developers","Real Estate"),
    ("PHOENIXLTD","Phoenix Mills","Real Estate Retail"),
    ("BRIGADE","Brigade Enterprises","Real Estate"),
    ("SOBHA","Sobha Limited","Real Estate"),
    ("PRESTIGE","Prestige Estates","Real Estate"),
    ("KAJARIA","Kajaria Ceramics","Ceramics"),
    ("CENTURYPLY","Century Plyboards","Plywood"),
    ("GREENPANEL","Greenpanel Industries","MDF Panels"),
    # Telecom, Media & Others
    ("BHARTIARTL","Bharti Airtel","Telecom"),
    ("INDUSTOWER","Indus Towers","Telecom Infrastructure"),
    ("TATACOMM","Tata Communications","Enterprise Telecom"),
    ("HFCL","HFCL Limited","Telecom Infra"),
    ("STLTECH","Sterlite Technologies","Optical Fiber"),
    ("ZEEL","Zee Entertainment","Media"),
    ("SUNTV","Sun TV Network","Media"),
    ("SAREGAMA","Saregama India","Music"),
    # Textiles & Agri
    ("PAGEIND","Page Industries","Premium Garments"),
    ("KPRMILL","KPR Mill","Textiles"),
    ("WELSPUNIND","Welspun India","Home Textiles"),
    ("TRIDENT","Trident Limited","Textiles Paper"),
    ("VARDHMAN","Vardhman Textiles","Textiles"),
    ("VEDANT","Vedant Fashions","Ethnic Apparel"),
    ("BALRAMCHIN","Balrampur Chini Mills","Sugar"),
    ("CHAMBAL","Chambal Fertilizers","Fertilizers"),
    ("COROMANDEL","Coromandel International","Agrochemicals"),
    ("KRBL","KRBL Limited","Rice"),
    ("GRASIM","Grasim Industries","Diversified"),
]

NASDAQ500 = [
    # Mega Cap Tech
    ("AAPL","Apple","Technology"),
    ("MSFT","Microsoft","Technology"),
    ("GOOGL","Alphabet Class A","Technology"),
    ("AMZN","Amazon","Consumer Cloud"),
    ("NVDA","NVIDIA","Semiconductors"),
    ("META","Meta Platforms","Social Media"),
    ("TSLA","Tesla","EV Auto"),
    ("NFLX","Netflix","Streaming"),
    ("ADBE","Adobe","Software"),
    # Semiconductors
    ("AMD","Advanced Micro Devices","Semiconductors"),
    ("INTC","Intel","Semiconductors"),
    ("QCOM","Qualcomm","Semiconductors"),
    ("AVGO","Broadcom","Semiconductors"),
    ("TXN","Texas Instruments","Semiconductors"),
    ("AMAT","Applied Materials","Semiconductor Equip"),
    ("LRCX","Lam Research","Semiconductor Equip"),
    ("MU","Micron Technology","Semiconductors"),
    ("MRVL","Marvell Technology","Semiconductors"),
    ("KLAC","KLA Corporation","Semiconductor Equip"),
    ("ASML","ASML Holding","Semiconductor Equip"),
    ("SNPS","Synopsys","EDA Software"),
    ("CDNS","Cadence Design","EDA Software"),
    ("ARM","Arm Holdings","Semiconductors"),
    ("SMCI","Super Micro Computer","Servers"),
    ("ON","ON Semiconductor","Semiconductors"),
    ("MPWR","Monolithic Power Systems","Semiconductors"),
    ("AMBA","Ambarella","AI Chips"),
    ("ALGM","Allegro MicroSystems","Semiconductors"),
    ("PI","Impinj","RFID Chips"),
    # Cloud & SaaS
    ("CRM","Salesforce","CRM Cloud"),
    ("NOW","ServiceNow","Cloud ITSM"),
    ("WDAY","Workday","HR Cloud"),
    ("SNOW","Snowflake","Data Cloud"),
    ("DDOG","Datadog","Observability"),
    ("PANW","Palo Alto Networks","Cybersecurity"),
    ("CRWD","CrowdStrike","Cybersecurity"),
    ("ZS","Zscaler","Cybersecurity"),
    ("FTNT","Fortinet","Cybersecurity"),
    ("OKTA","Okta","Identity Security"),
    ("TEAM","Atlassian","Dev Tools"),
    ("MDB","MongoDB","Database"),
    ("ORCL","Oracle","Enterprise Software"),
    ("INTU","Intuit","Financial Software"),
    ("VEEV","Veeva Systems","Life Sciences Cloud"),
    ("HUBS","HubSpot","Marketing SaaS"),
    ("NET","Cloudflare","Network Security"),
    ("GTLB","GitLab","DevSecOps"),
    ("BILL","Bill.com","SMB Finance SaaS"),
    ("PCTY","Paylocity","HR SaaS"),
    ("PAYC","Paycom Software","HR SaaS"),
    ("ZI","ZoomInfo","B2B Intelligence"),
    ("BRZE","Braze","Marketing Platform"),
    ("TTD","The Trade Desk","Programmatic Ads"),
    ("APP","AppLovin","AdTech Mobile"),
    ("CVLT","Commvault Systems","Data Protection"),
    ("VRNS","Varonis Systems","Data Security"),
    ("QLYS","Qualys","Cloud Security"),
    ("TENB","Tenable Holdings","Cybersecurity"),
    ("S","SentinelOne","Cybersecurity"),
    ("CYBR","CyberArk Software","Identity Security"),
    ("PATH","UiPath","RPA Automation"),
    ("MNDY","Monday.com","Project Management"),
    ("ASAN","Asana","Work Management"),
    # Biotech & Healthcare
    ("AMGN","Amgen","Biotech"),
    ("GILD","Gilead Sciences","Biotech"),
    ("BIIB","Biogen","Biotech"),
    ("REGN","Regeneron Pharma","Biotech"),
    ("VRTX","Vertex Pharma","Biotech"),
    ("MRNA","Moderna","mRNA Biotech"),
    ("ILMN","Illumina","Genomics"),
    ("IDXX","IDEXX Laboratories","Animal Health"),
    ("DXCM","Dexcom","Diabetes Tech"),
    ("ISRG","Intuitive Surgical","Surgical Robotics"),
    ("ALGN","Align Technology","Clear Aligners"),
    ("HOLX","Hologic","Women Health"),
    ("NTRA","Natera","Genetic Testing"),
    ("EXAS","Exact Sciences","Cancer Diagnostics"),
    ("BEAM","Beam Therapeutics","Gene Editing"),
    ("CRSP","CRISPR Therapeutics","Gene Editing"),
    ("ALNY","Alnylam Pharma","RNA Medicines"),
    ("IONS","Ionis Pharma","Genetic Medicines"),
    ("SGEN","Seagen","Oncology"),
    ("HIMS","Hims Hers Health","Telehealth"),
    ("TDOC","Teladoc Health","Telehealth"),
    ("ACCD","Accolade","Health Navigation"),
    ("CERT","Certara","Drug Development"),
    ("RXRX","Recursion Pharma","AI Drug Discovery"),
    ("SDGR","Schrodinger","Drug Discovery AI"),
    # Fintech & Payments
    ("PYPL","PayPal","Fintech"),
    ("SQ","Block Inc","Fintech"),
    ("COIN","Coinbase","Crypto Exchange"),
    ("HOOD","Robinhood Markets","Retail Investing"),
    ("SOFI","SoFi Technologies","Neobank"),
    ("AFRM","Affirm Holdings","BNPL"),
    ("UPST","Upstart Holdings","AI Lending"),
    ("FOUR","Shift4 Payments","Payments"),
    ("MQ","Marqeta","Card Issuing"),
    ("RELY","Remitly Global","Remittances"),
    ("LMND","Lemonade","InsurTech"),
    ("ROOT","Root Insurance","Auto InsurTech"),
    # Consumer & E-commerce
    ("MELI","MercadoLibre","LatAm E-commerce"),
    ("SHOP","Shopify","E-commerce Platform"),
    ("BKNG","Booking Holdings","Online Travel"),
    ("ABNB","Airbnb","Travel Platform"),
    ("EXPE","Expedia Group","Online Travel"),
    ("UBER","Uber Technologies","Ride-sharing"),
    ("LYFT","Lyft","Ride-sharing"),
    ("DASH","DoorDash","Food Delivery"),
    ("CART","Instacart Maplebear","Grocery Delivery"),
    ("ETSY","Etsy","Crafts Marketplace"),
    ("EBAY","eBay","E-commerce"),
    ("CHWY","Chewy","Pet E-commerce"),
    ("W","Wayfair","Online Home Goods"),
    ("DKNG","DraftKings","Sports Betting"),
    ("GLBE","Global-E Online","Cross-border Commerce"),
    # AI & Next Gen
    ("PLTR","Palantir Technologies","AI Data Analytics"),
    ("AI","C3.ai","Enterprise AI"),
    ("SOUN","SoundHound AI","Voice AI"),
    ("IONQ","IonQ","Quantum Computing"),
    ("RGTI","Rigetti Computing","Quantum Computing"),
    ("RBLX","Roblox","Gaming Metaverse"),
    ("U","Unity Software","Game Engine"),
    ("TTWO","Take-Two Interactive","Gaming"),
    ("EA","Electronic Arts","Gaming"),
    # Clean Energy
    ("ENPH","Enphase Energy","Solar Microinverters"),
    ("SEDG","SolarEdge Technologies","Solar Inverters"),
    ("FSLR","First Solar","Solar Panels"),
    ("PLUG","Plug Power","Green Hydrogen"),
    ("BLNK","Blink Charging","EV Charging"),
    ("CHPT","ChargePoint Holdings","EV Charging"),
    ("EVGO","EVgo","EV Charging"),
    ("FLNC","Fluence Energy","Energy Storage"),
    ("ARRY","Array Technologies","Solar Tracking"),
    # Media & Streaming
    ("SPOT","Spotify Technology","Audio Streaming"),
    ("ROKU","Roku","Streaming Platform"),
    ("PINS","Pinterest","Social Media"),
    ("SNAP","Snap Inc","Social Media"),
    ("BMBL","Bumble","Dating App"),
    ("MTCH","Match Group","Dating Apps"),
    # Industrials & Others
    ("ODFL","Old Dominion Freight","Transportation"),
    ("SAIA","Saia Inc","Trucking"),
    ("CPRT","Copart","Auto Auctions"),
    ("VRSK","Verisk Analytics","Data Analytics"),
    ("CSGP","CoStar Group","Real Estate Data"),
    ("ANSS","Ansys Inc","Simulation"),
    ("CDW","CDW Corporation","IT Solutions"),
    ("FAST","Fastenal","Industrial Distribution"),
    ("KTOS","Kratos Defense","Defence Tech"),
    ("AVAV","AeroVironment","Drones Defence"),
    ("CVNA","Carvana","Online Auto"),
    ("OPEN","Opendoor Technologies","PropTech"),
    ("RDFN","Redfin","PropTech"),
    ("ZM","Zoom Video","Video Communications"),
    ("RH","RH Restoration Hardware","Home Furnishings"),
    ("SE","Sea Limited","SE Asia Digital"),
    ("GRAB","Grab Holdings","SE Asia Super App"),
]


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def now_ist() -> str:
    ist = pytz.timezone("Asia/Kolkata")
    return datetime.now(ist).strftime("%d-%b-%Y %H:%M IST")

def is_weekend() -> bool:
    return datetime.utcnow().weekday() >= 5  # Sat=5, Sun=6

def load_json(path: str, default=None):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return default if default is not None else {}

def save_json(path: str, data):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def pct(a, b) -> float:
    """Percentage change from b to a."""
    return ((a - b) / b * 100) if b else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# PRICE FETCHER  (parallel, fast)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_prices_batch(tickers: list, suffix: str = "") -> dict:
    """
    Fetch 1-year daily OHLCV for all tickers in one yfinance call.
    suffix = ".NS" for NSE, "" for Nasdaq.
    Returns: { "SYMBOL": {"price": float, "high52w": float, "low52w": float} }
    """
    yf_tickers = [t + suffix for t in tickers]
    results = {}

    try:
        print(f"  Fetching {len(yf_tickers)} tickers in batch...", flush=True)
        raw = yf.download(
            tickers=yf_tickers,
            period="1y",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True,
        )

        for sym, yf_sym in zip(tickers, yf_tickers):
            try:
                if len(tickers) == 1:
                    df = raw
                else:
                    df = raw[yf_sym] if yf_sym in raw.columns.get_level_values(0) else None

                if df is None or df.empty:
                    continue

                df = df.dropna(subset=["Close"])
                if len(df) < 30:
                    continue

                results[sym] = {
                    "price":   round(float(df["Close"].iloc[-1]), 2),
                    "high52w": round(float(df["High"].max()), 2),
                    "low52w":  round(float(df["Low"].min()), 2),
                    "prev":    round(float(df["Close"].iloc[-2]), 2) if len(df) > 1 else 0,
                }
            except Exception:
                continue

    except Exception as e:
        print(f"  Batch fetch error: {e}", flush=True)

    return results


def fetch_prices_chunked(universe: list, suffix: str, chunk_size: int = 50) -> dict:
    """Split universe into chunks, fetch each in parallel via ThreadPoolExecutor."""
    tickers = [s[0] for s in universe]
    chunks = [tickers[i:i+chunk_size] for i in range(0, len(tickers), chunk_size)]
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
# SIGNAL DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def check_portfolio(holdings: list, prices: dict, cfg: dict) -> tuple:
    """
    For each active holding check:
    1. Stop loss breach → SELL signal
    2. Peak moved → floor update (only alert if floor changes >threshold%)
    Returns: (updated_holdings, sells, floors)
    """
    trailing_stop = cfg["trailing_stop_pct"] / 100
    floor_threshold = cfg["floor_alert_threshold_pct"] / 100

    sells, floors, updated = [], [], []

    for h in holdings:
        if h.get("status") == "SOLD":
            updated.append(h)
            continue

        sym = h["symbol"]
        p = prices.get(sym)
        if not p:
            updated.append(h)
            continue

        cur = p["price"]
        peak = h.get("peak_price", h["entry_price"])
        floor = h.get("floor_price", h["entry_price"] * (1 - trailing_stop))
        invested = h["entry_price"] * h["qty"]
        cur_value = cur * h["qty"]
        pnl_pct = pct(cur, h["entry_price"])

        # Update current price fields
        h = {**h, "current_price": cur, "current_value": round(cur_value, 2),
             "pnl": round(cur_value - invested, 2), "pnl_pct": round(pnl_pct, 2)}

        if cur <= floor:
            # SELL signal
            sells.append({
                "symbol": sym, "name": h.get("name", sym), "sector": h.get("sector", ""),
                "entry_price": h["entry_price"], "peak_price": round(peak, 2),
                "floor_price": round(floor, 2), "current_price": cur,
                "qty": h["qty"], "invested": round(invested, 2),
                "pnl_pct": round(pnl_pct, 2),
            })
            h["status"] = "STOP HIT"
        else:
            # Update peak if new high
            new_peak = max(peak, cur)
            new_floor = round(new_peak * (1 - trailing_stop), 2)
            old_floor = floor
            floor_change_pct = pct(new_floor, old_floor)

            if floor_change_pct >= cfg["floor_alert_threshold_pct"]:
                floors.append({
                    "symbol": sym, "name": h.get("name", sym), "sector": h.get("sector", ""),
                    "current_price": cur, "new_peak": round(new_peak, 2),
                    "old_floor": round(old_floor, 2), "new_floor": new_floor,
                    "floor_change_pct": round(floor_change_pct, 2),
                })

            h["peak_price"] = round(new_peak, 2)
            h["floor_price"] = new_floor

        updated.append(h)

    return updated, sells, floors


def scan_for_signals(universe: list, prices: dict, portfolio_symbols: set,
                     cfg: dict, portfolio_value: float, currency: str) -> list:
    """Scan watchlist for entry signals based on ATH target."""
    entry_mode = cfg["entry_mode"]
    position_size = portfolio_value * cfg["position_pct"] / 100
    trailing_stop = cfg["trailing_stop_pct"] / 100
    buys = []

    for sym, name, sector in universe:
        if sym in portfolio_symbols:
            continue
        p = prices.get(sym)
        if not p:
            continue

        cur = p["price"]
        high52w = p["high52w"]
        low52w = p["low52w"]

        # ATH target based on entry mode
        ath_target = high52w * (entry_mode / 100)
        pct_from_high = pct(cur, high52w)

        if cur >= ath_target:
            qty = max(1, int(position_size / cur))
            floor = round(cur * (1 - trailing_stop), 2)
            buys.append({
                "symbol": sym, "name": name, "sector": sector,
                "current_price": cur, "high52w": high52w, "low52w": low52w,
                "ath_target": round(ath_target, 2), "entry_mode": entry_mode,
                "pct_from_high": round(pct_from_high, 2),
                "suggested_floor": floor,
                "suggested_qty": qty,
                "suggested_amount": round(qty * cur, 2),
                "currency": currency,
            })

    # Sort: stocks closest to ATH first (most momentum)
    buys.sort(key=lambda x: x["pct_from_high"], reverse=True)
    return buys


# ─────────────────────────────────────────────────────────────────────────────
# MAIN SCAN
# ─────────────────────────────────────────────────────────────────────────────

def run_market_scan(market: str, universe: list, suffix: str,
                    portfolio: list, cfg: dict,
                    portfolio_value: float, currency: str) -> dict:
    t0 = time.time()
    print(f"\n{'='*60}", flush=True)
    print(f"  {market.upper()} SCAN — {now_ist()}", flush=True)
    print(f"  Universe: {len(universe)} stocks | Entry mode: {cfg['entry_mode']}% ATH", flush=True)
    print(f"{'='*60}", flush=True)

    # Fetch all prices in parallel
    prices = fetch_prices_chunked(universe, suffix)
    print(f"  Fetched prices for {len(prices)}/{len(universe)} stocks", flush=True)

    # Portfolio symbols
    active = [h for h in portfolio if h.get("status") == "ACTIVE"]
    portfolio_syms = {h["symbol"] for h in active}
    slots_free = max(0, cfg["max_stocks"] - len(active))

    # Check portfolio
    updated_portfolio, sells, floors = check_portfolio(active, prices, cfg)

    # Scan for buy signals (only if slots available)
    buys = []
    if slots_free > 0:
        buys = scan_for_signals(universe, prices, portfolio_syms, cfg,
                                portfolio_value, currency)
        buys = buys[:slots_free]  # Limit to available slots
    else:
        print(f"  Portfolio full ({cfg['max_stocks']} stocks) — skipping buy scan", flush=True)

    elapsed = round(time.time() - t0, 1)
    print(f"  BUY signals: {len(buys)} | SELL alerts: {len(sells)} | Floor updates: {len(floors)}", flush=True)
    print(f"  Scan time: {elapsed}s", flush=True)

    return {
        "buys": buys,
        "sells": sells,
        "floors": floors,
        "portfolio": updated_portfolio,
        "stats": {
            "scanned": len(prices),
            "universe": len(universe),
            "buy_signals": len(buys),
            "sell_signals": len(sells),
            "floor_updates": len(floors),
            "slots_free": slots_free,
            "scan_seconds": elapsed,
        },
        "scan_time_ist": now_ist(),
    }


def main():
    print(f"\n🔍 MOMENTUM SCANNER STARTING — {now_ist()}", flush=True)

    # Load config and portfolio
    cfg_raw   = load_json("config.json", {})
    strategy  = cfg_raw.get("strategy", {})
    india_cfg = strategy.get("india", {})
    us_cfg    = strategy.get("us", {})
    usd_inr   = strategy.get("usd_inr_rate", 84.5)

    portfolio_raw = load_json("portfolio.json", {"india": [], "us": []})
    india_portfolio = portfolio_raw.get("india", [])
    us_portfolio    = portfolio_raw.get("us", [])

    # Decide which markets to scan based on env var (set by GitHub Actions)
    scan_market = os.environ.get("SCAN_MARKET", "both").lower()
    results = {}

    if scan_market in ("india", "both"):
        results["india"] = run_market_scan(
            market="India Nifty 500",
            universe=NIFTY500,
            suffix=".NS",
            portfolio=india_portfolio,
            cfg=india_cfg,
            portfolio_value=india_cfg.get("portfolio_value_inr", 1000000),
            currency="₹",
        )
        # Save updated portfolio back
        portfolio_raw["india"] = results["india"]["portfolio"]

    if scan_market in ("us", "both"):
        results["us"] = run_market_scan(
            market="US Nasdaq",
            universe=NASDAQ500,
            suffix="",
            portfolio=us_portfolio,
            cfg=us_cfg,
            portfolio_value=us_cfg.get("portfolio_value_usd", 10000),
            currency="$",
        )
        portfolio_raw["us"] = results["us"]["portfolio"]

    # Save updated portfolio (peak prices, floors updated)
    save_json("portfolio.json", portfolio_raw)

    # Build signals.json
    existing = load_json("data/signals.json", {})
    signals = {
        "last_scan_ist": now_ist(),
        "last_india_scan_ist": results.get("india", {}).get("scan_time_ist",
                                existing.get("last_india_scan_ist", "Never")),
        "last_us_scan_ist": results.get("us", {}).get("scan_time_ist",
                             existing.get("last_us_scan_ist", "Never")),
        "usd_inr": usd_inr,
        "india": results.get("india", existing.get("india", {})),
        "us":    results.get("us",    existing.get("us", {})),
    }
    save_json("data/signals.json", signals)
    print(f"\n✅ signals.json written — {now_ist()}", flush=True)

    # Summary
    total_signals = (
        len(results.get("india", {}).get("buys", [])) +
        len(results.get("india", {}).get("sells", [])) +
        len(results.get("us", {}).get("buys", [])) +
        len(results.get("us", {}).get("sells", []))
    )
    print(f"📊 Total actionable signals: {total_signals}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
