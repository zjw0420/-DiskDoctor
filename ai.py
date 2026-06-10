"""DiskDoctor AI — Optional AI-powered suggestions (local + online dual mode)."""

import json

# ── Local rule-based suggestions (no dependency) ──

def local_suggestions(scan_result):
    """Generate suggestions using local rule engine. No network needed."""
    tips = []
    total = scan_result["total_size"]

    if scan_result["duplicate_count"] > 0:
        wasted = scan_result["wasted_space"]
        tips.append(f"发现 {scan_result['duplicate_count']} 组重复文件，浪费了约 {_fmt(wasted)} 空间。"
                    f"建议：在结果页勾选重复文件并一键删除。")

    cold = scan_result["cold_files"]
    if len(cold) > 10:
        cold_size = sum(f["size"] for f in cold)
        tips.append(f"有 {len(cold)} 个文件超过半年没动过，占 {_fmt(cold_size)}。"
                    f"建议：按「最后访问时间」排序，删除不再需要的旧文件。")

    large = scan_result["large_files"]
    if large:
        tips.append(f"有 {len(large)} 个文件超过 100MB。建议逐个检查是否还需要。")

    cats = scan_result["by_category"]
    total_gb = total / (1024 ** 3)
    if total_gb > 100:
        max_cat = max(cats.items(), key=lambda x: x[1]["size"])
        tips.append(f"磁盘使用率较高（{total_gb:.0f}GB），最大占用是「{max_cat[0]}」类型。")

    return tips


def _fmt(size):
    for u in ["B", "KB", "MB", "GB"]:
        if size < 1024: return f"{size:.1f}{u}"
        size /= 1024
    return f"{size:.1f}GB"


# ── Online AI suggestions (DeepSeek / OpenAI compatible) ──

def online_suggestions(scan_result, api_key="", provider="deepseek"):
    """Send scan summary to AI for smarter suggestions."""
    summary = _build_summary(scan_result)
    prompt = f"""你是磁盘清理专家。分析以下磁盘扫描结果，给出 3-5 条具体可操作的清理建议。
每条建议说明问题和解决办法。用中文回答，每条建议不超过80字。

扫描结果：
{summary}

请直接列出建议，不要客套话。"""

    try:
        if provider == "deepseek":
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
            model = "deepseek-chat"
        elif provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            model = "gpt-4o-mini"
        elif provider == "ollama":
            import urllib.request
            data = json.dumps({"model": "qwen2.5:3b", "prompt": prompt, "stream": False}).encode()
            req = urllib.request.Request("http://localhost:11434/api/generate", data=data,
                                         headers={"Content-Type": "application/json"})
            resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
            return [resp.get("response", "").strip()]
        else:
            return local_suggestions(scan_result)

        resp = client.chat.completions.create(
            model=model, max_tokens=800, temperature=0.7,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.choices[0].message.content
        # Split into individual tips
        lines = [l.strip(" -·0123456789.、") for l in text.split("\n") if l.strip()]
        return [l for l in lines if len(l) > 10][:5]

    except Exception as e:
        return [f"AI 建议暂时不可用（{str(e)[:50]}），已切换到本地规则引擎。"] + local_suggestions(scan_result)


def _build_summary(scan_result):
    """Build a text summary of scan results for AI prompt."""
    cats = scan_result["by_category"]
    lines = [
        f"总文件数: {scan_result['total_files']:,}",
        f"总大小: {_fmt(scan_result['total_size'])}",
        f"重复文件: {scan_result['duplicate_count']}组, 浪费{_fmt(scan_result['wasted_space'])}",
        f"冷文件(半年未访问): {len(scan_result['cold_files'])}个",
        f"大文件(>100MB): {len(scan_result['large_files'])}个",
        "类型分布:",
    ]
    for name, data in sorted(cats.items(), key=lambda x: -x[1]["size"]):
        lines.append(f"  {name}: {data['count']}个, {_fmt(data['size'])}")
    return "\n".join(lines)
