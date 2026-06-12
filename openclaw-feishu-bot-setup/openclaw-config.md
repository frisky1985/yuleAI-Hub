# OpenClaw 飞书通道配置

## openclaw.json 配置

在 `~/.openclaw/openclaw.json` 中配置飞书通道：

```json
{
  "channels": {
    "feishu": {
      "appId": "cli_aa90208374389cc2",
      "appSecret": "your-app-secret",
      "dmPolicy": "open",
      "allowFrom": ["*"],
      "groupPolicy": "open",
      "requireMention": true,
      "enabled": true,
      "groupAllowFrom": ["*"],
      "textChunkLimit": 15000,
      "chunkMode": "length"
    }
  }
}
```

### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|:-----|:-----|:-------|:------|
| `appId` | string | — | 飞书应用的 App ID |
| `appSecret` | string | — | 飞书应用的 App Secret |
| `enabled` | bool | `true` | 是否启用飞书通道 |
| `dmPolicy` | string | `"open"` | 私聊策略：`"open"`（任何人可发）`"closed"`（仅允许列表） |
| `allowFrom` | string[] | `["*"]` | 允许私聊的用户列表（`"*"` 表示所有人） |
| `groupPolicy` | string | `"open"` | 群聊策略 |
| `requireMention` | bool | `true` | 群聊中是否必须 @ 才响应 |
| `groupAllowFrom` | string[] | `["*"]` | 允许的群组列表 |
| `textChunkLimit` | number | `15000` | 单条消息最大字符数 |
| `chunkMode` | string | `"length"` | 分块模式 `"length"` 或 `"count"` |
| `webhookPath` | string | `"/feishu/events"` | 飞书事件回调路径 |
| `connectionMode` | string | `"webhook"` | 连接模式（webhook 需要 verificationToken + encryptKey） |

### 重启生效

修改配置后需重启 OpenClaw gateway：

```bash
launchctl unload ~/Library/LaunchAgents/ai.openclaw.gateway.plist
sleep 1
launchctl load ~/Library/LaunchAgents/ai.openclaw.gateway.plist
```

### 验证配置

```bash
# 检查 gateway 日志
grep feishu /Users/stefan/.openclaw/logs/gateway.log | tail -5
```
