"""DiskDoctor Scanner — Fast disk traversal with file metadata collection."""

import os, hashlib, time
from pathlib import Path
from collections import defaultdict

# ── File categories ──
CATEGORIES = {
    "图片": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico", ".tiff", ".heic", ".raw"},
    "视频": {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".m4v", ".3gp"},
    "音频": {".mp3", ".wav", ".aac", ".flac", ".ogg", ".wma", ".m4a", ".opus"},
    "文档": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv", ".md", ".json", ".xml"},
    "代码": {".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".rs", ".go", ".html", ".css", ".sql", ".sh"},
    "压缩包": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso"},
    "安装包": {".exe", ".msi", ".dmg", ".apk", ".deb", ".rpm"},
    "其他": set(),
}
def classify(name, ext):
    for cat, exts in CATEGORIES.items():
        if ext.lower() in exts: return cat
    return "其他"

# ── Temp/junk detection ──
TEMP_DIRS = ["temp", "tmp", "cache", "caches", ".cache", "logs"]
TEMP_EXTS = {".tmp", ".temp", ".log", ".bak", ".old", ".dmp", ".cache", ".chk"}
TEMP_PATHS = [r"\\Temp\\", r"\\tmp\\", r"\\cache\\", r"\\AppData\\Local\\Temp", r"\\Windows\\Temp"]
def is_temp(p, ext):
    pl = p.lower().replace("/", "\\")
    if ext.lower() in TEMP_EXTS: return True
    for tp in TEMP_PATHS:
        if tp.lower() in pl: return True
    for part in Path(p).parts:
        if part.lower() in TEMP_DIRS: return True
    return False

# ── Age brackets ──
AGE_BRACKETS = [("Last 7 days", 7*86400), ("1 week — 1 month", 30*86400),
                ("1 — 3 months", 90*86400), ("3 — 6 months", 180*86400),
                ("6 — 12 months", 365*86400), ("Over 1 year", float("inf"))]
def age_bracket(atime):
    age = time.time() - atime
    for n, lim in AGE_BRACKETS:
        if age < lim: return n
    return "Over 1 year"

# ── Hashing ──
def quick_hash(p, mb=1):
    try:
        h = hashlib.md5(); s = min(int(mb*1024*1024), os.path.getsize(p))
        with open(p, "rb") as f: h.update(f.read(s))
        return h.hexdigest()
    except: return None

def full_hash(p):
    try:
        h = hashlib.md5()
        with open(p, "rb") as f:
            for c in iter(lambda: f.read(8192), b""): h.update(c)
        return h.hexdigest()
    except: return None

# ── Perceptual hashing ──
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".heic"}

def phash_fast(p):
    try:
        from PIL import Image; import imagehash
        return str(imagehash.dhash(Image.open(p).convert("L")))
    except: return None

def phash_precise(p):
    try:
        from PIL import Image; import imagehash
        return imagehash.phash(Image.open(p))
    except: return None

def find_near_dupes(files, cb=None):
    """Find visually similar images using perceptual hashing."""
    imgs = [f for f in files if f["ext"] in IMAGE_EXTS and f["size"] > 1024][:10000]  # Max 10K images
    if len(imgs) < 2: return []

    buckets = defaultdict(list)
    for i, f in enumerate(imgs):
        if cb and i % 50 == 0: cb(len(files) + i, f"pHashing {i}/{len(imgs)}")
        h = phash_fast(f["path"])
        if h: buckets[h].append(f)

    groups = []; seen = set()
    import imagehash
    for bf in buckets.values():
        if len(bf) < 2: continue
        phs = {}
        for f in bf:
            try: phs[f["path"]] = phash_precise(f["path"])
            except: pass
        paths = list(phs.keys())
        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                p1, p2 = paths[i], paths[j]
                if (p1, p2) in seen: continue
                seen.add((p1, p2))
                try:
                    if (phs[p1] - phs[p2]) <= 8:
                        f1 = next(x for x in bf if x["path"] == p1)
                        f2 = next(x for x in bf if x["path"] == p2)
                        merged = False
                        for g in groups:
                            if f1 in g["files"] or f2 in g["files"]:
                                if f1 not in g["files"]: g["files"].append(f1)
                                if f2 not in g["files"]: g["files"].append(f2)
                                merged = True; break
                        if not merged: groups.append({"files": [f1, f2], "distance": phs[p1] - phs[p2]})
                except: pass

    result = []; sp = set()
    for g in groups:
        ps = []; [ps.append(f["path"]) for f in g["files"] if f["path"] not in sp and not sp.add(f["path"])]
        if len(ps) >= 2: result.append({"files": ps, "distance": g["distance"], "wasted": sum(f.get("size", 0) for f in g["files"][1:])})
    return result


# ── Main scan ──
def scan_folder(root_path, progress_callback=None):
    """Full disk scan: files, duplicates, near-dupes, cold, large, junk, age."""
    root = Path(root_path).resolve()
    files = []; total_size = 0
    by_category = defaultdict(lambda: {"count": 0, "size": 0})

    # Phase 1: Walk files
    max_depth = 8
    for dirpath, dirnames, filenames in os.walk(root):
        depth = len(Path(dirpath).relative_to(root).parts) if str(dirpath) != str(root) else 0
        if depth > max_depth: dirnames.clear(); continue
        dirnames[:] = [d for d in dirnames if not d.startswith(".")
                       and d not in ("$RECYCLE.BIN", "System Volume Information", "node_modules", "__pycache__")]

        for fname in filenames:
            try:
                fp = os.path.join(dirpath, fname); stat = os.stat(fp)
                ext = os.path.splitext(fname)[1]; category = classify(fname, ext)
                files.append({"path": fp, "name": fname, "ext": ext.lower(), "size": stat.st_size,
                              "category": category, "mtime": stat.st_mtime,
                              "atime": stat.st_atime, "ctime": stat.st_ctime})
                total_size += stat.st_size
                by_category[category]["count"] += 1; by_category[category]["size"] += stat.st_size
            except (OSError, PermissionError): continue
            if progress_callback and len(files) % 500 == 0:
                progress_callback(len(files), "scanning")
        

    if progress_callback: progress_callback(len(files), "analyzing duplicates...")

    # Phase 2: Exact duplicates (limit to 50K files for speed)
    dup_files = files[:50000]
    size_map = defaultdict(list)
    for f in dup_files:
        if 0 < f["size"] < 500 * 1024 * 1024: size_map[f["size"]].append(f)

    duplicate_groups = []
    dup_checked = 0
    total_grps = len(size_map)
    for sz, group in size_map.items():
        dup_checked += 1
        if progress_callback and dup_checked % 50 == 0:
            progress_callback(len(files) + dup_checked, f"dedup {dup_checked}/{total_grps}")
        if len(group) < 2: continue
        hash_map = defaultdict(list)
        for f in group[:200]:  # Max 200 files per size bucket
            h = quick_hash(f["path"])
            if h: hash_map[h].append(f)
        for h, subgroup in hash_map.items():
            if len(subgroup) < 2: continue
            full_map = defaultdict(list)
            for f in subgroup[:50]:  # Max 50 per hash bucket
                fh = full_hash(f["path"])
                if fh: full_map[fh].append(f)
            for fh, dupes in full_map.items():
                if len(dupes) >= 2:
                    duplicate_groups.append({"hash": fh, "size": dupes[0]["size"],
                        "files": [d["path"] for d in dupes],
                        "wasted": dupes[0]["size"] * (len(dupes) - 1)})

    # Phase 3: Cold, large, temp, age
    six_months = time.time() - 180 * 86400
    cold_files = [f for f in files if f["atime"] < six_months and f["size"] > 1024 * 1024]
    cold_files.sort(key=lambda f: f["atime"])
    large_files = [f for f in files if f["size"] > 100 * 1024 * 1024]
    large_files.sort(key=lambda f: -f["size"])
    temp_files = [f for f in files if is_temp(f["path"], f["ext"])]
    temp_size = sum(f["size"] for f in temp_files)

    by_age = defaultdict(lambda: {"count": 0, "size": 0})
    for f in files:
        bracket = age_bracket(f["atime"])
        by_age[bracket]["count"] += 1; by_age[bracket]["size"] += f["size"]

    # Phase 4: Near duplicates (perceptual)
    if progress_callback: progress_callback(len(files), "near-duplicate detection...")
    near_dupes = find_near_dupes(files, progress_callback)

    wasted_space = sum(d["wasted"] for d in duplicate_groups)

    return {
        "root": str(root),
        "files": files,
        "total_files": len(files),
        "total_size": total_size,
        "by_category": {k: dict(v) for k, v in by_category.items()},
        "duplicates": duplicate_groups,
        "duplicate_count": len(duplicate_groups),
        "wasted_space": wasted_space,
        "cold_files": cold_files[:200],
        "cold_count": len(cold_files),
        "large_files": large_files[:100],
        "large_count": len(large_files),
        "temp_files": temp_files[:100],
        "temp_count": len(temp_files),
        "temp_size": temp_size,
        "by_age": {k: dict(v) for k, v in by_age.items()},
        "near_duplicates": near_dupes,
        "near_duplicate_count": len(near_dupes),
        "near_wasted_space": sum(d.get("wasted", 0) for d in near_dupes),
    }
