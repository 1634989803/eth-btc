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

// 计算指标 (ETH / BTC-AHR999)
calcIndicator(prices, isBTC) {
    if (prices.length < 250) return null;
    const n = prices.length;
    
    if (isBTC) {
        // BTC AHR999: (price/SMA200) * (price/指数回归)
        const sma200 = prices.slice(-200).reduce((a,b) => a+b, 0) / 200;
        const x = [...Array(n).keys()];
        const y = prices.map(p => Math.log(p));
        const avgX = x.reduce((a,b) => a+b, 0) / n;
        const avgY = y.reduce((a,b) => a+b, 0) / n;
        const num = x.reduce((s, xi, i) => s + (xi - avgX) * (y[i] - avgY), 0);
        const den = x.reduce((s, xi) => s + (xi - avgX) ** 2, 0);
        const a = den ? num / den : 0;
        const b = avgY - a * avgX;
        const expVal = Math.exp(a * (n - 1) + b);
        return (prices[n-1] / sma200) * (prices[n-1] / expVal);
    }
    
    // ETH: (price/SMA120) * (price/EMA250)
    const sma120 = prices.slice(-120).reduce((a,b) => a+b, 0) / 120;
    const k = 2 / 251;
    let ema250 = prices.slice(-250).reduce((a,b) => a+b, 0) / 250;
    for (let i = n - 250; i < n; i++) ema250 = (prices[i] - ema250) * k + ema250;
    return (prices[n-1] / sma120) * (prices[n-1] / ema250);
},

// 判断阶梯
getZone(ratio, isBTC) {
    if (isBTC) {
        if (ratio < 0.45) return { name:'抄底区', mult:5 };
        if (ratio < 1.20) return { name:'定投区', mult:1 };
        return { name:'持有区', mult:0 };
    }
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
    
    // 取全部数据（不过滤日期）
    let allData;
    if (cfg.type === 'crypto') allData = await this.fetchBinance(cfg.apiSymbol, 800);
    else allData = await this.fetchBench(cfg.file);
    if (!allData || allData.length < 20) throw new Error('数据不足');
    
    const isBTC = asset === 'BTC';
    const divYield = includeDiv && cfg.type === 'bench' ? (cfg.divYield || 0) : 0;
    const monthlyDivRate = divYield / 12;
    
    // 找到用户选择的起止点在全部数据中的位置
    const startIdx = allData.findIndex(d => d.date >= startDate);
    const endIdx = allData.findIndex(d => d.date > endDate);
    const data = allData.slice(0, endIdx > 0 ? endIdx : allData.length);
    if (startIdx < 0) throw new Error('开始日期超出数据范围');
    if (endIdx > 0 && endIdx - startIdx < 2) throw new Error('该时间段数据不足');
    
    console.log(`回测: ${asset} ${startDate}~${endDate} 总数据${data.length}条 从${startIdx}开始`);
    
    // 回测
    let shares = 0, invested = 0, peak = 0, maxDD = 0;
    const curve = [];
    let lastMonth = '';
    let firstInvest = true;
    
    for (let i = 0; i < data.length; i++) {
        const { date, price } = data[i];
        const isInRange = i >= startIdx;
        
        // 用全部数据计算指标（预热用startDate之前的数据）
        // 但只从startDate开始定投
        const month = date.slice(0, 7);
        
        if (isInRange && month !== lastMonth) {
            lastMonth = month;
            
            let investAmt = 0;
            if (strategy === 'lump' && firstInvest) {
                investAmt = monthly;
                firstInvest = false;
            } else if (strategy === 'regular') {
                investAmt = monthly;
            } else if (strategy === 'indicator' && i >= 250) {
                // 用全部数据(含预热)算指标
                const subPrices = data.slice(0, i + 1).map(d => d.price);
                const ratio = this.calcIndicator(subPrices, isBTC);
                if (ratio) {
                    const zone = this.getZone(ratio, isBTC);
                    if (zone.mult > 0) {
                        investAmt = monthly * zone.mult;
                    } else if (zone.mult < 0 && shares > 0) {
                        shares *= 0.5;
                    }
                }
            }
            
            if (investAmt > 0) {
                shares += investAmt / price;
                invested += investAmt;
            }
            
            if (monthlyDivRate > 0 && shares > 0) {
                shares += shares * monthlyDivRate;
            }
        }
        
        // 只记录可见范围内的曲线
        if (isInRange) {
            const value = shares * price;
            if (value > peak) peak = value;
            const dd = peak > 0 ? (peak - value) / peak * 100 : 0;
            if (dd > maxDD) maxDD = dd;
            
            if (i % 20 === 0 || i === data.length - 1) {
                curve.push({ date, value: Math.round(value), invested: Math.round(invested) });
            }
        }
    }
    
    const finalData = data[data.length - 1];
    const finalValue = Math.round(shares * finalData.price);
    const totalReturn = invested > 0 ? ((finalValue - invested) / invested * 100) : 0;
    const totalMonths = (data.length - startIdx) / 30.44;
    const years = totalMonths / 12;
    let annualized = 0;
    if (years > 0 && totalReturn > -100) {
        annualized = (Math.pow(1 + totalReturn / 100, 1 / years) - 1) * 100;
    }
    
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
        finalPrice: Math.round(finalData.price * 100) / 100,
        curve,
    };
    
    // 对比标的（用相同逻辑）
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
