import json, os, urllib.request, smtplib, math
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

def env_int(key, default):
    v = os.environ.get(key, '').strip()
    return int(v) if v else default

def env_float(key, default):
    v = os.environ.get(key, '').strip()
    return float(v) if v else default

COIN = os.environ.get('COIN', 'ETH')
SYMBOL = COIN + 'USDT'

MA_SHORT = env_int('MA_SHORT', 120)
MA_LONG = env_int('MA_LONG', 250)
T_ALLIN = env_float('THRESH_ALLIN', 0.35)
T_HEAVY = env_float('THRESH_HEAVY', 0.45)
T_DCA = env_float('THRESH_DCA', 0.65)
T_SELL = env_float('THRESH_SELL', 1.60)

# 邮箱
SMTP_HOST = os.environ.get('SMTP_HOST', '')
SMTP_PORT = env_int('SMTP_PORT', 587)
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASS = os.environ.get('SMTP_PASS', '')
EMAIL_TO = os.environ.get('EMAIL_TO', '')
EMAIL_FROM = os.environ.get('EMAIL_FROM', SMTP_USER)

DATA_FILE = f'{COIN.lower()}_data.json'

def fetch_prices():
    coin_id = 'ethereum' if 'ETH' in SYMBOL else 'bitcoin'
    days = max(MA_LONG + 10, 400)
    errs = []
    
    srcs = [
        (f'CoinGecko', f'https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days={days}',
         lambda d: [p[1] for p in d['prices']]),
        (f'Binance', f'https://api.binance.com/api/v3/klines?symbol={SYMBOL}&interval=1d&limit={days}',
         lambda d: [float(k[4]) for k in d]),
        (f'Bybit', f'https://api.bybit.com/v5/market/kline?category=spot&symbol={SYMBOL}&interval=D&limit={days}',
         lambda d: [float(k[4]) for k in d['result']['list']]),
        (f'OKX', f'https://www.okx.com/api/v5/market/history-candles?instId={SYMBOL}&bar=1Dutc&limit={days}',
         lambda d: [float(k[4]) for k in d['data']]),
    ]
    
    for name, url, parser in srcs:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())
            prices = parser(data)
            if prices and len(prices) > 200:
                print(f'数据源: {name} ({len(prices)} 条)')
                return prices
        except Exception as e:
            errs.append(f'{name}: {e}')
    
    raise Exception(f'所有数据源都挂了: {"; ".join(errs)}')

def calc_sma(prices, n):
    return sum(prices[-n:]) / n if len(prices) >= n else 0

def calc_ema(prices, n):
    if len(prices) < n:
        return 0
    k = 2 / (n + 1)
    ema = calc_sma(prices, n)
    for i in range(len(prices) - n, len(prices)):
        ema = (prices[i] - ema) * k + ema
    return ema

def calc_exp_regression(prices):
    """指数回归: ln(price) = a * x + b, 算出估值线"""
    n = len(prices)
    if n < 2:
        return 0
    x_vals = list(range(n))
    y_vals = [math.log(p) for p in prices]
    avg_x = sum(x_vals) / n
    avg_y = sum(y_vals) / n
    num = sum((x - avg_x) * (y - avg_y) for x, y in zip(x_vals, y_vals))
    den = sum((x - avg_x) ** 2 for x in x_vals)
    a = num / den if den else 0
    b = avg_y - a * avg_x
    return math.exp(a * (n - 1) + b)

def eth_zones(ratio):
    """ETH阶梯定投：比值越低越低估"""
    if ratio < T_ALLIN:
        return ('梭哈区', '💜', '5倍定投, 重仓买入', '#9b59b6')
    if ratio < T_HEAVY:
        return ('重仓区', '💚', '3倍定投, 大幅加仓', '#27ae60')
    if ratio < T_DCA:
        return ('定投区', '💛', '1倍定投, 正常节奏', '#f39c12')
    if ratio < T_SELL:
        return ('轻投区', '🔵', '0.5倍定投, 小额分批', '#3498db')
    return ('止盈区', '🔴', '分批卖出', '#e74c3c')

def btc_ahr999(prices):
    """BTC AHR999 指数"""
    price = prices[-1]
    sma200 = calc_sma(prices, 200)
    exp_val = calc_exp_regression(prices)
    if sma200 <= 0 or exp_val <= 0:
        return 0
    ratio = (price / sma200) * (price / exp_val)
    return round(ratio, 4)

def btc_zones(ratio):
    """BTC AHR999 经典区间"""
    if ratio < 0.45:
        return ('抄底区', '🟣', '可以抄底', '#9b59b6')
    if ratio < 1.2:
        return ('定投区', '🟢', '正常定投', '#27ae60')
    return ('持有区', '🟡', '暂停买入', '#f39c12')

def send_email(coin, price, indicator, zone_info):
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASS, EMAIL_TO]):
        print('邮箱没配, 跳过邮件')
        return
    
    name, icon, action, color = zone_info
    today = datetime.now().strftime('%Y-%m-%d %A')
    subj = f'{coin} 定投日报 - {indicator} ({name})'
    
    body = f'''<html><body style="font-family:Microsoft YaHei,Arial;padding:20px;background:#f5f5f5;">
<div style="max-width:600px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;">
<div style="background:#1a1a2e;color:white;padding:20px;text-align:center;">
    <h2>{coin} 定投日报</h2>
    <p>{today}</p>
</div>
<div style="padding:20px;">
    <div style="text-align:center;padding:20px;background:{color}15;">
        <div style="font-size:48px;font-weight:bold;color:{color};">{indicator}</div>
        <div style="font-size:20px;color:{color};">{icon} {name}</div>
        <div style="font-size:16px;color:#666;">→ {action}</div>
    </div>
    <p style="text-align:center;color:#999;">当前价格: ${price:,.2f}</p>
</div></div></body></html>'''
    
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subj
    msg['From'] = EMAIL_FROM
    msg['To'] = EMAIL_TO
    msg.attach(MIMEText(body, 'html', 'utf-8'))
    
    try:
        s = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) if SMTP_PORT == 465 else smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
        if SMTP_PORT != 465:
            s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())
        s.quit()
        print(f'邮件已发到 {EMAIL_TO}')
    except Exception as e:
        print(f'邮件发送失败: {e}')

def main():
    print(f'--- {COIN} {datetime.now().strftime("%Y-%m-%d %H:%M")} ---')
    
    prices = fetch_prices()
    price = prices[-1]
    print(f'价格: ${price:,.2f}')
    
    if COIN == 'BTC':
        # AHR999 指标
        sma200 = calc_sma(prices, 200)
        exp_val = calc_exp_regression(prices)
        indicator = (price / sma200) * (price / exp_val)
        indicator = round(indicator, 4)
        zone = btc_zones(indicator)
        print(f'SMA200: ${sma200:,.2f}')
        print(f'指数估值: ${exp_val:,.2f}')
        print(f'AHR999: {indicator}')
        print(f'区域: {zone[0]}')
    else:
        # ETH 阶梯定投
        sma = calc_sma(prices, MA_SHORT)
        ema = calc_ema(prices, MA_LONG)
        indicator = (price / sma) * (price / ema)
        indicator = round(indicator, 4)
        zone = eth_zones(indicator)
        print(f'SMA{MA_SHORT}: ${sma:,.2f}')
        print(f'EMA{MA_LONG}: ${ema:,.2f}')
        print(f'偏离度: {indicator}')
        print(f'区域: {zone[0]}')
    
    # 写 data.json
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', DATA_FILE)
    existing = {'history': [], 'config': {}}
    if os.path.exists(path):
        with open(path) as f:
            existing = json.load(f)
    
    today = datetime.now().strftime('%Y-%m-%d')
    entry = {
        'date': today, 'price': price, 'indicator': indicator,
        'zone_name': zone[0], 'zone_icon': zone[1], 'zone_action': zone[2], 'zone_color': zone[3],
    }
    
    # 去重
    existing['history'] = [h for h in existing.get('history', []) if h['date'] != today]
    existing['history'].append(entry)
    existing['history'] = sorted(existing['history'], key=lambda x: x['date'])[-90:]
    existing['latest'] = entry
    existing['config'] = {
        'coin': COIN, 'last_update': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'thresh_allin': T_ALLIN, 'thresh_heavy': T_HEAVY, 'thresh_dca': T_DCA, 'thresh_sell': T_SELL,
    }
    existing['zone'] = {'name': zone[0], 'icon': zone[1], 'action': zone[2], 'color': zone[3]}
    
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print('data.json 已更新')
    
    send_email(COIN, price, indicator, zone)

if __name__ == '__main__':
    main()
