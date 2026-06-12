# 飞书开放平台配置指南

## 前置准备

在开始前确保已有：
1. 飞书管理员账号
2. OpenClaw gateway 正在运行（`localhost:18789`）
3. 公网隧道已启动（参见 [tunnel-setup.md](./tunnel-setup.md)）

---

## 一、创建飞书应用

1. 打开 [飞书开发者后台](https://open.feishu.cn/app)
2. 点击「创建企业自建应用」
3. 填写应用名称（如"OpenClaw 助手"）和描述
4. 点击「确定创建」

> ⚠️ 如果已有应用（如 appId 为 `cli_aa90208374389cc2`），可直接使用已有应用。

---

## 二、获取凭证

创建应用后，进入「凭证与基础信息」页面：

| 字段 | 说明 | 用途 |
|:-----|:------|:------|
| **App ID** | 应用唯一标识（如 `cli_xxxx`） | 填入 OpenClaw config |
| **App Secret** | 应用密钥 | 填入 OpenClaw config（敏感信息，请勿泄露） |

---

## 三、配置权限

进入「权限管理」页面，添加以下权限：

### 必需权限

| 权限 | 代码 | 用途 |
|:-----|:------|:------|
| 获取单聊、群组消息 | `im:message` | 接收和发送消息 |
| 获取用户发给机器人的单聊消息 | `im:message.p2p_msg:readonly` | 私聊场景 |
| 获取群组中@机器人的消息 | `im:message.group_at_msg:readonly` | 群聊场景 |
| 获取与发送群聊消息 | `im:chat:readonly` | 读取群组信息 |
| 获取用户基本信息 | `contact:user.base:readonly` | 识别用户身份 |

### 可选权限（按需添加）

| 权限 | 代码 | 用途 |
|:-----|:------|:------|
| 查看、转发和发送文件 | `drive:drive` | 文件处理 |
| 查看云文档 | `docx:document:readonly` | lark-cli 读取文档 |

---

## 四、配置事件订阅

### 4.1 设置回调地址

进入「事件订阅」页面：

1. **请求网址 URL：**
   ```
   https://<tunnel-url>/feishu/events
   ```
   例如 `https://9239ab27cc1ba2.lhr.life/feishu/events`

2. 点击「验证」→ 应返回 `Challenge 验证通过`

> ❗ 如果验证失败，先检查隧道是否运行：`curl https://<tunnel-url>/`

### 4.2 添加事件

点击「添加事件」，搜索并添加以下事件：

| 事件 | 用途 |
|:-----|:------|
| `im.message.receive_v1` | 接收用户和群聊中发送的消息 |

### 4.3 配置订阅方式（可选）

如果 OpenClaw 配置了 `verificationToken` 和 `encryptKey`，在此页面填写对应值。

---

## 五、发布应用

1. 回到「版本管理与发布」页面
2. 点击「创建版本」
3. 填写版本号和更新说明
4. 提交审核（企业自建应用通常自动通过）
5. 审核通过后，点击「发布」

---

## 六、验证连通性

### 在飞书中测试
1. 搜索你的应用名称，打开对话框
2. 发送一条消息（如"你好"）
3. 应收到机器人的回复

### 检查日志
```bash
# 查看 OpenClaw gateway 日志
cat /Users/stefan/.openclaw/logs/gateway.log | grep feishu | tail -20

# 检查隧道是否正常
curl https://<tunnel-url>/feishu/events
```

---

## 七、常见问题

### Q1: 事件回调验证失败

**可能原因：**
- 隧道未启动或已断开
- OpenClaw gateway 未运行
- 回调地址中的 `/feishu/events` 路径写错

**排查：**
```bash
# 检查 gateway 是否运行
ps aux | grep openclaw | grep gateway

# 检查隧道
curl https://<tunnel-url>/
```

### Q2: 机器人不回复消息

**可能原因：**
- 应用未发布上线
- OpenClaw 配置中 `requireMention: true` 但未 @ 机器人
- 飞书事件订阅未正确配置

**排查：**
- 确认应用状态为「已发布」
- 群聊中需要 @ 机器人才能触发回复
