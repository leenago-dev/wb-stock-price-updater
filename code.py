import FinanceDataReader as fdr
import yfinance as yf
import pandas as pd

krx = fdr.StockListing("KRX")
snp = fdr.StockListing("S&P500")
nsd = fdr.StockListing("NASDAQ")
etf = fdr.StockListing("ETF/KR")
nyse = fdr.StockListing("NYSE")
amex = fdr.StockListing("AMEX")
total = pd.concat((amex, nyse, snp, nsd, krx, etf))[
    ["Symbol", "Name"]
].drop_duplicates()

###

fdr.DataReader("^NYICDX")  # 달러인덱스
fdr.DataReader("USD/KRW")  # 달러/원 환율
fdr.DataReader("BTC/KRW")  # 비트코인/원 환율
fdr.DataReader("BTC/USD")  # 비트코인/달러 환율

### 미국 ETF 데이터 별도 조회

# 1. 필요한 도구들을 불러옵니다.
import yfinance as yf
import pandas as pd

# 2. 분석하고 싶은 ETF들의 '티커(Ticker)' 리스트를 정의합니다.
# 실제 업무에서는 이 리스트를 엑셀(CSV) 파일에서 불러옵니다.
# 예: etf_list = pd.read_csv('us_etf_list.csv')['Symbol'].tolist()
etf_tickers = [
    "SPY",
    "QQQ",
    "VOO",
    "SGOV",
    "SHY",
    "BND",
]  # SPY(S&P500), QQQ(나스닥), VTI(전체시장), JEPI(배당)

print(f"총 {len(etf_tickers)}개의 ETF 데이터를 요청합니다...")

# 3. 리스트에 있는 종목들의 정보를 가져옵니다.
data = []

for ticker in etf_tickers:
    # yfinance라는 '사서'에게 티커를 주며 정보를 요청합니다.
    etf = yf.Ticker(ticker)

    # 필요한 정보만 쏙쏙 뽑아서 정리합니다 (이게 바로 ETL의 Transform!)
    info = {"종목코드": ticker, "이름": etf.info.get("shortName")}
    data.append(info)

# 4. 보기 좋게 표(DataFrame)로 만듭니다.
df = pd.DataFrame(data)

# 결과 출력
print(df)


pd.concat((df, total))
