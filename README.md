# 🤖 AI 热点日报生成器

基于 xAI Grok 的 X 平台 AI 热点自动采集工具，每日自动搜索、翻译并推送到飞书。

## 功能

- 按 7 个分类独立搜索 X 平台热门推文
- 每个分类搜索 2 次并合并去重，提升覆盖率
- 自动将英文内容翻译成中文
- 支持定时任务（每天 UTC+8 08:00 执行）
- 结果自动推送到飞书 Lark

## 分类

| 分类 | 说明 |
|------|------|
| 🚀 新AI产品/工具 | 新发布的 AI 产品、应用、SaaS 工具 |
| 🤖 新AI硬件 | AI 芯片、NPU、GPU 新品、硬件设备 |
| 🔧 AI组件/Skill/MCP | MCP server、AI agent 组件、plugin |
| 📦 开源模型/项目 | 开源 AI 模型、数据集、GitHub 项目 |
| 📄 方法论/技术/论文 | AI 论文、技术突破、新训练方法 |
| 💬 行业讨论/争议 | 行业争议、大佬观点、政策监管 |
| 💡 AI新概念 | 新的 AI 概念、术语、范式 |

## 安装

```bash
pip install xai-sdk requests schedule
```

## 配置

创建 `config.json`：

```json
{
    "xai_api_key": "你的 xAI API Key",
    "lark_webhook_url": "你的飞书 Webhook URL"
}
```

## 使用

```bash
# 立即执行一次
python xai.py

# 快速模式（每类只搜 1 次）
python xai.py --quick

# 自定义时间范围
python xai.py --hours 12

# 不推送飞书
python xai.py --no-lark

# 不翻译英文
python xai.py --no-translate

# 启动定时任务（每天 UTC+8 08:00）
python xai.py --schedule
```

## 后台运行

```bash
nohup python xai.py --schedule > log.txt 2>&1 &
```

## 输出格式

```
• **Google Labs 在印度推出 Pomelli，一款 AI 营销工具...**
👤 @GoogleIndia
🔗 https://x.com/GoogleIndia/status/xxx
⭐ 2073/206
```

## License

MIT
