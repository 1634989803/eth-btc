#!/usr/bin/env python3
"""获取美股ETF基准数据 (在GitHub Actions美国服务器上跑)"""
import json, os, sys
from datetime import datetime

# 用 yfinance 或者手动请求
try:
    import yfinance as yf
    HAS_YF = True
except:
    HAS_YF = False

BENCHES = {
    'qqq': {'name': '纳斯达克100(QQQ)', 'symbol': 'QQQ'},
    'spy': {'name': '标普500(SPY)', 'symbol': 'SPY'},
    'qqqi': {'name': 'QQQI', 'symbol': 'QQQI'},
}

OUT = os.path.join(os.path.dirname(__file__), '..', 'benchmarks')

def fetch_yfinance(symbol):
    """用 yfinance 获取历史数据"""
    t = yf.Ticker(symbol)
    hist = t.history(period='5y')
    data = []
    for idx, row in hist.iterrows():
        data.append({
            'date': idx.strftime('%Y-%m-%d'),
            'price': round(float(row['Close']), 2),
        })
    return data

def fetch_fallback(symbol):
    """不用yfinance的备选方案"""
    import urllib.request
    # 用 Yahoo Finance CSV endpoint
    import time
    ts = int(time.time())
    url = f'https://query1.finance.yahoo.com/v7/finance/download/{symbol}?period1=1577836800&period2={ts}&interval=1d&events=history'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as r:
        lines = r.read().decode().strip().split('\n')
    data = []
    for line in lines[1:]:  # skip header
        parts = line.split(',')
        if len(parts) >= 5 and parts[4] and parts[4] != 'null':
            data.append({'date': parts[0], 'price': round(float(parts[4]), 2)})
    return data

def main():
    if not os.path.exists(OUT):
        os.makedirs(OUT)
    
    for key, cfg in BENCHES.items():
        path = os.path.join(OUT, f'{key}.json')
        print(f'{cfg["name"]}...', end=' ')
        
        try:
            if HAS_YF:
                data = fetch_yfinance(cfg['symbol'])
            else:
                data = fetch_fallback(cfg['symbol'])
            
            if len(data) > 100:
                out = {
                    'name': cfg['name'],
                    'symbol': key,
                    'updated': datetime.now().isoformat(),
                    'data': data,
                }
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(out, f, ensure_ascii=False)
                print(f'✅ {len(data)} 条')
            else:
                print(f'❌ 数据不足 ({len(data)})')
        except Exception as e:
            print(f'❌ {e}')

if __name__ == '__main__':
    main()
