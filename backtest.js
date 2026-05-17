/**
 * 定投回测引擎
 * 浏览器端运行, 支持多标的对比 + 分红计算
 */

const BACKTEST = {

// 基准标的配置
benches: {
    'csi300':  { name: '沪深300', type: 'index', divYield: 0.02  },
    'csi500':  { name: '中证500', type: 'index', divYield: 0.015 },
    'qqq':     { name: '纳斯达克100', type: 'etf', divYield: 0.0065 },
    'qqqi':    { name: 'QQQI',    type: 'etf', divYield: 0.12   },
    'spy':     { name: '标普500', type: 'etf', divYield: 0.013  },
},

// 从币安获取历史K线 (CORS 友好)
async fetchCryptoOHLC(symbol, days = 800) {
    const url = `https://api.binance.com/api/v3/klines?symbol=${symbol}&interval=1d&limit=${days}`;
    const r = await fetch(url);
    const data = await r.json();
    return data.map(k => ({
        t: k[0], date: new Date(k[0]).toISOString().slice(0,10),
        o: +k[1], h: +k[2], l: +k[3], c: +k[4], v: +k[5]
    }));
},

// 计算阶梯定投指标 (同TV指标逻辑)
calcIndicator(prices, maShort = 120, maLong = 250) {
    if (prices.length < maLong) return null;
    const sma = prices.slice(-maShort).reduce((a,b) => a+b, 0) / maShort;
    const ema = this.calcEMA(prices, maLong);
    return (prices[prices.length-1] / sma) * (prices[prices.length-1] / ema);
},

calcEMA(prices, period) {
    const k = 2 / (period + 1);
    let ema = prices.slice(0, period).reduce((a,b) => a+b, 0) / period;
    for (let i = period; i < prices.length; i++) {
        ema = (prices[i] - ema) * k + ema;
    }
    return ema;
},

// 判断阶梯
getZone(ratio, isBTC = false) {
    if (isBTC) {
        if (ratio < 0.45) return { name: '抄底区', icon: '🟣', mult: 5 };
        if (ratio < 1.20) return { name: '定投区', icon: '🟢', mult: 1 };
        return { name: '持有区', icon: '🟡', mult: 0 };
    }
    if (ratio < 0.35) return { name: '梭哈区', icon: '💜', mult: 5 };
    if (ratio < 0.45) return { name: '重仓区', icon: '💚', mult: 3 };
    if (ratio < 0.65) return { name: '定投区', icon: '💛', mult: 1 };
    if (ratio < 1.60) return { name: '轻投区', icon: '🔵', mult: 0.5 };
    return { name: '止盈区', icon: '🔴', mult: -0.5 }; // -0.5 = 卖一半
},

// 执行回测
async run(options) {
    const {
        coin = 'ETH',                // 币种
        monthlyAmount = 1000,        // 每月定投金额(USD)
        startDate = '2022-01-01',    // 开始日期
        endDate = new Date().toISOString().slice(0,10), // 结束日期
        includeDividends = true,     // 是否算分红
        compareBenchmarks = [],      // 对比标的 ['qqq', 'spy']
    } = options;

    const symbol = coin + 'USDT';
    const isBTC = coin === 'BTC';
    const ohlc = await this.fetchCryptoOHLC(symbol);
    
    // 过滤日期范围
    const filtered = ohlc.filter(d => d.date >= startDate && d.date <= endDate);
    if (filtered.length < 250) throw new Error('数据不足, 请缩小时间范围');
    
    const prices = filtered.map(d => d.c);
    const dates = filtered.map(d => d.date);
    
    // 逐月回测
    let totalShares = 0;
    let totalInvested = 0;
    let peak = 0;
    let maxDrawdown = 0;
    const equityCurve = [];
    
    // 按月初定投
    let lastMonth = '';
    let monthlyDiv = 0;
    
    for (let i = 120; i < prices.length; i++) { // 从有120日均线数据开始
        const currentMonth = dates[i].slice(0, 7);
        const price = prices[i];
        const ratio = this.calcIndicator(prices.slice(0, i + 1), 120, 250);
        if (!ratio) continue;
        
        const zone = this.getZone(ratio, isBTC);
        const date = dates[i];
        
        // 月初定投
        if (currentMonth !== lastMonth) {
            lastMonth = currentMonth;
            if (zone.mult > 0) {
                const invest = monthlyAmount * zone.mult;
                const shares = invest / price;
                totalShares += shares;
                totalInvested += invest;
            } else if (zone.mult < 0 && totalShares > 0) {
                // 止盈: 卖一半
                const sellShares = totalShares * 0.5;
                totalShares -= sellShares;
            }
            
            // 分红 (按月计算)
            if (includeDividends) {
                // 对于crypto没有分红, 但对ETF对比标的会算
            }
        }
        
        const portfolioValue = totalShares * price;
        if (portfolioValue > peak) peak = portfolioValue;
        const dd = (peak - portfolioValue) / peak;
        if (dd > maxDrawdown) maxDrawdown = dd;
        
        // 每10天记录一点
        if (i % 10 === 0 || i === prices.length - 1) {
            equityCurve.push({ date: dates[i], value: portfolioValue, invested: totalInvested });
        }
    }
    
    const finalValue = totalShares * prices[prices.length - 1];
    const totalReturn = totalInvested > 0 ? ((finalValue - totalInvested) / totalInvested * 100) : 0;
    const annualizedReturn = this.calcAnnualized(totalReturn, filtered.length / 365);
    
    const result = {
        coin,
        totalInvested: Math.round(totalInvested),
        finalValue: Math.round(finalValue),
        totalReturn: Math.round(totalReturn * 100) / 100,
        annualizedReturn: Math.round(annualizedReturn * 100) / 100,
        maxDrawdown: Math.round(maxDrawdown * 10000) / 100,
        totalShares: Math.round(totalShares * 10000) / 10000,
        equityCurve,
        dateRange: { start: dates[120], end: dates[dates.length - 1] },
        months: lastMonth,
    };
    
    // 对比标的
    result.benchmarks = [];
    for (const bench of compareBenchmarks) {
        const benchResult = await this.runBenchmark(bench, startDate, endDate, monthlyAmount, includeDividends);
        if (benchResult) result.benchmarks.push(benchResult);
    }
    
    return result;
},

// 回测基准标的 (从预加载的数据)
async runBenchmark(name, startDate, endDate, monthlyAmount, includeDividends) {
    try {
        const r = await fetch(`benchmarks/${name}.json`);
        const data = await r.json();
        // data = [{date, price}, ...] filtered by date range
        const filtered = data.filter(d => d.date >= startDate && d.date <= endDate);
        if (filtered.length < 20) return null;
        
        const config = this.benches[name];
        const divYield = config ? config.divYield : 0;
        const monthlyDivRate = divYield / 12;
        
        let shares = 0;
        let invested = 0;
        let lastMonth = '';
        
        for (let i = 0; i < filtered.length; i++) {
            const d = filtered[i];
            const month = d.date.slice(0, 7);
            
            if (month !== lastMonth) {
                lastMonth = month;
                const invest = monthlyAmount;
                shares += invest / d.price;
                invested += invest;
                
                // 分红: 按每月股息率增加股份
                if (includeDividends && monthlyDivRate > 0) {
                    const divShares = (shares * monthlyDivRate);
                    shares += divShares;
                }
            }
        }
        
        const finalValue = shares * filtered[filtered.length - 1].price;
        const totalReturn = ((finalValue - invested) / invested * 100);
        
        return {
            name: config ? config.name : name,
            totalReturn: Math.round(totalReturn * 100) / 100,
            finalValue: Math.round(finalValue),
            invested: Math.round(invested),
        };
    } catch {
        return null;
    }
},

calcAnnualized(totalReturn, years) {
    if (years <= 0) return 0;
    return (Math.pow(1 + totalReturn / 100, 1 / years) - 1) * 100;
}

};
