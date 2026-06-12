# OpenClaw 飞书机器人 + 公网隧道 搭建指南

> 场景：在本地开发机上运行 OpenClaw gateway，通过 SSH 隧道暴露到公网，对接飞书机器人。

## 📋 架构

```
飞书服务器                   公网隧道                       本地 Mac
┌──────────┐          ┌─────────────────┐          ┌─────────────────┐
│ 飞书事件   │──HTTPS──→│ localhost.run    │──SSH───→│ OpenClaw        │
│ 回调      │          │ (公网服务器)      │ 隧道    │ Gateway         │
│ 消息推送  │←──HTTPS──│ 9239ab27cc1ba2   │←──SSH──│ localhost:18789 │
└──────────┘          │ .lhr.life        │          └─────────────────┘
                      └─────────────────┘
```

## 📁 目录

| 文件 | 说明 |
|:-----|:------|
| [tunnel-setup.md](./tunnel-setup.md) | SSH 公网隧道搭建（localhost.run / serveo.net） |
| [feishu-config.md](./feishu-config.md) | 飞书开放平台配置（应用创建、权限、事件订阅） |
| [openclaw-config.md](./openclaw-config.md) | OpenClaw gateway 飞书通道配置 |

## 🚀 快速开始

```bash
# 1. 启动 OpenClaw gateway（端口 18789）
launchctl load ~/Library/LaunchAgents/ai.openclaw.gateway.plist

# 2. 启动 SSH 公网隧道
ssh -R 80:localhost:18789 nokey@localhost.run

# 3. 在飞书开发者后台配置事件回调
#    回调 URL: https://<tunnel-url>/feishu/events

# 4. 发布飞书应用上线
```
