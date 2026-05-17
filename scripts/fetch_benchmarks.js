// 获取基准数据: QQQ, SPY, CSI300, CSI500
// 运行: node scripts/fetch_benchmarks.js
// 输出到 benchmarks/ 目录

const https = require('https');
const fs = require('fs');
const path = require('path');

const BENCHES = {
    'qqq': { yahoo: 'QQQ', name: '纳斯达克100', div: 0.0065 },
    'spy': { yahoo: 'SPY', name: '标普500', div: 0.013 },
    'qqqi': { yahoo: 'QQQI', name: 'QQQI', div: 0.12 },
    'csi300': { sina: 'sh000300', name: '沪深300', div: 0.02 },
    'csi500': { sina: 'sh000905', name: '中证500', div: 0.015 },
};

const OUT_DIR = path.join(__dirname, '..', 'benchmarks');

function fetch(url) {
    return new Promise((resolve, reject) => {
        const opts = { headers: { 'User-Agent': 'Mozilla/5.0' }, timeout: 15000 };
        https.get(url, opts, res => {
            let data = '';
            res.on('data', c => data += c);
            res.on('end', () => resolve(data));
        }).on('error', reject);
    });
}

async function fetchYahoo(symbol) {
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${symbol}?range=5y&interval=1d`;
    const raw = await fetch(url);
    const json = JSON.parse(raw);
    const result = json.chart?.result?.[0];
    if (!result) throw new Error('yahoo empty');
    
    const timestamps = result.timestamp;
    const quotes = result.indicators.quote?.[0];
    if (!quotes) throw new Error('no quotes');
    
    const data = [];
    for (let i = 0; i < timestamps.length; i++) {
        if (quotes.close?.[i]) {
            data.push({
                date: new Date(timestamps[i] * 1000).toISOString().slice(0, 10),
                price: quotes.close[i],
            });
        }
    }
    return data;
}

async function fetchSina(code) {
    const url = `https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=${code},day,,,800,qfq`;
    const raw = await fetch(url);
    const json = JSON.parse(raw);
    const key = code.startsWith('sh') ? 'sh' : 'sz';
    const days = json?.data?.[code]?.day || json?.data?.[code]?.qfqday || [];
    
    return days.map(d => ({
        date: d[0].replace(/-/g, '-'),
        price: parseFloat(d[2]), // 收盘价
    })).filter(d => d.price > 0);
}

async function main() {
    if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });
    
    for (const [key, cfg] of Object.entries(BENCHES)) {
        console.log(`获取 ${cfg.name}...`);
        let data = [];
        try {
            if (cfg.yahoo) data = await fetchYahoo(cfg.yahoo);
            else if (cfg.sina) data = await fetchSina(cfg.sina);
            
            if (data.length > 50) {
                // 保存数据
                const out = { name: cfg.name, symbol: key, divYield: cfg.div, updated: new Date().toISOString(), data };
                fs.writeFileSync(path.join(OUT_DIR, `${key}.json`), JSON.stringify(out, null, 2));
                console.log(`  ✅ ${data.length} 条`);
            } else {
                console.log(`  ❌ 数据不足 (${data.length})`);
            }
        } catch (e) {
            console.log(`  ❌ ${e.message}`);
        }
    }
}

main().catch(console.error);
