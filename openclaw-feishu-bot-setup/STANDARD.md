# OpenClaw 飞书机器人接入规范

> 规范编号: OSH-FEISHU-001
> 版本: v1.0
> 状态: 生效
> 适用范围: 所有需要对接飞书机器人的 Hermes/OpenClaw 节点

---

## 1. 架构规范

### 1.1 网络拓扑

```
飞书服务器 ──HTTPS──→ 公网隧道 ──SSH──→ 本地 Gateway
```

- **本地**: OpenClaw gateway 监听 `localhost:18789`
- **隧道**: SSH 反向代理（localhost.run / Cloudflare Tunnel / frp）
- **飞书**: HTTPS 回调到隧道公网地址的 `/feishu/events` 路径

### 1.2 端口规范

| 组件 | 协议 | 端口 | 绑定地址 |
|:-----|:-----|:-----|:---------|
| OpenClaw Gateway | HTTP | 18789 | localhost |
| SSH 隧道 | SSH | 22（出站） | — |
| 飞书回调 | HTTPS | 443（入站 → 隧道） | — |

---

## 2. OpenClaw 配置规范

### 2.1 飞书通道配置

```json
{
  "channels": {
    "feishu": {
      "appId": "cli_xxx",
      "appSecret": "xxx",
      "enabled": true,
      "dmPolicy": "open",
      "allowFrom": ["*"],
      "groupPolicy": "open",
      "requireMention": true,
      "webhookPath": "/feishu/events"
    }
  }
}
```

### 2.2 配置检查清单

- [ ] `appId`/`appSecret` 已从飞书开发者后台获取
- [ ] `channels.feishu.enabled` 为 `true`
- [ ] Feishu plugin 已启用（`plugins.entries.feishu.enabled: true`）
- [ ] `requireMention` 根据场景设置（群聊默认 true）
- [ ] gateway 已重启使配置生效

---

## 3. SSH 隧道规范

### 3.1 命令规范

```bash
# 开发环境（localhost.run）
ssh -o ServerAliveInterval=60 -R 80:localhost:18789 nokey@localhost.run
```

### 3.2 高可用要求

- 隧道必须保持持久连接（`ServerAliveInterval=30~60`）
- 生产环境建议使用 `autossh` 实现自动重连
- 生产环境建议使用固定域名（Cloudflare Tunnel 或 frp）

### 3.3 安全规范

- 隧道仅转发 gateway 端口，不暴露其他本地端口
- 飞书回调走 HTTPS（localhost.run 自带 TLS 终止）
- 不将隧道 URL 公开分享

---

## 4. 飞书开放平台规范

### 4.1 必要配置

| 配置项 | 值 | 说明 |
|:-------|:---|:------|
| 回调 URL | `https://{tunnel}/feishu/events` | 事件推送地址 |
| 事件 | `im.message.receive_v1` | 消息接收事件 |
| 权限 | `im:message` | 消息收发权限 |

### 4.2 发布流程

1. 创建/使用已有应用
2. 配置事件订阅（回调 URL + 事件）
3. 开通消息权限
4. 创建版本 → 提交审核 → 发布

---

## 5. 网络故障处理规范

### 5.1 境外服务不可用判定

```bash
# HTTPS 测试
curl --connect-timeout 5 https://github.com
# 超时 → HTTPS 端口被墙

# SSH 测试
ssh -T -o ConnectTimeout=5 git@github.com
# 收到认证响应 → SSH 端口正常
```

### 5.2 降级方案

| 场景 | 措施 |
|:-----|:------|
| HTTPS（443）被墙 | 改用 SSH 隧道（localhost.run） |
| 所有境外不通 | 自建 frp 服务端 |
| 本地无公网 | Cloudflare Tunnel（免费） |

---

## 6. 验收标准

### 6.1 连通性验收

- [ ] `curl http://localhost:18789/` 返回 gateway 页面
- [ ] `curl https://{tunnel}/` 通过隧道访问成功
- [ ] 在飞书发消息能收到回复

### 6.2 日志验收

- [ ] Gateway 日志无 feishu 相关错误
- [ ] 事件订阅回调验证通过
- [ ] 消息收发双向正常

---

## 附录

### A. 术语表

| 术语 | 说明 |
|:-----|:------|
| Gateway | OpenClaw 消息网关，监听端口 18789 |
| Tunnel | SSH 反向代理隧道，将本地端口暴露到公网 |
| Event Subscription | 飞书开放平台的事件推送机制 |
| Webhook Path | Gateway 接收飞书事件的路径（默认 /feishu/events） |

### B. 相关资源

- [yuleAI-Hub: 完整指南](../openclaw-feishu-bot-setup/README.md)
- [隧道搭建详解](../openclaw-feishu-bot-setup/tunnel-setup.md)
- [飞书配置详解](../openclaw-feishu-bot-setup/feishu-config.md)
