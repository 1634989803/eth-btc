/**
 * 回测引擎 v2
 * 支持: ETH/BTC(实时) + 沪深300/中证500/QQQ/SPY(预载数据)
 * 策略: 指标DCA / 普通定投 / 一次性投入
 * 分红: ETF含分红再投
 */

const BT = {

// 所有可回测资产
assets: {
    'ETH': { name: 'ETH 以太坊', type: 'crypto', apiSymbol: 'ETHUSDT' },
    'BTC': { name: 'BTC 比特币', type: 'crypto', apiSymbol: 'BTCUSDT' },
    'csi300': { name: '沪深300', type: 'bench', file: 'csi300.json' },
    'csi500': { name: '中证500', type: 'bench', file: 'csi500.json' },
    'qqq': { name: '纳斯达克100(QQQ)', type: 'bench', file: 'qqq.json' },
    'spy': { name: '标普500(SPY)', type: 'bench', file: 'spy.json' },
},

// 从币安取K线 (CORS友好)
async fetchBinance(symbol, limit = 800) {
    const r = await fetch(`https://api.binance.com/api/v3/klines?symbol=${symbol}&interval=1d&limit=${limit}`);
    const d = await r.json();
    return d.map(k => ({ date: new Date(k[0]).toISOString().slice(0,10), price: +k[4] }));
},

// 从预载JSON取数据
async fetchBench(file) {
    const r = await fetch(`benchmarks/${file}`);
    const d = await r.json();
    return d.data.map(x => ({ date: x.date, price: x.price }));
},

// 计算指标 (ETH阶梯 / BTC-AHR999)
calcIndicator(prices, isBTC) {
    if (prices.length < 250) return null;
    const maShort = 120, maLong = 250;
    const sma = prices.slice(-maShort).reduce((a,b) => a+b, 0) / maShort;
    const k = 2 / (maLong + 1);
    let ema = prices.slice(-maLong).reduce((a,b) => a+b, 0) / maLong;
    for (let i = prices.length - maLong; i < prices.length; i++) ema = (prices[i] - ema) * k + ema;
    const ratio = (prices[prices.length-1] / sma) * (prices[prices.length-1] / ema);
    
    if (isBTC) {
        // BTC AHR999: 需要指数回归
        const n = prices.length;
        const x = [...Array(n).keys()];
        const y = prices.map(p => Math.log(p));
        const ax = x.reduce((a,b) => a+b, 0) / n;
        const ay = y.reduce((a,b) => a+b, 0) / n;
        const num = x.reduce((s, xi, i) => s + (xi - ax) * (y[i] - ay), 0);
        const den = x.reduce((s, xi) => s + (xi - ax) ** 2, 0);
        const a = den ? num / den : 0;
        const b = ay - a * ax;
        const expVal = Math.exp(a * (n - 1) + b);
        return (prices[prices.length-1] / sma) * (prices[prices.length-1] / expVal);
    }
    return ratio;
},

// 判断阶梯
getZone(ratio, isBTC) {
    if (isBTC) {
        if (ratio < 0.45) return { name:'抄底区', mult:5 };
        if (ratio < 1.20) return { name:'定投区', mult:1 };
        return { name:'持有区', mult:0 };
    }
    if (ratio < 0.35) return { name:'梭哈区', mult:5 };
    if (ratio < 0.45) return { name:'重仓区', mult:3 };
    if (ratio < 0.65) return { name:'定投区', mult:1 };
    if (ratio < 1.60) return { name:'轻投区', mult:0.5 };
    return { name:'止盈区', mult:-0.5 };
},

// 主回测
async run(opts) {
    const { asset, strategy, monthly, startDate, endDate, benchmarks, includeDiv } = opts;
    const cfg = this.assets[asset];
    if (!cfg) throw new Error('未知资产');
    
    // 取数据
    let data;
    if (cfg.type === 'crypto') data = await this.fetchBinance(cfg.apiSymbol);
    else data = await this.fetchBench(cfg.file);
    
    if (!data || data.length < 20) throw new Error('数据不足');
    data = data.filter(d => d.date >= startDate && d.date <= endDate);
    if (data.length < 20) throw new Error('该时间段数据不足');
    
    const isBTC = asset === 'BTC';
    const divYield = includeDiv && cfg.type === 'bench' ? (cfg.divYield || 0) : 0;
    const monthlyDivRate = divYield / 12;
    
    // 回测
    let shares = 0, invested = 0, peak = 0, maxDD = 0;
    const curve = [];
    let lastMonth = '';
    let startIdx = 0;
    
    // 指标DCA需要至少250个数据点预热
    if (strategy === 'indicator') {
        startIdx = 250;
        if (data.length <= startIdx) throw new Error('数据太少, 指标DCA需要至少250天数据预热');
    }
    
    for (let i = startIdx; i < data.length; i++) {
        const { date, price } = data[i];
        const month = date.slice(0, 7);
        
        // 每月定投
        if (month !== lastMonth) {
            lastMonth = month;
            
            let investAmt = 0;
            if (strategy === 'lump' && i === startIdx) {
                // 一次性投入
                investAmt = monthly;
            } else if (strategy === 'regular') {
                investAmt = monthly;
            } else if (strategy === 'indicator') {
                // 指标DCA
                const subPrices = data.slice(0, i + 1).map(d => d.price);
                const ratio = this.calcIndicator(subPrices, isBTC);
                if (ratio) {
                    const zone = this.getZone(ratio, isBTC);
                    if (zone.mult > 0) {
                        investAmt = monthly * zone.mult;
                    } else if (zone.mult < 0 && shares > 0) {
                        // 止盈: 卖一半
                        shares *= 0.5;
                    }
                }
            }
            
            if (investAmt > 0) {
                const newShares = investAmt / price;
                shares += newShares;
                invested += investAmt;
            }
            
            // 分红再投
            if (monthlyDivRate > 0 && shares > 0) {
                shares += shares * monthlyDivRate;
            }
        }
        
        const value = shares * price;
        if (value > peak) peak = value;
        const dd = peak > 0 ? (peak - value) / peak * 100 : 0;
        if (dd > maxDD) maxDD = dd;
        
        if (i % 20 === 0 || i === data.length - 1) {
            curve.push({ date, value: Math.round(value), invested: Math.round(invested) });
        }
    }
    
    const finalPrice = data[data.length - 1].price;
    const finalValue = Math.round(shares * finalPrice);
    const totalReturn = invested > 0 ? ((finalValue - invested) / invested * 100) : 0;
    const years = (data.length - startIdx) / 365;
    const annualized = years > 0 ? (Math.pow(1 + totalReturn / 100, 1 / years) - 1) * 100 : 0;
    
    const result = {
        asset: cfg.name,
        strategy: strategy === 'indicator' ? '指标DCA' : strategy === 'regular' ? '普通定投' : '一次性投入',
        totalInvested: invested,
        finalValue,
        totalReturn: Math.round(totalReturn * 100) / 100,
        annualized: Math.round(annualized * 100) / 100,
        maxDrawdown: Math.round(maxDD * 100) / 100,
        months: Math.round((data.length - startIdx) / 30),
        startDate: data[startIdx].date,
        endDate: data[data.length - 1].date,
        finalPrice: Math.round(finalPrice * 100) / 100,
        curve,
    };
    
    // 对比标的
    result.comparisons = [];
    for (const b of benchmarks) {
        try {
            const comp = await this.compareBench(b, startDate, endDate, monthly, strategy === 'lump', includeDiv);
            result.comparisons.push(comp);
        } catch {}
    }
    
    return result;
},

// 对比标的回测 (简单定投)
async compareBench(name, startDate, endDate, monthly, isLump, includeDiv) {
    const cfg = this.assets[name];
    if (!cfg) return null;
    let data;
    if (cfg.type === 'crypto') data = await this.fetchBinance(cfg.apiSymbol);
    else data = await this.fetchBench(cfg.file);
    if (!data) return null;
    
    data = data.filter(d => d.date >= startDate && d.date <= endDate);
    if (data.length < 10) return null;
    
    const divYield = includeDiv && cfg.type === 'bench' ? (cfg.divYield || 0) : 0;
    const mdr = divYield / 12;
    
    let shares = 0, invested = 0, lastMonth = '';
    for (const { date, price } of data) {
        const month = date.slice(0, 7);
        if (month !== lastMonth) {
            lastMonth = month;
            if (isLump && invested === 0) {
                shares += monthly / price;
                invested += monthly;
            } else if (!isLump) {
                shares += monthly / price;
                invested += monthly;
            }
            if (mdr > 0 && shares > 0) shares += shares * mdr;
        }
    }
    
    const finalValue = Math.round(shares * data[data.length - 1].price);
    const totalReturn = invested > 0 ? ((finalValue - invested) / invested * 100) : 0;
    
    return { name: cfg.name, totalInvested: invested, finalValue, totalReturn: Math.round(totalReturn * 100) / 100 };
}

};
