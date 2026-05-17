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
EMAIL_FROM = os.environ.get('EMAIL_FROM', '') or SMTP_USER

# WxPusher 微信推送 (免费)
WXPUSHER_TOKEN = os.environ.get('WXPUSHER_TOKEN', '')
WXPUSHER_UID = os.environ.get('WXPUSHER_UID', '')

# 读取 settings.json (开关和发送时间)
SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'settings.json')
EMAIL_ENABLED = True
EMAIL_TIME = '12:45'
try:
    with open(SETTINGS_PATH) as f:
        s = json.load(f)
        EMAIL_ENABLED = s.get('email_enabled', True)
        EMAIL_TIME = s.get('email_time', '12:45')
except:
    pass

# 如果不是设定的时间, 跳过邮件和微信 (允许15分钟误差)
now = datetime.now()
target_h, target_m = map(int, EMAIL_TIME.split(':'))
time_ok = abs(now.hour * 60 + now.minute - (target_h * 60 + target_m)) <= 15
SHOULD_NOTIFY = EMAIL_ENABLED and time_ok

DATA_FILE = f'{COIN.lower()}_data.json'

def fetch_prices():
    days = min(max(MA_LONG + 10, 250), 365)
    errs = []
    
    okx_symbol = SYMBOL.replace('USDT', '-USDT')
    
    srcs = [
        (f'OKX', f'https://www.okx.com/api/v5/market/history-candles?instId={okx_symbol}&bar=1Dutc&limit={days}',
         lambda d: [float(k[4]) for k in reversed(d['data'])]),
        (f'Bybit', f'https://api.bybit.com/v5/market/kline?category=spot&symbol={SYMBOL}&interval=D&limit={days}',
         lambda d: [float(k[4]) for k in d['result']['list']]),
        (f'Binance', f'https://api.binance.com/api/v3/klines?symbol={SYMBOL}&interval=1d&limit={days}',
         lambda d: [float(k[4]) for k in d]),
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

def push_wxpusher(eth_data, btc_data):
    """推送到微信 (WxPusher, 免费无认证)"""
    token = os.environ.get('WXPUSHER_TOKEN', '')
    uid = os.environ.get('WXPUSHER_UID', '')
    if not token or not uid:
        return
    
    e = eth_data['latest']
    b = btc_data['latest']
    
    now = datetime.now().strftime('%m-%d')
    content = f'''ETH: {e['indicator']} {e['zone_name']} ${e['price']:,.0f} {e['zone_action']}
BTC: {b['indicator']} {b['zone_name']} ${b['price']:,.0f} {b['zone_action']}
数据: OKX/Bybit · {now}'''
    
    data = json.dumps({
        'appToken': token,
        'content': content,
        'summary': f'ETH {e["indicator"]} · BTC {b["indicator"]}',
        'contentType': 2,
        'uids': [uid],
    }).encode()
    
    try:
        req = urllib.request.Request('https://wxpusher.zjiecode.com/api/send/message',
            data=data, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = json.loads(r.read())
            if resp.get('code') == 1000:
                print('✅ 微信已推送')
            else:
                print(f'❌ 微信推送失败: {resp}')
    except Exception as e:
        print(f'❌ 微信推送失败: {e}')

def load_coin_data(coin):
    """读取另一个币的数据文件"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', f'{coin.lower()}_data.json')
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None

def send_simple_email(eth_data, btc_data):
    """定投日报邮件"""
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASS, EMAIL_TO]):
        print('邮箱没配, 跳过邮件')
        return False
    
    def trend(data):
        h = data.get('history', [])
        if len(h) >= 2:
            return '↑' if h[-1]['indicator'] > h[-2]['indicator'] else '↓'
        return '→'
    
    e, b = eth_data['latest'], btc_data['latest']
    et, bt = trend(eth_data), trend(btc_data)
    today = datetime.now().strftime('%Y-%m-%d %A')
    subj = f'ETH {e["indicator"]}{et}{e["zone_name"]} · BTC {b["indicator"]}{bt}{b["zone_name"]} · {datetime.now().strftime("%m-%d")}'
    
    body = f'''<html><body style="font-family:Microsoft YaHei,Arial;padding:20px;background:#f5f5f5;">
<div style="max-width:500px;margin:0 auto;background:white;border-radius:10px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.1);">
<div style="background:#1a1a2e;color:white;padding:15px;text-align:center;">
    <h2 style="margin:0;font-size:18px;">📊 定投日报</h2>
    <p style="margin:3px 0 0;opacity:0.6;font-size:12px;">{today}</p>
</div>
<div style="padding:15px;">
    <table style="width:100%;border-collapse:collapse;">
    <tr style="background:#f8f9fa;">
        <td style="padding:12px;text-align:center;border-radius:8px 0 0 8px;">
            <div style="font-size:11px;color:#888;">ETH</div>
            <div style="font-size:24px;font-weight:bold;color:#3498db;">{e["indicator"]}{et}</div>
            <div style="font-size:12px;color:{'#27ae60' if e['zone_name'] in ['轻投区','定投区','重仓区','梭哈区'] else '#e74c3c'};">{e["zone_name"]}</div>
            <div style="font-size:11px;color:#666;">${e["price"]:,.0f}</div>
        </td>
        <td style="padding:12px;text-align:center;border-radius:0 8px 8px 0;">
            <div style="font-size:11px;color:#888;">BTC</div>
            <div style="font-size:24px;font-weight:bold;color:#27ae60;">{b["indicator"]}{bt}</div>
            <div style="font-size:12px;color:{'#27ae60' if b['zone_name'] in ['定投区','抄底区'] else '#f39c12'};">{b["zone_name"]}</div>
            <div style="font-size:11px;color:#666;">${b["price"]:,.0f}</div>
        </td>
    </tr>
    </table>
    <div style="display:flex;gap:8px;margin-top:10px;">
        <div style="flex:1;padding:8px;background:#f0f3ff;border-radius:6px;text-align:center;">
            <div style="font-size:10px;color:#888;">ETH 操作</div>
            <div style="font-size:12px;font-weight:600;">{e["zone_action"]}</div>
        </div>
        <div style="flex:1;padding:8px;background:#f0f3ff;border-radius:6px;text-align:center;">
            <div style="font-size:10px;color:#888;">BTC 操作</div>
            <div style="font-size:12px;font-weight:600;">{b["zone_action"]}</div>
        </div>
    </div>
    <div style="text-align:center;font-size:10px;color:#bbb;margin-top:10px;">
        数据来源: OKX/Bybit · {datetime.now().strftime("%H:%M")}更新
    </div>
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
        print(f'✅ 邮件已发送: {subj}')
        return True
    except Exception as e:
        print(f'❌ 邮件发送失败: {e}')
        return False

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
    
    # ETH只存数据, BTC存完再发合并邮件
    if COIN == 'BTC':
        eth = load_coin_data('ETH')
        btc = load_coin_data('BTC')
        if eth and btc:
            if SHOULD_NOTIFY:
                send_simple_email(eth, btc)
                push_wxpusher(eth, btc)
            else:
                t = EMAIL_TIME
                print(f'通知已关闭或不在发送时间(设定{t}), 跳过邮件和微信')
        else:
            print('ETH或BTC数据不全, 跳过')

if __name__ == '__main__':
    main()
