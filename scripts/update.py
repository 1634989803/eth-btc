#!/usr/bin/env python3
"""
ETH/BTC 阶梯定投指标 - 数据采集脚本
由 GitHub Actions 每天自动运行
"""

import json
import os
import urllib.request
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ═══════ 配置（通过环境变量传入） ═══════
COIN = os.environ.get('COIN', 'ETH')          # ETH 或 BTC
SYMBOL = COIN + 'USDT'

def get_env_int(key, default):
    v = os.environ.get(key, '')
    return int(v) if v.strip() else default

def get_env_float(key, default):
    v = os.environ.get(key, '')
    return float(v) if v.strip() else default

MA_SHORT = get_env_int('MA_SHORT', 120)
MA_LONG = get_env_int('MA_LONG', 250)
THRESH_ALLIN = get_env_float('THRESH_ALLIN', 0.35)
THRESH_HEAVY = get_env_float('THRESH_HEAVY', 0.45)
THRESH_DCA = get_env_float('THRESH_DCA', 0.65)
THRESH_SELL = get_env_float('THRESH_SELL', 1.60)

# 邮箱配置
SMTP_HOST = os.environ.get('SMTP_HOST', '')
SMTP_PORT = get_env_int('SMTP_PORT', 587)
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASS = os.environ.get('SMTP_PASS', '')
EMAIL_TO = os.environ.get('EMAIL_TO', '')
EMAIL_FROM = os.environ.get('EMAIL_FROM', SMTP_USER)

DATA_FILE = 'data.json'
DATA_DIR = os.path.dirname(os.path.abspath(__file__)) + '/..'


def fetch_klines(symbol, interval='1d', limit=260):
    """从币安获取K线数据"""
    url = f'https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}'
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    prices = [float(k[4]) for k in data]  # 收盘价
    return prices


def calc_sma(prices, period):
    """计算 SMA"""
    if len(prices) < period:
        return 0
    return sum(prices[-period:]) / period


def calc_ema(prices, period):
    """计算 EMA"""
    if len(prices) < period:
        return 0
    multiplier = 2 / (period + 1)
    ema = calc_sma(prices, period)
    start = len(prices) - period
    for i in range(start, len(prices)):
        ema = (prices[i] - ema) * multiplier + ema
    return ema


def get_zone(ratio):
    """判断阶梯"""
    zones = [
        (0, THRESH_ALLIN, '梭哈区', '💜', '5倍定投，分批重仓买入', '#9b59b6'),
        (THRESH_ALLIN, THRESH_HEAVY, '重仓区', '💚', '3倍定投，大幅加仓', '#27ae60'),
        (THRESH_HEAVY, THRESH_DCA, '定投区', '💛', '1倍定投，正常建仓', '#f39c12'),
        (THRESH_DCA, THRESH_SELL, '持有区', '⬜', '持仓不动，暂停定投', '#7f8c8d'),
        (THRESH_SELL, float('inf'), '止盈区', '🔴', '分批卖出，锁定利润', '#e74c3c'),
    ]
    for mn, mx, name, icon, action, color in zones:
        if mn <= ratio < mx:
            return {'name': name, 'icon': icon, 'action': action, 'color': color}
    return zones[-1]


def send_email(coin, price, sma120, ema250, ratio, zone):
    """发送邮件"""
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASS, EMAIL_TO]):
        print('⚠️ 邮箱未配置，跳过邮件发送')
        return

    today = datetime.now().strftime('%Y-%m-%d %A')
    subject = f'{coin} 定投日报 - 偏离度 {ratio} ({zone["name"]})'

    html = f'''<html><body style="font-family:'Microsoft YaHei',Arial,sans-serif;padding:20px;background:#f5f5f5;">
<div style="max-width:600px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
<div style="background:#1a1a2e;color:white;padding:20px;text-align:center;">
    <h2 style="margin:0;">{coin} 阶梯定投日报</h2>
    <p style="margin:5px 0 0;opacity:0.8;">{today}</p>
</div>
<div style="padding:20px;">
    <div style="text-align:center;padding:20px;margin:15px 0;border-radius:8px;background:{zone["color"]}15;">
        <div style="font-size:48px;font-weight:bold;color:{zone["color"]};">{ratio}</div>
        <div style="font-size:20px;margin-top:8px;color:{zone["color"]};">{zone["icon"]} {zone["name"]}</div>
        <div style="font-size:16px;margin-top:8px;color:#666;">→ {zone["action"]}</div>
    </div>
    <table style="width:100%;border-collapse:collapse;margin:15px 0;">
        <tr><td style="padding:10px;border-bottom:1px solid #eee;color:#666;">当前价格</td>
            <td style="padding:10px;border-bottom:1px solid #eee;font-weight:bold;text-align:right;">${price:,.2f}</td></tr>
        <tr><td style="padding:10px;border-bottom:1px solid #eee;color:#666;">SMA {MA_SHORT}</td>
            <td style="padding:10px;border-bottom:1px solid #eee;text-align:right;">${sma120:,.2f}</td></tr>
        <tr><td style="padding:10px;border-bottom:1px solid #eee;color:#666;">EMA {MA_LONG}</td>
            <td style="padding:10px;border-bottom:1px solid #eee;text-align:right;">${ema250:,.2f}</td></tr>
        <tr><td style="padding:10px;color:#666;">偏离度指数</td>
            <td style="padding:10px;font-weight:bold;text-align:right;color:{zone["color"]};">{ratio}</td></tr>
    </table>
    <div style="background:#f8f9fa;padding:12px;border-radius:8px;font-size:12px;color:#888;margin-top:15px;">
        <strong>📊 区间说明</strong><br>
        💜 梭哈 (&lt; {THRESH_ALLIN}) → 5倍定投<br>
        💚 重仓 ({THRESH_ALLIN}~{THRESH_HEAVY}) → 3倍定投<br>
        💛 定投 ({THRESH_HEAVY}~{THRESH_DCA}) → 1倍定投<br>
        ⬜ 持有 ({THRESH_DCA}~{THRESH_SELL}) → 暂停<br>
        🔴 止盈 (&gt; {THRESH_SELL}) → 分批卖出<br>
        数据: Binance | 由 GitHub Actions 自动生成
    </div>
</div></div></body></html>'''

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = EMAIL_FROM
    msg['To'] = EMAIL_TO
    msg.attach(MIMEText(html, 'html', 'utf-8'))

    try:
        if SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
            server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())
        server.quit()
        print(f'✅ 邮件已发送到 {EMAIL_TO}')
    except Exception as e:
        print(f'❌ 邮件发送失败: {e}')


def main():
    print(f'=== {COIN} 阶梯定投指标更新 ===')
    print(f'时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'币种: {COIN}')
    
    # 获取行情
    prices = fetch_klines(SYMBOL, '1d', MA_LONG + 10)
    if not prices:
        print('❌ 获取行情失败')
        return

    current_price = prices[-1]
    sma120 = calc_sma(prices, MA_SHORT)
    ema250 = calc_ema(prices, MA_LONG)
    ratio = round((current_price / sma120) * (current_price / ema250), 4)
    zone = get_zone(ratio)

    print(f'当前价格: ${current_price:,.2f}')
    print(f'SMA{MA_SHORT}: ${sma120:,.2f}')
    print(f'EMA{MA_LONG}: ${ema250:,.2f}')
    print(f'偏离度: {ratio}')
    print(f'区域: {zone["icon"]} {zone["name"]} → {zone["action"]}')

    # 读取已有数据
    data_path = os.path.join(DATA_DIR, DATA_FILE)
    existing = {'history': [], 'config': {}}
    if os.path.exists(data_path):
        with open(data_path, 'r') as f:
            existing = json.load(f)

    today_str = datetime.now().strftime('%Y-%m-%d')
    new_entry = {
        'date': today_str,
        'price': current_price,
        'sma120': round(sma120, 2),
        'ema250': round(ema250, 2),
        'ratio': ratio,
        'zone': zone['name'],
    }

    # 去重：如果今天已有记录则覆盖
    history = existing.get('history', [])
    history = [h for h in history if h['date'] != today_str]
    history.append(new_entry)
    # 保留最近 90 天
    history = sorted(history, key=lambda x: x['date'])[-90:]

    config = {
        'coin': COIN,
        'thresh_allin': THRESH_ALLIN,
        'thresh_heavy': THRESH_HEAVY,
        'thresh_dca': THRESH_DCA,
        'thresh_sell': THRESH_SELL,
        'ma_short': MA_SHORT,
        'ma_long': MA_LONG,
        'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }

    output = {
        'latest': new_entry,
        'history': history,
        'config': config,
        'zone': zone,
    }

    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'✅ 数据已写入 {DATA_FILE}')

    # 发邮件
    send_email(COIN, current_price, sma120, ema250, ratio, zone)
    print('=== 完成 ===')


if __name__ == '__main__':
    main()
