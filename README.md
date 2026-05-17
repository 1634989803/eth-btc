# BTC/ETH 定投指标

每天早上自动算 BTC AHR999 和 ETH 阶梯定投指标，更新网页和发邮件。

## 怎么用

进 https://1634989803.github.io/eth-btc/ 看数据就行。

## 怎么收邮件

仓库 Settings → Secrets and variables → Actions，加这几个：

| Secret | 说明 |
|---|---|
| SMTP_HOST | smtp.qq.com |
| SMTP_PORT | 587 |
| SMTP_USER | 你的邮箱 |
| SMTP_PASS | 邮箱授权码 |
| EMAIL_TO | 收件地址 |

不加也能用，只是没邮件。

## 技术

GitHub Actions 每6小时跑一次 → 拿 CoinGecko 数据 → 算指标 → 写入 eth_data.json / btc_data.json → 推仓库。GitHub Pages 展示。
