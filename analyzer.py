"""DiskDoctor Analyzer — Generate human-readable insights from scan data."""

import os, time
from datetime import datetime


def format_size(size):
    """Format bytes to human readable."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def format_date(ts):
    """Format timestamp to readable date."""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def generate_insights(scan_result):
    """Generate human-readable findings and suggestions."""
    findings = []
    stats = []

    # ── Summary ──
    total_gb = scan_result["total_size"] / (1024 ** 3)
    stats.append(f"📊 共扫描 {scan_result['total_files']:,} 个文件，总大小 {format_size(scan_result['total_size'])}")

    # ── Category breakdown ──
    cats = scan_result["by_category"]
    top_cats = sorted(cats.items(), key=lambda x: -x[1]["size"])[:5]
    cat_lines = []
    for name, data in top_cats:
        cat_lines.append(f"  {name}: {data['count']:,} 个文件，占 {format_size(data['size'])}")
    if cat_lines:
        findings.append({"icon": "📂", "title": "文件类型分布",
                         "detail": "\n".join(cat_lines), "severity": "info"})

    # ── Duplicates ──
    if scan_result["duplicate_count"] > 0:
        wasted = scan_result["wasted_space"]
        findings.append({
            "icon": "🔄", "title": f"发现 {scan_result['duplicate_count']} 组重复文件",
            "detail": f"浪费空间: {format_size(wasted)}\n"
                      f"删除重复文件可以立即释放 {format_size(wasted)} 空间。",
            "severity": "warning" if wasted > 500 * 1024 * 1024 else "info",
        })

    # ── Cold files ──
    cold = scan_result["cold_files"]
    if cold:
        cold_size = sum(f["size"] for f in cold)
        cold_top = cold[:5]
        detail = f"{len(cold)} 个文件超过半年未访问，共占 {format_size(cold_size)}\n"
        detail += "最早的几个：\n"
        for f in cold_top:
            detail += f"  · {os.path.basename(f['path'])} — 最后访问 {format_date(f['atime'])}\n"
        findings.append({
            "icon": "❄️", "title": f"{len(cold)} 个冷文件（半年未用）",
            "detail": detail,
            "severity": "warning" if cold_size > 500 * 1024 * 1024 else "info",
        })

    # ── Large files ──
    large = scan_result["large_files"]
    if large:
        large_size = sum(f["size"] for f in large)
        detail = f"{len(large)} 个超大文件（>100MB），共占 {format_size(large_size)}\n"
        detail += "最大的几个：\n"
        for f in large[:5]:
            detail += f"  · {os.path.basename(f['path'])} — {format_size(f['size'])}\n"
        findings.append({
            "icon": "🐘", "title": f"{len(large)} 个超大文件",
            "detail": detail,
            "severity": "info",
        })

    # ── Downloads folder ──
    downloads = [f for f in scan_result.get("files", [])
                 if "downloads" in f["path"].lower()
                 or "下载" in f["path"]]
    if downloads:
        dl_size = sum(f["size"] for f in downloads)
        installers = [f for f in downloads if f["category"] == "安装包"]
        if installers:
            findings.append({
                "icon": "📥", "title": "下载文件夹清理建议",
                "detail": f"下载文件夹共 {len(downloads)} 个文件 ({format_size(dl_size)})\n"
                          f"其中 {len(installers)} 个是安装包，装完就可以删。",
                "severity": "tip",
            })

    # ── Actionable summary ──
    actionable = []
    if scan_result["wasted_space"] > 0:
        actionable.append(f"🗑️ 删除重复文件 → 释放 {format_size(scan_result['wasted_space'])}")
    if cold:
        actionable.append(f"📦 清理冷文件 → 可能释放 {format_size(sum(f['size'] for f in cold))}")
    if large:
        actionable.append(f"📂 检查 {len(large)} 个大文件 → 看哪些不需要")

    return {
        "summary": stats,
        "findings": findings,
        "actionable": actionable,
        "health_score": _calc_health(scan_result),
    }


def _calc_health(scan_result):
    """Calculate disk health score (0-100)."""
    score = 100
    total = scan_result["total_size"]
    if total == 0:
        return 100

    # Duplicates penalty
    dup_pct = scan_result["wasted_space"] / total
    score -= min(30, int(dup_pct * 100))

    # Cold files penalty
    cold_size = sum(f["size"] for f in scan_result["cold_files"])
    cold_pct = cold_size / total
    score -= min(20, int(cold_pct * 50))

    # Too many large files
    large = scan_result["large_files"]
    if len(large) > 20:
        score -= 10

    return max(0, min(100, score))
