"""Application configuration and constants."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Environment (local, prod)
ENVIRONMENT = os.getenv("ENVIRONMENT", "prod")

# Market data & cache configuration (fixed, not env-driven)
CACHE_DIR = Path("data")
CACHE_FILE = CACHE_DIR / "cache.pkl"
CACHE_VALIDITY_HOURS = 24
MARKET_DATA_PERIOD = "1y"
MARKET_DATA_MAX_RETRIES = 3
MARKET_DATA_RETRY_DELAY_SECONDS = 2
MARKET_DATA_ENABLE_RETRY = True

# Telegram bot token
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not set in .env file")

# List of admin IDs for notifications
ADMIN_IDS = [169675602, 7035744629]

# Rebalancing interval in trading days
REBALANCE_INTERVAL_DAYS = 22

# Custom tickers to add to S&P 500 list
CUSTOM_TICKERS = ['RGTI', 'QBTS', 'QUBT']

# Custom tickers for paper_medium strategy
SNP500_TICKERS = ['MMM', 'AOS', 'ABT', 'ABBV', 'ACN', 'ADBE', 'AMD', 'AES', 'AFL', 'A', 'APD', 'ABNB', 'AKAM', 'ALB', 'ARE', 'ALGN', 'ALLE', 'LNT', 'ALL', 'GOOGL', 'GOOG', 'MO', 'AMZN', 'AMCR', 'AEE', 'AEP', 'AXP', 'AIG', 'AMT', 'AWK', 'AMP', 'AME', 'AMGN', 'APH', 'ADI', 'AON', 'APA', 'APO', 'AAPL', 'AMAT', 'APTV', 'ACGL', 'ADM', 'ANET', 'AJG', 'AIZ', 'T', 'ATO', 'ADSK', 'ADP', 'AZO', 'AVB', 'AVY', 'AXON', 'BKR', 'BALL', 'BAC', 'BAX', 'BDX', 'BBY', 'TECH', 'BIIB', 'BLK', 'BX', 'BK', 'BA', 'BKNG', 'BWA', 'BSX', 'BMY', 'AVGO', 'BR', 'BRO', 'BLDR', 'BG', 'BXP', 'CHRW', 'CDNS', 'CZR', 'CPT', 'CPB', 'COF', 'CAH', 'KMX', 'CCL', 'CARR', 'CAT', 'CBOE', 'CBRE', 'CDW', 'CE', 'COR', 'CNC', 'CNP', 'CF', 'CRL', 'SCHW', 'CHTR', 'CVX', 'CMG', 'CB', 'CHD', 'CI', 'CINF', 'CTAS', 'CSCO', 'C', 'CFG', 'CLX', 'CME', 'CMS', 'KO', 'CTSH', 'CL', 'CMCSA', 'CAG', 'COP', 'ED', 'STZ', 'CEG', 'COO', 'CPRT', 'GLW', 'CPAY', 'CTVA', 'CSGP', 'COST', 'CTRA', 'CRWD', 'CCI', 'CSX', 'CMI', 'CVS', 'DHR', 'DRI', 'DVA', 'DAY', 'DECK', 'DE', 'DELL', 'DAL', 'DVN', 'DXCM', 'FANG', 'DLR', 'DG', 'DLTR', 'D', 'DPZ', 'DOV', 'DOW', 'DHI', 'DTE', 'DUK', 'DD', 'EMN', 'ETN', 'EBAY', 'ECL', 'EIX', 'EW', 'EA', 'ELV', 'EMR', 'ENPH', 'EOG', 'EPAM', 'EQT', 'EFX', 'EQIX', 'EQR', 'ERIE', 'ESS', 'EL', 'EG', 'EVRG', 'ES', 'EXC', 'EXPE', 'EXPD', 'EXR', 'XOM', 'FFIV', 'FDS', 'FICO', 'FAST', 'FRT', 'FDX', 'FIS', 'FITB', 'FSLR', 'FE', 'FI', 'FMC', 'F', 'FTNT', 'FTV', 'FOXA', 'FOX', 'BEN', 'FCX', 'GRMN', 'IT', 'GE', 'GEHC', 'GEV', 'GEN', 'GNRC', 'GD', 'GIS', 'GM', 'GPC', 'GILD', 'GPN', 'GL', 'GDDY', 'GS', 'HAL', 'HIG', 'HAS', 'HCA', 'DOC', 'HSIC', 'HSY', 'HPE', 'HLT', 'HOLX', 'HD', 'HON', 'HRL', 'HST', 'HWM', 'HPQ', 'HUBB', 'HUM', 'HBAN', 'HII', 'IBM', 'IEX', 'IDXX', 'ITW', 'INCY', 'IR', 'PODD', 'INTC', 'ICE', 'IFF', 'IP', 'IPG', 'INTU', 'ISRG', 'IVZ', 'INVH', 'IQV', 'IRM', 'JBHT', 'JBL', 'JKHY', 'J', 'JNJ', 'JCI', 'JPM', 'K', 'KVUE', 'KDP', 'KEY', 'KEYS', 'KMB', 'KIM', 'KMI', 'KKR', 'KLAC', 'KHC', 'KR', 'LHX', 'LH', 'LRCX', 'LW', 'LVS', 'LDOS', 'LEN', 'LII', 'LLY', 'LIN', 'LYV', 'LKQ', 'LMT', 'L', 'LOW', 'LULU', 'LYB', 'MTB', 'MPC', 'MKTX', 'MAR', 'MMC', 'MLM', 'MAS', 'MA', 'MTCH', 'MKC', 'MCD', 'MCK', 'MDT', 'MRK', 'META', 'MET', 'MTD', 'MGM', 'MCHP', 'MU', 'MSFT', 'MAA', 'MRNA', 'MHK', 'MOH', 'TAP', 'MDLZ', 'MPWR', 'MNST', 'MCO', 'MS', 'MOS', 'MSI', 'MSCI', 'NDAQ', 'NTAP', 'NFLX', 'NEM', 'NWSA', 'NWS', 'NEE', 'NKE', 'NI', 'NDSN', 'NSC', 'NTRS', 'NOC', 'NCLH', 'NRG', 'NUE', 'NVDA', 'NVR', 'NXPI', 'ORLY', 'OXY', 'ODFL', 'OMC', 'ON', 'OKE', 'ORCL', 'OTIS', 'PCAR', 'PKG', 'PLTR', 'PANW', 'PSKY', 'PH', 'PAYX', 'PAYC', 'PYPL', 'PNR', 'PEP', 'PFE', 'PCG', 'PM', 'PSX', 'PNW', 'PNC', 'POOL', 'PPG', 'PPL', 'PFG', 'PG', 'PGR', 'PLD', 'PRU', 'PEG', 'PTC', 'PSA', 'PHM', 'PWR', 'QCOM', 'DGX', 'RL', 'RJF', 'RTX', 'O', 'REG', 'REGN', 'RF', 'RSG', 'RMD', 'RVTY', 'ROK', 'ROL', 'ROP', 'ROST', 'RCL', 'SPGI', 'CRM', 'SBAC', 'SLB', 'STX', 'SRE', 'NOW', 'SHW', 'SPG', 'SWKS', 'SJM', 'SW', 'SNA', 'SOLV', 'SO', 'LUV', 'SWK', 'SBUX', 'STT', 'STLD', 'STE', 'SYK', 'SMCI', 'SYF', 'SNPS', 'SYY', 'TMUS', 'TROW', 'TTWO', 'TPR', 'TRGP', 'TGT', 'TEL', 'TDY', 'TFX', 'TER', 'TSLA', 'TXN', 'TPL', 'TXT', 'TMO', 'TJX', 'TSCO', 'TT', 'TDG', 'TRV', 'TRMB', 'TFC', 'TYL', 'TSN', 'USB', 'UBER', 'UDR', 'ULTA', 'UNP', 'UAL', 'UPS', 'URI', 'UNH', 'UHS', 'VLO', 'VTR', 'VLTO', 'VRSN', 'VRSK', 'VZ', 'VRTX', 'VTRS', 'VICI', 'V', 'VST', 'VMC', 'WRB', 'GWW', 'WAB', 'WMT', 'DIS', 'WBD', 'WM', 'WAT', 'WEC', 'WFC', 'WELL', 'WST', 'WDC', 'WY', 'WMB', 'WTW', 'WDAY', 'WYNN', 'XEL', 'XYL', 'YUM', 'ZBRA', 'ZBH', 'ZTS']

MEDIUM_TICKERS = ['RGTI', 'QBTS', 'QUBT']

HIGH_TICKERS = [
    'AA', 'AAL', 'AAMI', 'AAOI', 'AAP', 'AAT', 'ABCL', 'ABEO', 'ABEV', 'ABG',
    'ABOS', 'ABR', 'ABSI', 'ACAD', 'ACDC', 'ACHC', 'ACHR', 'ACI', 'ACLS', 'ACLX',
    'ACMR', 'ACRS', 'AD', 'ADC', 'ADCT', 'ADEA', 'ADPT', 'ADV', 'AEG', 'AEHR',
    'AEO', 'AEVA', 'AG', 'AGD', 'AGIO', 'AGNC', 'AI', 'AIFU', 'AL', 'ALE',
    'ALEX', 'ALGT', 'ALHC', 'ALIT', 'ALLO', 'ALNY', 'ALT', 'ALTG', 'ALXO', 'AM',
    'AMBA', 'AMBQ', 'AMH', 'AMR', 'AMRZ', 'AMSC', 'ANAB', 'ANGI', 'AOD', 'AORT',
    'AOSL', 'APDN', 'APEI', 'APGE', 'APLD', 'APLS', 'APP', 'AR', 'ARAY', 'ARBK',
    'ARCB', 'ARCC', 'ARCT', 'ARDT', 'ARES', 'ARMN', 'AROC', 'ARQT', 'ARRY', 'ARX',
    'AS', 'ASA', 'ASIX', 'ASMB', 'ASPI', 'ASTS', 'ASX', 'ASYS', 'ATLC', 'ATUS',
    'AU', 'AUGO', 'AUR', 'AUTL', 'AVAL', 'AVBH', 'AVBP', 'AVD', 'AVO', 'AVXL',
    'AXL', 'AXR', 'AXS', 'AXTA', 'AXTI', 'B', 'BABA', 'BB', 'BBAI', 'BBD',
    'BBW', 'BCH', 'BCPC', 'BDN', 'BE', 'BEAM', 'BF-B', 'BFLY', 'BGS', 'BHFAP',
    'BINI', 'BIRD', 'BITF', 'BJ', 'BKH', 'BKKT', 'BKSY', 'BLD', 'BLNK', 'BMNR',
    'BNBX', 'BNGO', 'BOLD', 'BOW', 'BPYPP', 'BRK-B', 'BRW', 'BRX', 'BSBR', 'BSLK',
    'BSVN', 'BTBT', 'BTCM', 'BTDR', 'BTG', 'BULL', 'BURL', 'BVN', 'BW', 'BYM',
    'BYND', 'BYRN', 'CABA', 'CACC', 'CAI', 'CAKE', 'CAL', 'CALM', 'CAMT', 'CAPR',
    'CAR', 'CARE', 'CARS', 'CASY', 'CAVA', 'CBL', 'CBRL', 'CBT', 'CCEC', 'CCRD',
    'CCU', 'CDE', 'CECO', 'CEE', 'CELH', 'CENX', 'CEVA', 'CFFI', 'CFLT', 'CGEM',
    'CGON', 'CHCT', 'CHEK', 'CHRD', 'CHRS', 'CIEN', 'CIFR', 'CINT', 'CIO', 'CISS',
    'CLB', 'CLF', 'CLMT', 'CLNE', 'CLS', 'CLSK', 'CLW', 'CMA', 'CMC', 'CMPS',
    'CMTG', 'CMTL', 'CNF', 'CNH', 'CNK', 'CNQ', 'CNR', 'CNX', 'COHU', 'COIN',
    'COKE', 'CORZ', 'CPNG', 'CQP', 'CRAI', 'CRBU', 'CRC', 'CRCL', 'CRD-A', 'CRDF',
    'CRDO', 'CRH', 'CRK', 'CRMD', 'CRNC', 'CRNT', 'CRNX', 'CRS', 'CRSP', 'CRSR',
    'CRTO', 'CRWV', 'CSGS', 'CSR', 'CTLP', 'CTMX', 'CTOS', 'CTRN', 'CUBE', 'CVE',
    'CVLT', 'CVNA', 'CW', 'CWEN-A', 'CX', 'CXM', 'CYBR', 'CYD', 'CYH', 'DAO',
    'DASH', 'DAVE', 'DBI', 'DCO', 'DDD', 'DDL', 'DDOG', 'DFDV', 'DGICA', 'DGII',
    'DIN', 'DINO', 'DJT', 'DK', 'DKNG', 'DLTH', 'DLX', 'DNA', 'DNLI', 'DNN',
    'DNUT', 'DQ', 'DRD', 'DSX', 'DTM', 'DUOL', 'DWSN', 'DX', 'DXPE', 'DXYZ',
    'DYN', 'EAF', 'EAT', 'EB', 'EBS', 'EC', 'EDIT', 'EEFT', 'EGO', 'EGP',
    'EHAB', 'ELF', 'ELP', 'ELS', 'ENLT', 'ENOV', 'ENR', 'ENS', 'ENVA', 'ENVX',
    'EOLS', 'EOSE', 'EPD', 'EQNR', 'EQX', 'ERIC', 'ERII', 'ERO', 'ESI', 'ESRT',
    'ESTA', 'ET', 'ETR', 'ETSY', 'ETV', 'EVEX', 'EVGO', 'EVH', 'EVTL', 'EXE',
    'EXK', 'EXP', 'EXTR', 'EYE', 'EZPW', 'FCNCA', 'FDMT', 'FEAM', 'FERG', 'FFAI',
    'FGNX', 'FIG', 'FINV', 'FIP', 'FIX', 'FLEX', 'FLNC', 'FLUT', 'FLWS', 'FLXS',
    'FLY', 'FMCC', 'FNB', 'FNF', 'FNKO', 'FNMA', 'FNV', 'FOUR', 'FPH', 'FPI',
    'FRO', 'FRPT', 'FSM', 'FTI', 'FTK', 'FTRE', 'FUBO', 'FUN', 'FUNC', 'FUTU',
    'FVRR', 'FWONA', 'FWRD', 'FYBR', 'GBX', 'GCL', 'GCMG', 'GCO', 'GCTK', 'GCTS',
    'GEL', 'GERN', 'GETY', 'GEVO', 'GFI', 'GGB', 'GHC', 'GHM', 'GIII', 'GKOS',
    'GLDD', 'GLPI', 'GMAB', 'GME', 'GO', 'GOSS', 'GPRE', 'GRAB', 'GRAL', 'GRC',
    'GRI', 'GRP-UN', 'GRPN', 'GSAT', 'GSBD', 'GSIT', 'GTN', 'GTN-A', 'GTX', 'HAE',
    'HAIN', 'HALO', 'HBM', 'HBNC', 'HCTI', 'HCWB', 'HEI-A', 'HESM', 'HIMS', 'HL',
    'HLF', 'HLN', 'HMC', 'HMN', 'HMY', 'HNGE', 'HONE', 'HOOD', 'HOUS', 'HQY',
    'HRTG', 'HRTX', 'HRZN', 'HTFL', 'HTLD', 'HTZ', 'HUBG', 'HUMA', 'HUN', 'HUT',
    'HWBK', 'HWKN', 'HYPD', 'HZO', 'IAG', 'IAS', 'IBKR', 'IBRX', 'IBTA', 'IDA',
    'IDCC', 'IDT', 'IFRX', 'IGA', 'IGD', 'IGR', 'ILMN', 'IMAX', 'IMCR', 'IMMR',
    'IMNM', 'IMO', 'INDI', 'INDP', 'INFY', 'INGM', 'INMD', 'INOD', 'INSG', 'INSM',
    'INTR', 'INVX', 'IONQ', 'IOT', 'IOVA', 'IPGP', 'IPI', 'IQ', 'IRBT', 'IREN',
    'IRON', 'ISSC', 'ITIC', 'ITUB', 'IX', 'JACK', 'JAKK', 'JBGS', 'JBLU', 'JBS',
    'JD', 'JEF', 'JELD', 'JHS', 'JHX', 'JLL', 'JMIA', 'JOBY', 'KALU', 'KALV',
    'KB', 'KEP', 'KGC', 'KGS', 'KLXE', 'KMDA', 'KNDI', 'KNF', 'KNX', 'KOF',
    'KORE', 'KRO', 'KSPI', 'KSS', 'KULR', 'KURA', 'KYTX', 'LAC', 'LAMR', 'LAUR',
    'LAW', 'LAZR', 'LB', 'LBRDA', 'LBRDK', 'LBTYA', 'LC', 'LCFY', 'LCID', 'LDI',
    'LEGN', 'LENZ', 'LEU', 'LGO', 'LILA', 'LILAK', 'LINC', 'LINE', 'LITE', 'LKNCY',
    'LLYVA', 'LLYVK', 'LMND', 'LNG', 'LOVE', 'LQDA', 'LQDT', 'LSPD', 'LSTR', 'LTM',
    'LUMN', 'LUNR', 'LUXE', 'LX', 'LYFT', 'LYG', 'LZ', 'MANH', 'MARA', 'MAT',
    'MATV', 'MATX', 'MBLY', 'MBOT', 'MCHX', 'MDGL', 'MDU', 'MEC', 'MELI', 'MEOH',
    'MESO', 'MFA', 'MFG', 'MFH', 'MGNX', 'MGTX', 'MGX', 'MH', 'MIDD', 'MIN',
    'MIR', 'MIRM', 'MKL', 'MKSI', 'MNMD', 'MNRO', 'MOD', 'MP', 'MPLX', 'MPW',
    'MRSN', 'MRVI', 'MRVL', 'MRX', 'MSB', 'MSC', 'MSGS', 'MSTR', 'MT', 'MTDR',
    'MTSI', 'MTW', 'MUX', 'MVIS', 'MXCT', 'MYFW', 'MYGN', 'NBIS', 'NBR', 'NBTX',
    'NBY', 'NCNA', 'NCV', 'NCZ', 'NDLS', 'NEOG', 'NET', 'NEU', 'NFBK', 'NFE',
    'NFG', 'NFJ', 'NGD', 'NGS', 'NGVC', 'NIO', 'NJR', 'NLY', 'NMAX', 'NMCO',
    'NMG', 'NMR', 'NMZ', 'NNE', 'NNI', 'NNN', 'NOG', 'NOK', 'NOTE', 'NOV',
    'NPK', 'NPWR', 'NRDY', 'NRGV', 'NRIM', 'NRIX', 'NTES', 'NTLA', 'NTRA', 'NTST',
    'NU', 'NUKK', 'NUTX', 'NUVB', 'NVAX', 'NVMI', 'NVO', 'NVRI', 'NVTS', 'NWBI',
    'NWE', 'NXE', 'NXST', 'NXT', 'NXTC', 'NYT', 'OCGN', 'OCUL', 'OGE', 'OGN',
    'OGS', 'OHI', 'OII', 'OKLO', 'OLLI', 'OLN', 'OMER', 'OMI', 'ONC', 'ONDS',
    'ONIT', 'ONON', 'OPAD', 'OPEN', 'OPFI', 'OPY', 'ORA', 'ORLA', 'ORN', 'OS',
    'OSCR', 'OSK', 'OVV', 'OWL', 'OXM', 'PAA', 'PACB', 'PACK', 'PAR', 'PATH',
    'PAY', 'PBA', 'PBF', 'PBM', 'PBR', 'PBR-A', 'PBYI', 'PCB', 'PCOR', 'PCRX',
    'PCT', 'PD', 'PDT', 'PDYN', 'PEN', 'PENN', 'PFGC', 'PFIS', 'PFSI', 'PHAT',
    'PHVS', 'PHYS', 'PI', 'PII', 'PINS', 'PK', 'PKOH', 'PKST', 'PL', 'PLAY',
    'PLCE', 'PLOW', 'PLUG', 'PLYM', 'PMVP', 'PNFP', 'PONY', 'POR', 'POWL', 'PPC',
    'PR', 'PRAA', 'PRAX', 'PRCT', 'PRG', 'PRMB', 'PROK', 'PRSU', 'PRTA', 'PRTS',
    'PSFE', 'PSLV', 'PSTG', 'PSTL', 'PTLO', 'PTON', 'PX', 'PYXS', 'QCLS',
    'QS', 'QURE', 'RAMP', 'RARE', 'RBLX', 'RBOT', 'RBRK', 'RC', 'RCAT', 'RCEL',
    'RCUS', 'RDDT', 'RDNT', 'RDW', 'REAL', 'REPL', 'REXR', 'RGC', 'RGLD', 'RGNX',
    'RH', 'RHLD', 'RIG', 'RILY', 'RIOT', 'RIVN', 'RKLB', 'RKT', 'RM', 'RNA',
    'RNGR', 'ROKU', 'RPM', 'RPRX', 'RPTX', 'RRC', 'RS', 'RUM', 'RUN', 'RVLV',
    'RVMD', 'RWAY', 'RXO', 'RXRX', 'RXT', 'RY', 'RYAM', 'SAIA', 'SAIL', 'SANA',
    'SANM', 'SAR', 'SATS', 'SBET', 'SBH', 'SBSW', 'SCCO', 'SCL', 'SCS', 'SD',
    'SEDG', 'SEI', 'SEM', 'SERV', 'SES', 'SFBS', 'SFD', 'SFM', 'SG', 'SGBX',
    'SGU', 'SHBI', 'SHG', 'SHOP', 'SIDU', 'SIG', 'SILA', 'SIRI', 'SKE', 'SLDB',
    'SLNH', 'SLS', 'SMA', 'SMBK', 'SMG', 'SMLR', 'SMMT', 'SMR', 'SMRT', 'SMWB',
    'SNAP', 'SNBR', 'SNDK', 'SNDR', 'SNDX', 'SNOW', 'SNV', 'SOC', 'SOFI', 'SONN',
    'SOUN', 'SPCE', 'SPE', 'SPHR', 'SPOT', 'SPRO', 'SPRU', 'SPRY', 'SPXX', 'SR',
    'SRDX', 'SRFM', 'SRPT', 'SRRK', 'SSD', 'SSTK', 'ST', 'STC', 'STGW', 'STLA',
    'STOK', 'STRL', 'STTK', 'STVN', 'SUI', 'SUN', 'SVC', 'SVCO', 'SWX', 'SXT',
    'SYM', 'SYNA', 'SYRE', 'SZRRF', 'TAC', 'TALO', 'TAOX', 'TARS', 'TBHC', 'TCBX',
    'TD', 'TDOC', 'TDS', 'TDW', 'TE', 'TEAD', 'TECK', 'TEI', 'TEM', 'TEO',
    'TEVA', 'TGE', 'TGL', 'TGS', 'TGTX', 'THC', 'THG', 'TIC', 'TIGO', 'TIGR',
    'TILE', 'TIMB', 'TKO', 'TLK', 'TLN', 'TLNE', 'TLRY', 'TLX', 'TMC', 'TMDX',
    'TMHC', 'TNGX', 'TNXP', 'TRIN', 'TRIP', 'TRP', 'TRU', 'TRUP', 'TS', 'TSAT',
    'TSHA', 'TSM', 'TSSI', 'TTD', 'TTGT', 'TTI', 'TV', 'TWLO', 'TWST', 'TXNM',
    'UAN', 'UCTT', 'UEC', 'UFPI', 'UGI', 'UI', 'ULH', 'UMC', 'UNM', 'UOKA',
    'UPBD', 'UPST', 'UPWK', 'UPXI', 'URBN', 'URGN', 'USAR', 'USFD', 'USLM',
    'USPH', 'UTHR', 'UTI', 'UTZ', 'UUUU', 'UWMC', 'VALE', 'VEEV', 'VEL', 'VERA',
    'VFC', 'VG', 'VICR', 'VIK', 'VIR', 'VIRT', 'VIST', 'VITL', 'VKTX', 'VNO',
    'VNOM', 'VOR', 'VOYG', 'VRNS', 'VRNT', 'VRT', 'VRTS', 'VSAT', 'VSCO', 'VSTM',
    'VTEX', 'VTLE', 'VTOL', 'VTS', 'VUZI', 'VYGR', 'W', 'WAL', 'WBX', 'WCC',
    'WCN', 'WDH', 'WEA', 'WES', 'WF', 'WHR', 'WIT', 'WIW', 'WKHS', 'WLDS',
    'WLK', 'WMG', 'WOLF', 'WPC', 'WPP', 'WPRT', 'WRD', 'WSBF', 'WSC', 'WSM',
    'WSR', 'WT', 'WTBA', 'WTI', 'WTRG', 'WULF', 'XHR', 'XNET', 'XPO', 'XPOF',
    'XRX', 'XYF', 'XYZ', 'YEXT', 'YOU', 'ZBIO', 'ZEPP', 'ZETA', 'ZG', 'ZIM',
    'ZION', 'ZNB', 'ZS', 'ZYXI'
]

# Alpaca API keys for paper_medium account
ALPACA_API_KEY_MEDIUM = os.getenv("ALPACA_API_KEY_MEDIUM", "")
ALPACA_SECRET_KEY_MEDIUM = os.getenv("ALPACA_SECRET_KEY_MEDIUM", "")

# Alpaca API keys for primary account
ALPACA_API_KEY_LOW = os.getenv("ALPACA_API_KEY_LOW", "")
ALPACA_SECRET_KEY_LOW = os.getenv("ALPACA_SECRET_KEY_LOW", "")

# Alpaca API keys for live account
ALPACA_API_KEY_LIVE = os.getenv("ALPACA_API_KEY_LIVE", "")
ALPACA_SECRET_KEY_LIVE = os.getenv("ALPACA_SECRET_KEY_LIVE", "")

# Alpaca API keys for paper_high account
ALPACA_API_KEY_HIGH = os.getenv("ALPACA_API_KEY_HIGH", "")
ALPACA_SECRET_KEY_HIGH = os.getenv("ALPACA_SECRET_KEY_HIGH", "")
