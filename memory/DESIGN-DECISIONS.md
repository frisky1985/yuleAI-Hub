# yuleAI-Hub 设计决策记录

## 最终方案：方案A — 紫色知识家园

**日期：** 2026-05-26
**Logo：** YL（紫色渐变 40px 圆角图标）
**配色：** 紫 `#6C5CE7` + 绿松 `#00B894` + 暖金 `#FDCB6E`
**字体：** 霞鹜文楷（正文）+ Noto Sans SC（界面元素）

## 关键教训：GitHub Pages 部署

- **.nojekyll** — 根目录放空文件 `.nojekyll`，禁用 Jekyll 处理
- **CSS 内联** — 样式直接写在 `<style>` 标签里而非外部文件，确保本地和线上渲染完全一致
- 之前踩坑：外部 CSS 文件 + Jekyll 处理后，本地 demo-A.html 和 GitHub Pages 效果不同，因为 Jekyll 会处理 `_layouts/` 等目录、可能修改文件路径
- 解决办法：`.nojekyll` + CSS 内联到 HTML → 本地看到什么，线上就是什么

## 站点结构

```
yuleAI-Hub/
├── .nojekyll           # GitHub Pages 禁用 Jekyll
├── index.html          # 首页（内联CSS，方案A设计）
├── search.json         # 搜索索引
├── know-how/           # 实践指南
├── tools/              # 工具配置
├── projects/           # 项目文档
├── knowledge/          # 知识库
├── skills/             # 技能
├── rules/              # 规则集
└── about/              # 关于
```

## 用到的工具链

- OpenClaw (当前运行环境)
- Hermes Agent — 通过 MCP Bridge 委派设计任务
- QoderCLI — 代码分析和对比
- GitHub Pages — 静态站点托管
- 浏览器 — 验证部署效果
