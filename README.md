# ETH/BTC 阶梯定投指标监控

## 部署步骤

### 1. 创建 GitHub 仓库
1. 打开 https://github.com/new
2. 仓库名随便填，比如 `eth-dca-indicator`
3. 选择 **Public**（公开，GitHub Pages 免费需要公开仓库）
4. 点击创建

### 2. 上传代码
把 `eth_github` 文件夹里的**所有文件**上传到仓库（可以用 GitHub 网页端上传，也可以用 Git 命令行）。

### 3. 开启 GitHub Pages
1. 进仓库 → **Settings** → **Pages**
2. **Source** 选 **Deploy from a branch**
3. **Branch** 选 `main`，目录选 `/ (root)`
4. 点 **Save**
5. 等几分钟，你的网站地址就会显示为 `https://你的用户名.github.io/仓库名/`

### 4. 配置邮箱（可选，收日报邮件）
进仓库 → **Settings** → **Secrets and variables** → **Actions** → 点 **New repository secret**，添加以下密钥：

| Secret 名称 | 说明 | 示例 |
|---|---|---|
| `SMTP_HOST` | SMTP 服务器地址 | `smtp.qq.com` |
| `SMTP_PORT` | 端口 | `587` |
| `SMTP_USER` | 邮箱账号 | `your@qq.com` |
| `SMTP_PASS` | 邮箱授权码（不是密码） | `xxxxxxxxxxxx` |
| `EMAIL_TO` | 收件邮箱 | `your@qq.com` |
| `EMAIL_FROM` | 发件地址（可空，默认用 SMTP_USER） | |

> QQ邮箱授权码获取：登录 QQ邮箱 → 设置 → 账户 → 开启 SMTP → 生成授权码

如果不配邮箱，网站照常运行，只是收不到邮件通知。

### 5. 启用定时任务
GitHub Actions 会自动启用，每天早上 9:00 自动运行一次。

你也可以在仓库 → **Actions** → **每日定投指标更新** → **Run workflow** 手动触发。

## 友链管理
目前友链写在 `data.json` 里。后续可以加后台管理界面（后续迭代）。

## 自定义阈值
编辑 `.github/workflows/daily.yml` 中的 `THRESH_ALLIN`、`THRESH_HEAVY` 等参数即可。

## 技术栈
- GitHub Actions（定时任务 + 数据采集）
- GitHub Pages（前端托管）
- Binance API（行情数据）
- Python（指标计算）
- SMTP（邮件通知）
