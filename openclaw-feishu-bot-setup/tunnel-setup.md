# 公网隧道搭建指南

## 场景说明

OpenClaw gateway 运行在本地（`localhost:18789`），飞书需要公网 HTTPS 地址推送事件。需要将本地端口暴露到公网。

## 方案对比

| 方案 | 安装 | 国内可用性 | 域名稳定性 | 推荐场景 |
|:-----|:-----|:----------|:----------|:---------|
| **localhost.run** | 零安装（SSH 原生） | ✅ 好 | ❌ 每次重连变 | 开发测试 |
| **serveo.net** | 零安装（SSH 原生） | ⚠️ 不稳定 | ❌ 每次重连变 | 备用 |
| **Cloudflare Tunnel** | 需安装 cloudflared | ✅ 好 | ✅ 稳定 | 生产推荐 |
| **frp** | 需 frp 客户端+服务端 | ✅ 最好 | ✅ 稳定 | 生产推荐 |
| **ngrok** | 需下载二进制 | ⚠️ 被墙 | ✅ 固定子域名（需付费） | 商用开发 |

> **推荐开发阶段：** localhost.run（无需任何注册和安装）
> **推荐生产阶段：** Cloudflare Tunnel 或自建 frp

---

## 一、localhost.run（零安装，推荐开发用）

### 前置条件
- SSH 客户端（macOS/Linux 自带）
- 能访问 `localhost.run`（SSH 端口 22）

### 启动命令

```bash
ssh -R 80:localhost:18789 nokey@localhost.run
```

### 输出示例

```
** your connection id is xxxx-xxxx-xxxx, please mention it if you send me a message about an issue. **
9239ab27cc1ba2.lhr.life tunneled with tls termination, https://9239ab27cc1ba2.lhr.life
```

记录输出的 URL（如 `https://9239ab27cc1ba2.lhr.life`），这就是你的公网地址。

### 验证

```bash
curl https://<tunnel-url>/
# 应返回 OpenClaw gateway 的响应
```

### 后台运行（保持持久）

```bash
# 使用 nohup 保持后台运行
nohup ssh -o ServerAliveInterval=60 -R 80:localhost:18789 nokey@localhost.run > /tmp/tunnel.log 2>&1 &
```

### 注意事项
- **每次重启隧道 URL 会变**——飞书事件回调地址需要同步更新
- 隧道超时自动断开后需重新连接
- 建议配合 `autossh` 实现自动重连

---

## 二、serveo.net（备选方案）

```bash
ssh -R 80:localhost:18789 serveo.net
```

### 自定义子域名
```bash
ssh -R mydomain:80:localhost:18789 serveo.net
```

---

## 三、Cloudflare Tunnel（生产推荐）

### 安装 cloudflared
```bash
# macOS
brew install cloudflared

# 或手动下载
curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz -o /tmp/cloudflared.tgz
```

### 登录并创建隧道
```bash
cloudflared tunnel login
cloudflared tunnel create openclaw-tunnel
```

### 配置
```yaml
# ~/.cloudflared/config.yml
tunnel: <tunnel-id>
credentials-file: /Users/stefan/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: bot.yourdomain.com
    service: http://localhost:18789
  - service: http_status:404
```

### 启动
```bash
cloudflared tunnel run openclaw-tunnel
```

### DNS 配置
在 Cloudflare DNS 面板添加 CNAME 记录指向 `<tunnel-id>.cfargotunnel.com`

---

## 四、常见问题

### Q1: SSH 隧道频繁断开

**原因：** NAT 超时或网络不稳定。

**解决：**
```bash
# 添加保活参数
ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -R 80:localhost:18789 nokey@localhost.run

# 或使用 autossh 自动重连
brew install autossh
autossh -M 0 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -R 80:localhost:18789 nokey@localhost.run
```

### Q2: GitHub 连接超时

在中国大陆访问 GitHub、ngrok 等境外服务可能出现连接问题：
- HTTPS（端口 443）→ 可能被墙
- SSH（端口 22）→ 通常可用
- 建议使用 localhost.run（SSH 隧道）作为替代方案

### Q3: 公网地址不支持 HTTPS

飞书要求回调地址必须是 HTTPS。localhost.run 自带 TLS 终止，自动提供 HTTPS 地址。
