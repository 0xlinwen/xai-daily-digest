"""
xAI X Search 日报生成器
- 按分类独立搜索，提升覆盖率
- 每个分类搜索2次并合并去重
- 自动将英文内容翻译成中文
- 支持定时任务（UTC+8 每日执行）
- 结果推送到 Lark

配置文件: config.json
{
    "xai_api_key": "你的 xAI API Key",
    "lark_webhook_url": "你的 Lark Webhook URL"
}
"""

import time
import json
import argparse
import requests
import schedule
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import x_search

# ──────────────────────────────────────────
# 配置
# ──────────────────────────────────────────
CONFIG_FILE = Path(__file__).parent / "config.json"
MODEL = "grok-4-1-fast"
OUTPUT_DIR = Path("./output")
TIMEZONE = ZoneInfo("Asia/Shanghai")  # UTC+8
SCHEDULE_TIME = "08:00"  # 每天 UTC+8 早上8点执行


def load_config() -> dict:
    """从 config.json 加载配置"""
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"配置文件不存在: {CONFIG_FILE}\n请复制 config.json.example 并填入你的配置")
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


CONFIG = load_config()
API_KEY = CONFIG.get("xai_api_key", "")
LARK_WEBHOOK_URL = CONFIG.get("lark_webhook_url", "")
MAX_RESULTS = CONFIG.get("max_results_per_category")
SEARCH_RUNS = CONFIG.get("search_runs_per_category")

# 分类定义：(显示标题, 搜索关键词描述)
CATEGORIES = [
    ("🚀 新AI产品/工具", "新发布的AI产品、应用、SaaS工具，product launch，AI app"),
    ("🤖 新AI硬件", "AI芯片、NPU、GPU新品、AI硬件设备发布，AI chip hardware"),
    ("🔧 AI组件/Skill/MCP", "MCP server、AI agent组件、plugin、skill、function calling工具"),
    ("📦 开源模型/项目", "开源AI模型、数据集、github项目发布，open source model release"),
    ("📄 方法论/技术/论文", "AI论文、技术突破、新训练方法、benchmark，research paper"),
    ("💬 AI行业讨论/争议", "AI行业重要争议、大佬观点、政策监管、融资收购讨论"),
    ("💡 AI新概念", "新的AI概念、术语、范式、思维框架"),
]


# ──────────────────────────────────────────
# Lark 推送
# ──────────────────────────────────────────
def send_to_lark(content: str) -> bool:
    """发送消息到 Lark webhook"""
    if not LARK_WEBHOOK_URL:
        print("⚠️ 未配置 LARK_WEBHOOK_URL，跳过推送")
        return False

    payload = {
        "msg_type": "text",
        "content": {"text": content}
    }

    try:
        resp = requests.post(
            LARK_WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        if resp.status_code == 200 and resp.json().get("code") == 0:
            print("✅ 已推送到 Lark")
            return True
        else:
            print(f"❌ Lark 推送失败: {resp.text}")
            return False
    except Exception as e:
        print(f"❌ Lark 推送异常: {e}")
        return False


# ──────────────────────────────────────────
# 核心搜索函数
# ──────────────────────────────────────────
def _create_client() -> Client:
    if not API_KEY:
        raise ValueError("请在 config.json 中配置 xai_api_key")
    return Client(api_key=API_KEY)


def search_once(client: Client, category_title: str, keywords: str, hours: int) -> str:
    """单次搜索某个分类"""
    chat = client.chat.create(
        model=MODEL,
        tools=[x_search()],
    )
    chat.append(user(f"""
请搜索最近 {hours} 小时内 X 平台上关于以下主题的热门推文：
主题：{keywords}

输出要求：
- 最多返回 {MAX_RESULTS} 条最具代表性的推文
- 没有相关内容时只输出：[暂无]
- 排除广告、转发无评论、无实质内容的推文
- 按热度（点赞+转发+收藏）从高到低排列

每条严格按此格式输出（每个字段单独一行，条目之间空一行）：
• **内容摘要**（1-2句话说明核心信息）
👤 @用户名
🔗 推文URL
⭐ 点赞数/转发数/收藏

示例：
• **Together AI开源了CoderForge-Preview数据集，生成成本13万美元，包含51k任务的6.7B tokens代理编码轨迹。**
👤 @ZainHasan6
🔗 https://x.com/ZainHasan6/status/2026898606838657252
⭐ 1074/76
"""))
    try:
        response = chat.sample()
        return response.content.strip()
    except Exception as e:
        return f"[搜索失败: {e}]"


def merge_and_dedup(client: Client, category_title: str, result_a: str, result_b: str) -> str:
    """合并两次搜索结果并去重"""
    if "[暂无]" in result_a and "[暂无]" in result_b:
        return "[暂无]"
    if "[暂无]" in result_a or "[搜索失败" in result_a:
        return result_b
    if "[暂无]" in result_b or "[搜索失败" in result_b:
        return result_a

    chat = client.chat.create(model=MODEL, tools=[])
    chat.append(user(f"""
以下是针对「{category_title}」主题的两次 X 平台搜索结果，请合并去重：

【第一次结果】
{result_a}

【第二次结果】
{result_b}

合并规则：
- 内容高度相似的推文只保留热度更高的一条
- 保留所有不重复的有价值条目
- 最终最多输出 {MAX_RESULTS} 条，按热度从高到低排列
- 没有任何有效内容时只输出：[暂无]

输出格式（每个字段单独一行，条目之间空一行）：
• **内容摘要**
👤 @用户名
🔗 链接
⭐ 热度
"""))
    try:
        response = chat.sample()
        return response.content.strip()
    except Exception as e:
        return result_a


def search_category(client: Client, title: str, keywords: str, hours: int, runs: int = 2) -> str:
    """搜索单个分类，支持多次运行取并集"""
    print(f"  第1次搜索...")
    result_a = search_once(client, title, keywords, hours)

    if runs == 1:
        return result_a

    time.sleep(2)
    print(f"  第2次搜索...")
    result_b = search_once(client, title, keywords, hours)

    time.sleep(1)
    print(f"  合并去重...")
    return merge_and_dedup(client, title, result_a, result_b)


def translate_to_chinese(client: Client, content: str) -> str:
    """将英文内容翻译成中文，保持格式不变"""
    if not content or "[暂无]" in content or "[搜索失败" in content:
        return content

    chat = client.chat.create(model=MODEL, tools=[])
    chat.append(user(f"""
请将以下内容中的英文部分翻译成中文，保持原有格式完全不变。

翻译规则：
- 只翻译 **...** 中的内容摘要部分
- 保留所有 emoji、@用户名、URL、数字
- 已经是中文的内容保持不变
- 不要添加任何额外文字或解释

格式必须严格保持（每个字段单独一行，条目之间空一行）：
• **内容摘要**
👤 @用户名
🔗 链接
⭐ 热度

原文：
{content}
"""))
    try:
        response = chat.sample()
        return response.content.strip()
    except Exception as e:
        print(f"  ⚠️ 翻译失败，使用原文: {e}")
        return content


# ──────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────
def generate_report(
    hours: int = 24,
    runs: int = None,
    categories: list = None,
    save: bool = True,
    push_lark: bool = True,
    translate: bool = True,
) -> str:
    """
    生成 AI 热点日报

    参数：
        hours:      搜索最近多少小时，默认24
        runs:       每个分类搜索几次，默认从配置文件读取
        categories: 自定义分类列表，不传则使用默认7个分类
        save:       是否保存到本地文件，默认True
        push_lark:  是否推送到 Lark，默认True
        translate:  是否将英文翻译成中文，默认True
    """
    client = _create_client()
    active_categories = categories or CATEGORIES
    active_runs = runs if runs is not None else SEARCH_RUNS
    results = {}

    print(f"\n🔍 开始搜索（最近 {hours} 小时，每类搜索 {active_runs} 次）")
    print(f"共 {len(active_categories)} 个分类，预计耗时 {len(active_categories) * active_runs * 20 // 60 + 1} 分钟\n")

    for i, (title, keywords) in enumerate(active_categories, 1):
        print(f"[{i}/{len(active_categories)}] {title}")
        result = search_category(client, title, keywords, hours, active_runs)
        results[title] = result
        print(f"  ✅ 完成\n")

        if i < len(active_categories):
            time.sleep(3)

    # 翻译英文内容
    if translate:
        print("🌐 翻译英文内容...")
        for title, content in results.items():
            if "[暂无]" not in content:
                print(f"  翻译 {title}...")
                results[title] = translate_to_chinese(client, content)
                time.sleep(1)
        print("  ✅ 翻译完成\n")

    # 组装日报
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M")
    report_lines = [
        f"🤖 AI 热点日报",
        f"📅 {now} (UTC+8) | 最近 {hours} 小时\n",
    ]

    empty_count = 0
    for title, content in results.items():
        if "[暂无]" in content:
            empty_count += 1
            continue
        report_lines.append(f"{title}\n")
        report_lines.append(content)
        report_lines.append("\n" + "─" * 30 + "\n")

    if empty_count > 0:
        report_lines.append(f"\nℹ️ {empty_count} 个分类暂无热门推文")

    report = "\n".join(report_lines)

    # 保存文件
    if save:
        OUTPUT_DIR.mkdir(exist_ok=True)
        filename = OUTPUT_DIR / f"ai_report_{datetime.now(TIMEZONE).strftime('%Y%m%d_%H%M')}.md"
        filename.write_text(report, encoding="utf-8")
        print(f"\n💾 日报已保存至：{filename}")

    # 推送到 Lark
    if push_lark:
        send_to_lark(report)

    return report


# ──────────────────────────────────────────
# 定时任务
# ──────────────────────────────────────────
def scheduled_job():
    """定时任务执行的函数"""
    print(f"\n⏰ 定时任务触发: {datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        generate_report(hours=24, save=True, push_lark=True, translate=True)
    except Exception as e:
        print(f"❌ 定时任务执行失败: {e}")


def run_scheduler():
    """启动定时调度器"""
    # 计算 UTC 时间（schedule 库使用本地时间，需要转换）
    # UTC+8 的 08:00 = UTC 的 00:00
    utc_hour = (8 - 8) % 24  # UTC+8 转 UTC
    utc_time = f"{utc_hour:02d}:00"

    schedule.every().day.at(utc_time).do(scheduled_job)

    print(f"🕐 定时任务已启动")
    print(f"   执行时间: 每天 {SCHEDULE_TIME} (UTC+8)")
    print(f"   当前时间: {datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')} (UTC+8)")
    print(f"   按 Ctrl+C 停止\n")

    while True:
        schedule.run_pending()
        time.sleep(60)


# ──────────────────────────────────────────
# 命令行入口
# ──────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="xAI X Search AI 热点日报生成器")
    parser.add_argument("--hours", type=int, default=24, help="搜索最近多少小时（默认24）")
    parser.add_argument("--runs", type=int, default=None, help="每个分类搜索次数（默认从配置文件读取）")
    parser.add_argument("--no-save", action="store_true", help="不保存到本地文件")
    parser.add_argument("--no-lark", action="store_true", help="不推送到 Lark")
    parser.add_argument("--no-translate", action="store_true", help="不翻译英文内容")
    parser.add_argument("--quick", action="store_true", help="快速模式：每类只搜1次")
    parser.add_argument("--schedule", action="store_true", help="启动定时任务模式（每天 UTC+8 08:00 执行）")
    args = parser.parse_args()

    # 定时任务模式
    if args.schedule:
        run_scheduler()
        return

    # 确定 runs 值：命令行 > --quick > 配置文件
    runs = args.runs
    if args.quick:
        runs = 1

    report = generate_report(
        hours=args.hours,
        runs=runs,
        save=not args.no_save,
        push_lark=not args.no_lark,
        translate=not args.no_translate,
    )

    print("\n" + "=" * 60)
    print(report)


if __name__ == "__main__":
    main()
