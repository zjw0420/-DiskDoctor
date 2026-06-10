"""DiskDoctor — Friendly disk space analyzer. Powered by ScanEngine v2."""

import sys, os, json, threading, time, shutil
from pathlib import Path
from datetime import datetime
from uuid import uuid4

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QTreeWidget, QTreeWidgetItem,
    QTabWidget, QTextEdit, QFileDialog, QCheckBox, QComboBox,
    QLineEdit, QGroupBox, QHeaderView, QMessageBox, QMenu, QScrollArea, QButtonGroup
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor, QPainter, QBrush, QPen, QPixmap

from engine import ScanEngine
from analyzer import generate_insights, format_size, format_date
from ai import local_suggestions, online_suggestions

PROJ = Path(__file__).parent
SETTINGS = PROJ / "settings.json"
EMOJI_FILE = PROJ / "emojis.json"
BACKUP_DIR = PROJ / "backup"; BACKUP_DIR.mkdir(exist_ok=True)
DEL_LOG = PROJ / "deletions.json"

# ── i18n ──
T = {
    "en": {
        "title": "DiskDoctor", "scan": "Scan", "stop": "Stop", "open": "Open...",
        "export": "Export...", "settings": "Settings", "lang": "中文",
        "welcome": "Select a folder and click Scan to analyze.",
        "scanning": "Scanning...", "files_found": "files found",
        "overview": "Overview", "file_types": "File Types", "duplicates": "Duplicates",
        "cold_files": "Cold Files", "large_files": "Large Files",
        "junk": "Junk", "age": "Age", "snapshot": "Snapshot",
        "ai_tips": "AI Tips", "restore": "Restore",
        "health": "Disk Health", "total": "Total", "tip": "Tip",
        "chart": "Chart:", "emoji_style": "Emoji:",
        "treemap": "Treemap", "donut": "Donut", "bars": "Bars",
        "cat": "Cat", "yellow": "Yellow", "classic": "Classic",
        "del_sel": "Delete selected", "del_dup": "Delete checked duplicates",
        "del_junk": "Delete all junk (safe)",
        "restore_btn": "Restore selected files",
        "save_snap": "Save current scan as snapshot",
        "compare": "Compare with selected",
        "no_dups": "No duplicates found.",
        "no_junk": "No junk files found.",
        "near_dupes": "Near-Dupes", "near_dupes_desc": "{n} groups of visually similar images found.",
        "no_near_dupes": "No visually similar images found.",
        "last_7": "Last 7 days", "week_month": "1 week - 1 month",
        "1_3_months": "1 - 3 months", "3_6_months": "3 - 6 months",
        "6_12_months": "6 - 12 months", "over_1yr": "Over 1 year",
        "safe_no": "No", "safe_maybe": "Maybe", "safe_mostly": "Mostly safe",
        "safe_safe": "Safe", "safe_very": "Very safe",
        "del_nd": "Delete selected (keeps best copy)",
    },
    "zh": {
        "title": "DiskDoctor — 磁盘小医生", "scan": "开始扫描", "stop": "停止",
        "open": "打开文件夹...", "export": "导出报告...", "settings": "设置",
        "lang": "English", "welcome": "选个文件夹，点「开始扫描」来分析磁盘。",
        "scanning": "扫描中...", "files_found": "个文件",
        "overview": "概览", "file_types": "文件分类", "duplicates": "重复文件",
        "cold_files": "冷文件", "large_files": "大文件",
        "junk": "垃圾文件", "age": "文件年龄", "snapshot": "快照对比",
        "ai_tips": "AI 建议", "restore": "恢复文件",
        "health": "磁盘健康", "total": "总大小", "tip": "建议",
        "chart": "图表:", "emoji_style": "表情:",
        "treemap": "方块图", "donut": "甜甜圈", "bars": "柱状图",
        "cat": "小猫", "yellow": "小黄人", "classic": "经典",
        "del_sel": "删除选中", "del_dup": "删除勾选的重复文件",
        "del_junk": "一键清除垃圾（安全）",
        "restore_btn": "恢复选中的文件",
        "save_snap": "保存当前快照",
        "compare": "对比选中快照",
        "no_dups": "未发现重复文件。",
        "no_junk": "未发现垃圾文件。",
        "near_dupes": "近似重复", "near_dupes_desc": "找到 {n} 组视觉相似但非完全相同的图片。",
        "no_near_dupes": "未发现近似重复的图片。",
        "last_7": "最近7天", "week_month": "1周 — 1个月",
        "1_3_months": "1 — 3个月", "3_6_months": "3 — 6个月",
        "6_12_months": "6 — 12个月", "over_1yr": "超过1年",
        "safe_no": "不能删", "safe_maybe": "再看看", "safe_mostly": "基本安全",
        "safe_safe": "可以删", "safe_very": "非常安全",
        "del_nd": "删除选中（保留最佳副本）",
    }
}

def load_settings():
    if SETTINGS.exists():
        try: return json.loads(SETTINGS.read_text(encoding='utf-8'))
        except: SETTINGS.unlink(missing_ok=True)
    return {"ai_mode":"local","api_key":"","provider":"deepseek","lang":"zh","emoji_style":"cat",
            "ignore":["node_modules","__pycache__",".git","$RECYCLE.BIN"]}
def save_settings(s): SETTINGS.write_text(json.dumps(s, indent=2, ensure_ascii=False))

# ── Emoji engine ──
CAT_PACK = {"huge":"😿","very_big":"😿","big":"😸","medium_big":"😺","medium":"😻","small_big":"😸","small":"😺","tiny":"🐱","micro":"🐱"}
YELLOW_PACK = {"huge":"🤯","very_big":"😱","big":"😫","medium_big":"😰","medium":"😬","small_big":"🤔","small":"😊","tiny":"🙂","micro":"😍"}
CLASSIC_PACK = {"huge":"💥","very_big":"💣","big":"📦","medium_big":"📥","medium":"📁","small_big":"📄","small":"📃","tiny":"📎","micro":"✨"}
EMOJI_PACKS = {"cat": CAT_PACK, "yellow": YELLOW_PACK, "classic": CLASSIC_PACK}
CUSTOM_EMOJI_DIR = PROJ / "custom_emoji"; CUSTOM_EMOJI_DIR.mkdir(exist_ok=True)

def load_custom_pack():
    pack = {}
    for name in ["huge","very_big","big","medium","small","tiny"]:
        path = CUSTOM_EMOJI_DIR / f"{name}.png"
        if path.exists(): pack[name] = str(path)
    if len(pack) >= 3: EMOJI_PACKS["custom"] = pack; return True
    return False
load_custom_pack()

def create_custom_pack(image_path):
    from PIL import Image
    sizes = {"huge":48,"very_big":40,"big":32,"medium_big":28,"medium":24,"small_big":20,"small":16,"tiny":12,"micro":8}
    img = Image.open(image_path).convert("RGBA")
    for name, px in sizes.items():
        img.resize((px,px), Image.LANCZOS).save(CUSTOM_EMOJI_DIR / f"{name}.png")
    EMOJI_PACKS["custom"] = {name: str(CUSTOM_EMOJI_DIR / f"{name}.png") for name in sizes}

def size_mood(size, pack):
    if not pack: pack = CAT_PACK
    if size > 1024**4: v = pack.get("huge")
    elif size > 500*1024**3: v = pack.get("very_big")
    elif size > 100*1024**3: v = pack.get("big")
    elif size > 10*1024**3: v = pack.get("medium_big")
    elif size > 1024**3: v = pack.get("medium")
    elif size > 500*1024**2: v = pack.get("small_big")
    elif size > 100*1024**2: v = pack.get("small")
    elif size > 10*1024**2: v = pack.get("tiny")
    else: v = pack.get("micro")
    return v if v else pack.get("small","?")

def health_face(score):
    if score > 80: return "😎"
    if score > 60: return "🙂"
    if score > 40: return "🤔"
    if score > 20: return "😟"
    return "💀"

CAT_ICONS = {"图片":"🖼","视频":"🎬","音频":"🎵","文档":"📄","代码":"💻","压缩包":"📦","安装包":"📥","其他":"📁"}

# System protection
SYS_PATHS = [r"C:\\Windows", r"\\Program Files", r"\\Program Files (x86)", r"System32", r"SysWOW64", r"$RECYCLE.BIN"]
def is_system(p): return any(pat.lower() in p.lower() for pat in SYS_PATHS)

# ── Backup/delete ──
def load_dels():
    if DEL_LOG.exists():
        try: return json.loads(DEL_LOG.read_text(encoding='utf-8'))
        except: return []
    return []
def save_del(r): records = load_dels(); records.append(r); DEL_LOG.write_text(json.dumps(records, indent=2, ensure_ascii=False))
def safe_del(paths):
    ok, fail = 0, 0
    for src in paths:
        try:
            if not os.path.exists(src): fail += 1; continue
            rid = datetime.now().strftime("%Y%m%d_%H%M%S_") + str(uuid4())[:8]
            dst = BACKUP_DIR / (rid + "_" + Path(src).name)
            shutil.move(src, str(dst))
            try: save_del({"original": src, "backup": str(dst), "time": datetime.now().isoformat(), "restored": False})
            except: pass
            ok += 1
        except: fail += 1
    return ok, fail
def restore_files(recs):
    restored = 0
    for r in recs:
        try:
            os.makedirs(os.path.dirname(r["original"]), exist_ok=True)
            shutil.move(r["backup"], r["original"]); restored += 1
        except: pass
    return restored
def confirm_del(parent, paths, lang="zh"):
    if not paths: return False
    total = sum(os.path.getsize(p) for p in paths if os.path.exists(p))
    sys_files = [p for p in paths if is_system(p)]
    is_en = lang == "en"
    c1 = f"Delete {len(paths)} files ({format_size(total)})?\nFiles go to backup, can be restored." if is_en else f"确认删除 {len(paths)} 个文件（{format_size(total)}）？\n文件将移到备份，可以恢复。"
    if QMessageBox.question(parent, "Confirm" if is_en else "确认删除", c1) != QMessageBox.Yes: return False
    if sys_files:
        msg = "❗❗❗ SYSTEM FILE WARNING ❗❗❗\n\n" if is_en else "❗❗❗ 系统文件警告 ❗❗❗\n\n"
        msg += "\n".join(f"  · {Path(f).name}" for f in sys_files[:5])
        msg += "\n\n" + ("These are in system directories. Deleting may break software.\nAbsolutely sure?" if is_en else "\n这些文件在系统目录中。删除可能导致软件故障。\n确定要删除吗？")
        if QMessageBox.warning(parent, "❗ System Files" if is_en else "❗ 系统文件", msg, QMessageBox.Yes|QMessageBox.No, QMessageBox.No) != QMessageBox.Yes: return False
    if total > 10*1024**3:
        c3 = f"Really delete {format_size(total)}?" if is_en else f"确定要删除 {format_size(total)} 吗？这是最后确认。"
        if QMessageBox.question(parent, "Final Check" if is_en else "最后确认", c3) != QMessageBox.Yes: return False
    return True

# ── Scan Worker (uses ScanEngine v2) ──
class ScanWorker(QThread):
    progress = Signal(object)   # engine.Progress
    finished = Signal(object)   # result dict
    error = Signal(str)

    def __init__(self, folder):
        super().__init__()
        self.folder = folder
        self._engine = None

    def run(self):
        self._engine = ScanEngine(walk_workers=4, hash_workers=2)
        self._engine.on_progress = lambda p: self.progress.emit(p)
        try:
            result = self._engine.scan(self.folder)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))

    def cancel(self):
        if self._engine:
            self._engine.cancel()


# ── Visualization Widgets ──
class CushionTreemap(QWidget):
    COLORS = [QColor("#4a90d9"),QColor("#50b86c"),QColor("#e8a838"),QColor("#d94a4a"),QColor("#8b5cf6"),QColor("#e05a9e"),QColor("#36b8b8"),QColor("#d97a2c")]
    def __init__(self, parent=None): super().__init__(parent); self.items=[]; self.pack=CAT_PACK; self.setMinimumHeight(200)
    def set_data(self, categories, pack=None):
        if pack: self.pack = pack
        self.items = [(k,v["size"]) for k,v in categories.items() if v["size"]>0]; self.items.sort(key=lambda x:-x[1]); self.update()
    def paintEvent(self, e):
        if not self.items: return
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing); w,h=self.width(),self.height()
        if w<=0 or h<=0: return
        total=sum(s for _,s in self.items); x,y=0.0,0.0
        for i,(name,size) in enumerate(self.items):
            ratio=size/total; rw=w*ratio if w>h*1.4 else w; rh=h if w>h*1.4 else h*ratio; r=(x,y,rw,rh)
            if w>h*1.4: x+=rw
            else: y+=rh
            c=self.COLORS[i%len(self.COLORS)]; p.setPen(QPen(c.darker(120),1)); p.setBrush(QBrush(c))
            rx,ry,rw,rh=int(r[0]),int(r[1]),int(r[2]),int(r[3]); p.drawRect(rx,ry,rw,rh)
            p.setPen(Qt.NoPen); p.setBrush(QBrush(QColor(255,255,255,30))); p.drawRect(rx,ry,rw,rh//2)
            p.setBrush(QBrush(QColor(0,0,0,20))); p.drawRect(rx,ry+rh//2,rw,rh-rh//2)
            if rw>30 and rh>14:
                p.setPen(QPen(QColor("#fff"))); mood=size_mood(size,self.pack); cat=CAT_ICONS.get(name,"")
                fs=14 if rw>120 and rh>60 else 11 if rw>80 and rh>40 else 8
                is_img=mood and os.path.exists(str(mood))
                if is_img and rw>60 and rh>50:
                    pix=QPixmap(str(mood)); p.drawPixmap(rx+4,ry+4,min(24,rw-8),min(24,rh-8),pix)
                    p.setFont(QFont("Segoe UI",fs,QFont.Bold)); p.drawText(rx+30,ry+4,rw-34,rh-24,Qt.AlignLeft|Qt.AlignTop|Qt.TextWordWrap,f"{cat} {name}")
                else:
                    p.setFont(QFont("Segoe UI",fs,QFont.Bold)); p.drawText(rx+4,ry+4,rw-8,rh-24,Qt.AlignLeft|Qt.AlignTop|Qt.TextWordWrap,f"{mood} {cat} {name}")
                p.setFont(QFont("Segoe UI",max(8,fs-2))); p.drawText(rx+4,ry+rh-22,rw-8,18,Qt.AlignLeft|Qt.AlignBottom,format_size(size))

class DonutChart(QWidget):
    C=[QColor("#4a90d9"),QColor("#50b86c"),QColor("#e8a838"),QColor("#d94a4a"),QColor("#8b5cf6"),QColor("#e05a9e"),QColor("#36b8b8"),QColor("#d97a2c")]
    def __init__(self,parent=None): super().__init__(parent); self.items=[]; self.setMinimumHeight(200)
    def set_data(self,categories): self.items=[(k,v["size"]) for k,v in categories.items() if v["size"]>0]; self.items.sort(key=lambda x:-x[1]); self.update()
    def paintEvent(self,e):
        if not self.items: return
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing); w,h=self.width(),self.height(); cx,cy=w//2,h//2; r=min(w,h)//2-40; inner=r*0.55
        total=sum(s for _,s in self.items); angle=0.0
        for i,(name,size) in enumerate(self.items):
            span=(size/total)*360*16; c=self.C[i%len(self.C)]; p.setBrush(QBrush(c)); p.setPen(QPen(Qt.white,2))
            p.drawPie(int(cx-r),int(cy-r),int(r*2),int(r*2),int(angle),int(span)); angle+=span
        p.setBrush(QBrush(Qt.white)); p.setPen(Qt.NoPen); p.drawEllipse(int(cx-inner),int(cy-inner),int(inner*2),int(inner*2))
        p.setPen(QPen(QColor("#333"))); p.setFont(QFont("Segoe UI",10,QFont.Bold)); p.drawText(int(cx-inner),int(cy-12),int(inner*2),24,Qt.AlignCenter,format_size(total))
        p.setFont(QFont("Segoe UI",8)); p.drawText(int(cx-inner),int(cy+8),int(inner*2),16,Qt.AlignCenter,"Total")
        # Legend
        lx,ly=10,10
        for i,(name,size) in enumerate(self.items):
            if ly>h-20: break
            c=self.C[i%len(self.C)]; p.setBrush(QBrush(c)); p.setPen(Qt.NoPen); p.drawRect(lx,ly,12,12)
            p.setPen(QPen(QColor("#333"))); p.setFont(QFont("Segoe UI",8))
            p.drawText(lx+16,ly+10,f"{CAT_ICONS.get(name,'')} {name}  {format_size(size)}  ({size/total*100:.1f}%)"); ly+=18

class BarChart(QWidget):
    C=DonutChart.C
    def __init__(self,parent=None): super().__init__(parent); self.items=[]; self.setMinimumHeight(200)
    def set_data(self,categories): self.items=[(k,v["size"]) for k,v in categories.items() if v["size"]>0]; self.items.sort(key=lambda x:x[1]); self.update()
    def paintEvent(self,e):
        if not self.items: return
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing); w,h=self.width(),self.height()
        total=max(s for _,s in self.items); ml,mr,mt,mb=100,20,20,30; cw,ch=w-ml-mr,h-mt-mb
        bh=min(40,(ch-len(self.items)*8)/len(self.items)); y=mt
        for i,(name,size) in enumerate(self.items):
            bw=(size/total)*cw; c=self.C[i%len(self.C)]; p.setBrush(QBrush(c)); p.setPen(Qt.NoPen)
            p.drawRoundedRect(int(ml),int(y),int(bw),int(bh),4,4)
            p.setPen(QPen(QColor("#333"))); p.setFont(QFont("Segoe UI",9))
            p.drawText(4,int(y),ml-8,int(bh),Qt.AlignRight|Qt.AlignVCenter,f"{CAT_ICONS.get(name,'')} {name}")
            p.setPen(QPen(QColor("#fff"))); p.drawText(int(ml)+8,int(y),int(bw)-16,int(bh),Qt.AlignLeft|Qt.AlignVCenter,f"{format_size(size)}  ({size/total*100:.0f}%)")
            y+=bh+8

# ── Tips ──
def friendly_tips(r):
    tips=[]; total_gb=r["total_size"]/(1024**3)
    if total_gb>100: tips.append(f"😱 磁盘用了 {total_gb:.0f}GB，有点满了。不过别慌，一步步来。")
    elif total_gb>50: tips.append(f"🤔 磁盘用了 {total_gb:.0f}GB，还算正常，趁现在清理一下。")
    if r["duplicate_count"]>0: tips.append(f"📦 发现 {r['duplicate_count']} 组重复文件，浪费 {format_size(r['wasted_space'])}。去「重复文件」页勾选删除（会保留一份原件）。")
    cold=r.get("cold_files",[])
    if len(cold)>5: tips.append(f"📁 {len(cold)} 个文件半年没打开过，占 {format_size(sum(f['size'] for f in cold))}。去「冷文件」页看看。")
    large=r.get("large_files",[])
    if large: tips.append(f"💣 {len(large)} 个大文件（>100MB），去「大文件」页逐个检查。")
    if r.get("temp_count",0)>0: tips.append(f"🗑️ {r['temp_count']} 个临时/缓存文件可以安全删除。去「垃圾文件」页一键清理。")
    if not tips: tips.append("😍 磁盘很健康！没什么需要清理的。")
    return tips

# ── Main Window ──
class DiskDoctor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings=load_settings(); self.lang=self.settings.get("lang","zh"); self.emoji_style=self.settings.get("emoji_style","cat")
        self.pack=EMOJI_PACKS.get(self.emoji_style, CAT_PACK)
        self.scan_result=None; self.folder=None
        self.setWindowTitle(self.t("title")); self.setMinimumSize(1200,780)
        has_theme = False
        try:
            from qt_material import apply_stylesheet, list_themes
            has_theme = True
        except ImportError:
            pass
        if not has_theme:
            self.setStyleSheet("""
                QMainWindow{background:#f0f2f5} *{font-family:"Segoe UI","Microsoft YaHei",sans-serif;font-size:13px;color:#1a1a2e}
                QPushButton{background:#fff;color:#333;border:1px solid #e0e0e0;border-radius:8px;padding:8px 18px}
                QPushButton:hover{background:#f5f7fa;border-color:#667eea}
                QPushButton.primary{background:#667eea;color:#fff;border:none;padding:9px 22px;font-weight:600;border-radius:10px}
                QPushButton.danger{background:#fff;color:#e74c3c;border:2px solid #e74c3c}
                QPushButton.danger:hover{background:#e74c3c;color:#fff}
                QTreeWidget{background:#fff;border:1px solid #e8ecf1;border-radius:10px;alternate-background-color:#fafbfc;color:#333;outline:none}
                QTreeWidget::item:hover{background:#eef1ff} QTreeWidget::item:selected{background:#667eea;color:#fff}
                QHeaderView::section{background:#f8f9fc;border:none;border-bottom:2px solid #e8ecf1;padding:10px 8px;font-weight:700;color:#555}
                QProgressBar{border:none;border-radius:6px;background:#e8ecf1;height:8px}
                QProgressBar::chunk{background:#667eea;border-radius:6px}
                QTabWidget::pane{border:1px solid #e8ecf1;border-radius:0 10px 10px 10px;background:#fff}
                QTabBar::tab{background:#f0f2f5;color:#888;padding:8px 18px;border:1px solid #e8ecf1;border-bottom:none;border-radius:8px 8px 0 0;margin-right:3px}
                QTabBar::tab:selected{background:#fff;color:#667eea;font-weight:700}
                QComboBox,QLineEdit{background:#fff;color:#333;border:1px solid #e0e0e0;border-radius:8px;padding:7px 12px}
                QGroupBox{border:1px solid #e8ecf1;border-radius:10px;margin-top:12px;padding:20px 12px 12px 12px;color:#555}
                QGroupBox::title{subcontrol-origin:margin;left:16px;color:#667eea}
                QCheckBox{color:#333} QTextEdit{background:#fff;border:1px solid #e0e0e0;border-radius:8px;color:#333;padding:8px}
                QMenu{background:#fff;border:1px solid #e8ecf1;border-radius:10px;padding:4px} QMenu::item{padding:8px 32px}
                QMenu::item:selected{background:#eef1ff}
                QScrollBar:vertical{width:10px} QScrollBar::handle:vertical{background:#c8ccd4;border-radius:5px}
            """)
        self._ui()

    def t(self, key): return T.get(self.lang,{}).get(key, key)

    def _ui(self):
        cw=QWidget(); self.setCentralWidget(cw); ml=QVBoxLayout(cw); ml.setContentsMargins(16,12,16,12); ml.setSpacing(8)

        # Toolbar
        tb=QHBoxLayout()
        self.path_lbl=QLabel("  "+self.t("welcome")); self.path_lbl.setStyleSheet("background:#fff;border:1px solid #d0d0d0;padding:6px 10px;color:#888;"); self.path_lbl.setMinimumWidth(300)
        btn_open=QPushButton(self.t("open")); btn_open.clicked.connect(self._pick)
        self.btn_scan=QPushButton(self.t("scan")); self.btn_scan.setProperty("class","primary"); self.btn_scan.clicked.connect(self._start); self.btn_scan.setEnabled(False)
        self.btn_stop=QPushButton(self.t("stop")); self.btn_stop.clicked.connect(self._cancel); self.btn_stop.setVisible(False)
        self.btn_export=QPushButton(self.t("export")); self.btn_export.clicked.connect(self._export_rpt); self.btn_export.setVisible(False)
        self.btn_settings=QPushButton(self.t("settings")); self.btn_settings.clicked.connect(self._show_settings)
        self.btn_lang=QPushButton(self.t("lang")); self.btn_lang.clicked.connect(self._toggle_lang)
        tb.addWidget(self.path_lbl); tb.addWidget(btn_open); tb.addWidget(self.btn_scan); tb.addWidget(self.btn_stop)
        tb.addWidget(self.btn_export); tb.addStretch(); tb.addWidget(self.btn_settings); tb.addWidget(self.btn_lang)
        ml.addLayout(tb)

        # Scan progress
        self.scan_area=QWidget(); self.scan_area.setVisible(False); sal=QVBoxLayout(self.scan_area); sal.setContentsMargins(0,4,0,4)
        self.phase_lbl=QLabel(""); self.phase_lbl.setStyleSheet("color:#555;font-size:13px;"); sal.addWidget(self.phase_lbl)
        self.big_bar=QProgressBar(); self.big_bar.setMinimumHeight(22); sal.addWidget(self.big_bar)
        sr=QHBoxLayout(); self.small_bar=QProgressBar(); self.small_bar.setMaximumHeight(3)
        self.count_lbl=QLabel(""); self.count_lbl.setStyleSheet("color:#888;font-size:11px;")
        self.eta_lbl=QLabel(""); self.eta_lbl.setStyleSheet("color:#888;font-size:11px;")
        sr.addWidget(self.small_bar); sr.addWidget(self.count_lbl); sr.addWidget(self.eta_lbl)
        sal.addLayout(sr); ml.addWidget(self.scan_area)

        # Viz switcher
        self.viz_area=QWidget(); self.viz_area.setVisible(False); val=QVBoxLayout(self.viz_area); val.setContentsMargins(0,6,0,0)
        vbl=QHBoxLayout()
        self.viz_label=QLabel(self.t("chart")); vbl.addWidget(self.viz_label)
        self.btn_viz=[]; self.viz_group=QButtonGroup(self); self.viz_group.setExclusive(True)
        for i,n in enumerate([self.t("treemap"),self.t("donut"),self.t("bars")]):
            b=QPushButton(f"  {n}  "); b.setCheckable(True); b.setChecked(i==0); b.setMinimumHeight(32)
            b.setStyleSheet("QPushButton{padding:6px 16px;font-size:13px;font-weight:bold} QPushButton:checked{background:#4a90d9;color:#fff;border-color:#4a90d9}")
            self.viz_group.addButton(b,i); vbl.addWidget(b); self.btn_viz.append(b)
        self.viz_group.buttonClicked.connect(lambda btn: self._viz(self.viz_group.id(btn)))
        vbl.addSpacing(20); self.emo_label=QLabel(self.t("emoji_style")); vbl.addWidget(self.emo_label)
        self.btn_emo=[]; self.emo_group=QButtonGroup(self); self.emo_group.setExclusive(True)
        emo_styles=["cat","yellow","classic"]
        if "custom" in EMOJI_PACKS: emo_styles.append("custom")
        emo_display={"cat":f"🐱 {self.t('cat')}","yellow":f"😊 {self.t('yellow')}","classic":f"💥 {self.t('classic')}","custom":"🖼️ Custom"}
        for i,st in enumerate(emo_styles):
            b=QPushButton(f"  {emo_display.get(st,st)}  "); b.setCheckable(True); b.setChecked(self.emoji_style==st); b.setMinimumHeight(32)
            b.setStyleSheet("QPushButton{padding:6px 12px;font-size:12px} QPushButton:checked{background:#50b86c;color:#fff;border-color:#50b86c}")
            self.emo_group.addButton(b,i); vbl.addWidget(b); self.btn_emo.append(b)
        self.emo_group.buttonClicked.connect(lambda btn: self._chg_emoji(emo_styles[self.emo_group.id(btn)]))
        btn_import=QPushButton("+ Import"); btn_import.setMinimumHeight(32)
        btn_import.setStyleSheet("QPushButton{padding:6px 10px;font-size:11px;border-style:dashed}"); btn_import.clicked.connect(self._import_emoji); vbl.addWidget(btn_import)
        vbl.addStretch(); val.addLayout(vbl)

        self.viz_stack=QWidget(); vsl=QVBoxLayout(self.viz_stack); vsl.setContentsMargins(0,0,0,0)
        self.treemap=CushionTreemap(); self.treemap.setMinimumSize(400,300)
        self.donut=DonutChart(); self.donut.setMinimumSize(400,300)
        self.bars=BarChart(); self.bars.setMinimumSize(400,300)
        vsl.addWidget(self.treemap); vsl.addWidget(self.donut); vsl.addWidget(self.bars)
        vsl.addStretch()
        self.donut.setVisible(False); self.bars.setVisible(False)
        scroll=QScrollArea(); scroll.setWidget(self.viz_stack); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:1px solid #e0e0e0;border-radius:4px} QScrollBar:vertical{width:12px;background:#f0f0f0} QScrollBar::handle:vertical{background:#c0c0c0;border-radius:4px} QScrollBar::add-line:vertical{height:0} QScrollBar::sub-line:vertical{height:0}")
        val.addWidget(scroll)

        self.content_widget=QWidget(); self.content_layout=QVBoxLayout(self.content_widget); self.content_layout.setContentsMargins(0,0,0,0); self.content_layout.setSpacing(8)
        self.tabs=QTabWidget(); self.tabs.setVisible(False); self.tabs.setMaximumHeight(500)
        self.content_layout.addWidget(self.tabs); self.content_layout.addWidget(self.viz_area)
        self.tabs.currentChanged.connect(lambda idx: self.viz_area.setVisible(
            idx >= 0 and self.tabs.count() > 0 and self.tabs.tabText(idx) == self.t("overview")))
        self.content_scroll=QScrollArea(); self.content_scroll.setWidget(self.content_widget); self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setStyleSheet("QScrollArea{border:none;background:transparent} QScrollBar:vertical{width:10px}")
        ml.addWidget(self.content_scroll, stretch=1)

        # Preview
        self.preview_panel=QWidget(); self.preview_panel.setVisible(False); self.preview_panel.setMaximumHeight(200)
        ppl=QHBoxLayout(self.preview_panel); ppl.setContentsMargins(8,4,8,4)
        self.preview_img=QLabel(); self.preview_img.setMaximumSize(180,160); self.preview_img.setStyleSheet("border:1px solid #d0d0d0;border-radius:4px;background:#fff")
        self.preview_img.setScaledContents(True); self.preview_img.setAlignment(Qt.AlignCenter); ppl.addWidget(self.preview_img)
        self.preview_info=QLabel(); self.preview_info.setWordWrap(True); ppl.addWidget(self.preview_info, stretch=1)
        btn_open_p=QPushButton("Open" if self.lang=='en' else "打开"); btn_open_p.clicked.connect(self._preview_open); ppl.addWidget(btn_open_p)
        btn_close_p=QPushButton("✕"); btn_close_p.setFixedWidth(30); btn_close_p.clicked.connect(lambda: self.preview_panel.setVisible(False)); ppl.addWidget(btn_close_p)
        ml.addWidget(self.preview_panel)

        self.welcome=QLabel(f"<div style='text-align:center;padding:80px;color:#888;'><p style='font-size:64px;'>🐱</p><p style='font-size:18px;'>DiskDoctor</p><p>{self.t('welcome')}</p></div>")
        self.welcome.setAlignment(Qt.AlignCenter); ml.addWidget(self.welcome, stretch=1)

    # ── Scan ──
    def _pick(self):
        d=QFileDialog.getExistingDirectory(self,"Select folder")
        if d: self.folder=d; self.path_lbl.setText(f"  {d}"); self.btn_scan.setEnabled(True)

    def _start(self):
        if not self.folder: return
        for w in [self.welcome, self.tabs, self.viz_area]:
            try: w.setVisible(False)
            except: pass
        try: self.scan_area.setVisible(True); self.btn_stop.setVisible(True); self.btn_scan.setEnabled(False)
        except: return
        try:
            self.worker=ScanWorker(self.folder)
            self.worker.progress.connect(self._on_progress)
            self.worker.finished.connect(self._on_done)
            self.worker.error.connect(lambda m: (self._scan_reset(), QMessageBox.warning(self,"Error","Scan error")))
            self.worker.start()
        except Exception as e:
            self._scan_reset()
            QMessageBox.warning(self,"Error",f"Failed to start scan: {e}")

    def _on_progress(self, prog):
        pct = min(95, int(prog.elapsed % 100))  # Animate
        self.big_bar.setValue(pct)
        phase_names = {"walking":"Scanning","hashing":"Detecting duplicates","perceptual":"Finding similar images","finalizing":"Building report"}
        self.phase_lbl.setText(f"{phase_names.get(prog.phase.value, prog.phase.value)}... {prog.files_found:,} files")
        self.count_lbl.setText(f"{prog.files_found:,}")
        self.eta_lbl.setText(f"⏱ {prog.elapsed:.0f}s | ⏳ ~{prog.eta_seconds:.0f}s" if prog.eta_seconds>0 else f"⏱ {prog.elapsed:.0f}s")
        self.small_bar.setValue(min(prog.files_found % 50 * 2, 99))

    def _cancel(self):
        try:
            if hasattr(self,'worker') and self.worker and self.worker.isRunning():
                self.worker.cancel()
                self.worker.wait(3000)
        except: pass
        self._scan_reset()

    def _scan_reset(self):
        try: self.scan_area.setVisible(False)
        except: pass
        try: self.btn_stop.setVisible(False)
        except: pass
        try: self.btn_scan.setEnabled(True)
        except: pass

    def _on_done(self, result):
        self.scan_result=result
        self._scan_reset()
        try: self.btn_scan.setVisible(False)
        except: pass
        try: self.btn_export.setVisible(True)
        except: pass
        try: self.welcome.setVisible(False)
        except: pass
        try: self._build()
        except Exception as e:
            QMessageBox.warning(self,"Error",f"Failed to build UI: {e}")

    # ── Lang / Emoji / Viz ──
    def _toggle_lang(self):
        self.lang="en" if self.lang=="zh" else "zh"
        self.settings["lang"]=self.lang; save_settings(self.settings)
        self.setWindowTitle(self.t("title")); self.btn_lang.setText(self.t("lang"))
        self.btn_scan.setText(self.t("scan")); self.btn_stop.setText(self.t("stop")); self.btn_export.setText(self.t("export"))
        self.viz_label.setText(self.t("chart")); self.emo_label.setText(self.t("emoji_style"))
        for i,n in enumerate([self.t("treemap"),self.t("donut"),self.t("bars")]):
            if i<len(self.btn_viz): self.btn_viz[i].setText(f"  {n}  ")
        if self.scan_result: self._build()

    def _chg_emoji(self, style):
        self.emoji_style=style; self.pack=EMOJI_PACKS.get(style,CAT_PACK)
        self.settings["emoji_style"]=style; save_settings(self.settings)
        if self.scan_result:
            self.treemap.set_data(self.scan_result["by_category"], self.pack); self._build()

    def _import_emoji(self):
        try:
            path,_=QFileDialog.getOpenFileName(self,"Select image","","Images (*.png *.jpg *.jpeg *.gif *.bmp)")
            if not path: return
            create_custom_pack(path)
            self.emoji_style="custom"
            self.settings["emoji_style"]="custom"
            save_settings(self.settings)
            if self.scan_result:
                self.pack=EMOJI_PACKS.get("custom",CAT_PACK)
                self.treemap.set_data(self.scan_result["by_category"],self.pack)
                self._build()
            QMessageBox.information(self,"Done" if self.lang=='en' else "完成","Custom emoji pack created!" if self.lang=='en' else "自定义表情包已创建！")
        except Exception as e:
            QMessageBox.warning(self,"Error",f"Import failed: {e}")

    def _viz(self, mode):
        self.treemap.setVisible(mode==0); self.donut.setVisible(mode==1); self.bars.setVisible(mode==2)
        if self.scan_result:
            if mode==1: self.donut.set_data(self.scan_result["by_category"])
            elif mode==2: self.bars.set_data(self.scan_result["by_category"])

    # ── Build Tabs ──
    def _build(self):
        r=self.scan_result; ins=generate_insights(r); tips=friendly_tips(r)
        cur_idx = self.tabs.currentIndex()
        self.tabs.clear(); self.tabs.setVisible(True); self.viz_area.setVisible(True)
        self.treemap.set_data(r["by_category"],self.pack); self.donut.set_data(r["by_category"]); self.bars.set_data(r["by_category"])

        # Overview
        ov=QWidget(); vl=QVBoxLayout(ov)
        vl.addWidget(QLabel(f"{health_face(ins['health_score'])} {self.t('health')}: {ins['health_score']}/100    {size_mood(r['total_size'],self.pack)} {self.t('total')}: {format_size(r['total_size'])}"))
        for t in tips:
            gb=QGroupBox(self.t("tip")); gl=QVBoxLayout(gb); lb=QLabel(t); lb.setWordWrap(True); gl.addWidget(lb); vl.addWidget(gb)
        vl.addStretch(); self.tabs.addTab(ov, self.t("overview"))

        # File Types
        ft=QWidget(); fl=QVBoxLayout(ft)
        t=QTreeWidget(); t.setHeaderLabels(["Type","Files","Size","%"] if self.lang=='en' else ["类型","数量","大小","占比"]); t.setAlternatingRowColors(True)
        for n,d in sorted(r["by_category"].items(),key=lambda x:-x[1]["size"]):
            QTreeWidgetItem(t,[f"{size_mood(d['size'],self.pack)} {CAT_ICONS.get(n,'')} {n}",f"{d['count']:,}",format_size(d['size']),f"{d['size']/max(r['total_size'],1)*100:.1f}%"])
        t.header().setStretchLastSection(True); fl.addWidget(t); self.tabs.addTab(ft,self.t("file_types"))

        # Duplicates
        dw=QWidget(); dl=QVBoxLayout(dw)
        if r["duplicates"]:
            dup_desc=f"{r['duplicate_count']} groups, {format_size(r['wasted_space'])} wasted." if self.lang=='en' else f"{r['duplicate_count']} 组重复，浪费 {format_size(r['wasted_space'])}。"
            dl.addWidget(QLabel(dup_desc))
            self.dup_cbs=[]
            for dg in r["duplicates"][:100]:
                cb=QCheckBox(f"[{format_size(dg['wasted'])}] {Path(dg['files'][0]).name} x{len(dg['files'])}"); cb.files=dg["files"]; self.dup_cbs.append(cb); dl.addWidget(cb)
            btn=QPushButton(self.t("del_dup")); btn.setProperty("class","danger"); btn.clicked.connect(self._del_dups); dl.addWidget(btn)
        else: dl.addWidget(QLabel(self.t("no_dups")))
        dl.addStretch(); self.tabs.addTab(dw,self.t("duplicates"))

        # Cold
        cw=QWidget(); cl=QVBoxLayout(cw)
        cold_desc=f"{len(r.get('cold_files',[]))} files not opened in 6+ months." if self.lang=='en' else f"{len(r.get('cold_files',[]))} 个文件半年以上未打开。"
        cl.addWidget(QLabel(cold_desc))
        ch=["File","Size","Last opened","Path"] if self.lang=='en' else ["文件名","大小","最后访问","路径"]
        ct=self._tree(ch,[(f"{size_mood(f['size'],self.pack)} {f['name']}",format_size(f['size']),format_date(f['atime']),f['path']) for f in sorted(r.get("cold_files",[]),key=lambda x:x['atime'])])
        ct.setSelectionMode(QTreeWidget.ExtendedSelection); cl.addWidget(ct)
        cd=QPushButton(self.t("del_sel")); cd.setProperty("class","danger"); cd.clicked.connect(lambda:self._del_tree(ct)); cl.addWidget(cd)
        self.tabs.addTab(cw,self.t("cold_files"))

        # Large
        lw=QWidget(); ll=QVBoxLayout(lw)
        large_desc=f"{len(r.get('large_files',[]))} files >100MB." if self.lang=='en' else f"{len(r.get('large_files',[]))} 个文件超过100MB。"
        ll.addWidget(QLabel(large_desc))
        lh=["File","Size","Path"] if self.lang=='en' else ["文件名","大小","路径"]
        lt=self._tree(lh,[(f"{size_mood(f['size'],self.pack)} {f['name']}",format_size(f['size']),f['path']) for f in sorted(r.get("large_files",[]),key=lambda x:-x['size'])])
        lt.setSelectionMode(QTreeWidget.ExtendedSelection); ll.addWidget(lt)
        ld=QPushButton(self.t("del_sel")); ld.setProperty("class","danger"); ld.clicked.connect(lambda:self._del_tree(lt)); ll.addWidget(ld)
        self.tabs.addTab(lw,self.t("large_files"))

        # Junk
        jw=QWidget(); jl=QVBoxLayout(jw)
        temp=r.get("temp_files",[])
        if temp:
            junk_desc=f"{len(temp)} junk files ({format_size(r.get('temp_size',0))}). 100% safe." if self.lang=='en' else f"{len(temp)} 个垃圾文件（{format_size(r.get('temp_size',0))}）。100% 安全可删。"
            jl.addWidget(QLabel(junk_desc))
            jh=["File","Size","Path"] if self.lang=='en' else ["文件名","大小","路径"]
            jt=self._tree(jh,[(f"🗑️ {f['name']}",format_size(f['size']),f['path']) for f in temp])
            jt.setSelectionMode(QTreeWidget.ExtendedSelection); jl.addWidget(jt)
            jd=QPushButton(self.t("del_junk")); jd.setProperty("class","danger"); jd.clicked.connect(lambda:self._del_all_junk(temp)); jl.addWidget(jd)
        else: jl.addWidget(QLabel(self.t("no_junk")))
        jl.addStretch(); self.tabs.addTab(jw,self.t("junk"))

        # Age
        aw=QWidget(); al=QVBoxLayout(aw)
        ba=r.get("by_age",{})
        if ba:
            at=QTreeWidget(); at.setHeaderLabels(["Age","Files","Size","Safe?"] if self.lang=='en' else ["年龄段","文件数","大小","能删吗"]); at.setAlternatingRowColors(True)
            nk={"Last 7 days":"last_7","1 week — 1 month":"week_month","1 — 3 months":"1_3_months","3 — 6 months":"3_6_months","6 — 12 months":"6_12_months","Over 1 year":"over_1yr"}
            hints={"Last 7 days":"🚫 "+self.t("safe_no"),"1 week — 1 month":"🤔 "+self.t("safe_maybe"),"1 — 3 months":"🤔 "+self.t("safe_maybe"),"3 — 6 months":"👍 "+self.t("safe_mostly"),"6 — 12 months":"👍 "+self.t("safe_safe"),"Over 1 year":"✅ "+self.t("safe_very")}
            for name in nk:
                if name in ba:
                    d=ba[name]; QTreeWidgetItem(at,[self.t(nk[name]),f"{d['count']:,}",format_size(d['size']),hints.get(name,"?")])
            at.header().setStretchLastSection(True); al.addWidget(at)
        al.addStretch(); self.tabs.addTab(aw,self.t("age"))

        # Near-dupes
        ndw=QWidget(); ndl=QVBoxLayout(ndw)
        near=r.get("near_duplicates",[])
        if near:
            ndl.addWidget(QLabel(f"🖼️ {self.t('near_dupes_desc').replace('{n}',str(len(near)))}"))
            ndt=QTreeWidget(); ndt.setHeaderLabels(["Group","Files","Wasted"] if self.lang=='en' else ["相似度","文件","可释放"]); ndt.setAlternatingRowColors(True); ndt.setRootIsDecorated(False)
            for nd in near[:100]:
                names=", ".join(Path(p).name for p in nd["files"][:3])
                QTreeWidgetItem(ndt,[f"Dist: {nd['distance']}",f"{names} ({len(nd['files'])} similar)",f"~{format_size(nd.get('wasted',0))}"])
            ndt.header().setStretchLastSection(True); ndl.addWidget(ndt)
            ndb=QPushButton(self.t("del_nd")); ndb.setProperty("class","danger"); ndb.clicked.connect(lambda:self._del_nd_tree(ndt,near)); ndl.addWidget(ndb)
        else: ndl.addWidget(QLabel(self.t("no_near_dupes")))
        ndl.addStretch(); self.tabs.addTab(ndw,self.t("near_dupes"))

        # Snapshot
        sw=QWidget(); sl=QVBoxLayout(sw)
        sd=PROJ/"snapshots"; sd.mkdir(exist_ok=True)
        sl.addWidget(QPushButton(self.t("save_snap"),clicked=self._snap))
        prev=sorted(sd.glob("*.json"),key=lambda p:p.stat().st_mtime,reverse=True)
        if prev:
            self.sc=QComboBox(); [self.sc.addItem(p.stem) for p in prev[:10]]; sl.addWidget(self.sc)
            sl.addWidget(QPushButton(self.t("compare"),clicked=self._cmp_snap))
            self.sr_lbl=QLabel(""); sl.addWidget(self.sr_lbl)
        sl.addStretch(); self.tabs.addTab(sw,self.t("snapshot"))

        # AI
        aiw=QWidget(); ail=QVBoxLayout(aiw)
        self.ai_txt=QTextEdit(); self.ai_txt.setReadOnly(True)
        mode=self.settings.get("ai_mode","local")
        lt=local_suggestions(r); self.ai_txt.setPlainText("\n\n".join(f"💬 {t}" for t in lt))
        if mode in ("deepseek","openai") and self.settings.get("api_key"):
            threading.Thread(target=lambda:self._run_ai(r,self.settings["api_key"],mode),daemon=True).start()
        ail.addWidget(self.ai_txt); self.tabs.addTab(aiw,self.t("ai_tips"))

        # Restore
        rw=QWidget(); rl=QVBoxLayout(rw)
        recs=[r for r in load_dels() if not r.get("restored")]
        if recs:
            rl.addWidget(QLabel(f"{len(recs)} deleted files can be restored."))
            rt=QTreeWidget(); rt.setHeaderLabels(["File","Original","Deleted"] if self.lang=='en' else ["文件名","原始路径","删除时间"]); rt.setAlternatingRowColors(True); rt.setSelectionMode(QTreeWidget.ExtendedSelection)
            for rec in recs: QTreeWidgetItem(rt,[Path(rec["original"]).name,rec["original"],rec["time"]])
            rt.header().setStretchLastSection(True); rl.addWidget(rt); self.restore_tree=rt
            rb=QPushButton(self.t("restore_btn")); rb.setProperty("class","primary"); rb.clicked.connect(self._restore); rl.addWidget(rb)
        else: rl.addWidget(QLabel("No deleted files." if self.lang=='en' else "没有已删除的文件。"))
        rl.addStretch(); self.tabs.addTab(rw,self.t("restore"))

        # Settings
        self._add_settings_tab()

        if cur_idx >= 0 and cur_idx < self.tabs.count():
            self.tabs.setCurrentIndex(cur_idx)

    def _add_settings_tab(self):
        sw2=QWidget(); sl2=QVBoxLayout(sw2)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setStyleSheet("QScrollArea{border:none}")
        inner=QWidget(); il=QVBoxLayout(inner)
        # Font size — Ctrl+scroll to adjust
        gz=QGroupBox("Font Size" if self.lang=='en' else "字号（Ctrl+滚轮）"); gzl=QVBoxLayout(gz)
        gzl.addWidget(QLabel("Ctrl+MouseWheel to zoom in/out" if self.lang=='en' else "按住 Ctrl 键 + 滚动鼠标滚轮 放大/缩小"))
        self.font_label=QLabel(f"{'Current:' if self.lang=='en' else '当前：'} {self.settings.get('font_size',10)}pt")
        gzl.addWidget(self.font_label); il.addWidget(gz)

        # Theme selector
        g0=QGroupBox("Theme" if self.lang=='en' else "主题"); g0l=QVBoxLayout(g0)
        self.theme_cb=QComboBox()
        try:
            from qt_material import list_themes
            themes=[t.replace('.xml','') for t in list_themes()]
            self.theme_cb.addItems(themes)
            cur=self.settings.get("theme","dark_teal")
            if cur in themes: self.theme_cb.setCurrentText(cur)
        except: self.theme_cb.addItems(["dark_teal","light_blue","dark_amber"])
        g0l.addWidget(QLabel("Theme:" if self.lang=='en' else "主题:")); g0l.addWidget(self.theme_cb)
        il.addWidget(g0)
        # AI settings
        g1=QGroupBox("AI"); g1l=QVBoxLayout(g1)
        self.ai_cb=QComboBox(); self.ai_cb.addItems(["local","deepseek","openai","ollama"]); self.ai_cb.setCurrentText(self.settings.get("ai_mode","local"))
        g1l.addWidget(QLabel("Engine:" if self.lang=='en' else "引擎:")); g1l.addWidget(self.ai_cb)
        g1l.addWidget(QLabel("API Key:" if self.lang=='en' else "API密钥:")); self.key_in=QLineEdit(); self.key_in.setText(self.settings.get("api_key","")); self.key_in.setEchoMode(QLineEdit.Password); g1l.addWidget(self.key_in)
        g2=QGroupBox("Ignore" if self.lang=='en' else "忽略文件夹"); g2l=QVBoxLayout(g2); self.ig_edit=QTextEdit(); self.ig_edit.setPlainText("\n".join(self.settings.get("ignore",[]))); self.ig_edit.setMaximumHeight(80); g2l.addWidget(self.ig_edit)
        il.addWidget(g1); il.addWidget(g2); il.addWidget(QPushButton("Save" if self.lang=='en' else "保存",clicked=self._save_sets)); il.addStretch()
        scroll.setWidget(inner); sl2.addWidget(scroll); self.tabs.addTab(sw2,self.t("settings"))

    # ── Actions ──
    def _show_settings(self):
        if self.scan_result:
            for i in range(self.tabs.count()):
                if "设置" in self.tabs.tabText(i) or "Settings" in self.tabs.tabText(i):
                    self.tabs.setCurrentIndex(i); return
        try: self.welcome.setVisible(False)
        except: pass
        try: self.viz_area.setVisible(False)
        except: pass
        self.tabs.clear(); self.tabs.setVisible(True)
        self._add_settings_tab(); self.tabs.setCurrentIndex(self.tabs.count()-1)

    def _save_sets(self):
        self.settings["ai_mode"]=self.ai_cb.currentText(); self.settings["api_key"]=self.key_in.text()
        self.settings["ignore"]=[l.strip() for l in self.ig_edit.toPlainText().split("\n") if l.strip()]
        # Apply theme
        new_theme=self.theme_cb.currentText()
        if new_theme != self.settings.get("theme",""):
            self.settings["theme"]=new_theme
            try:
                from qt_material import apply_stylesheet
                apply_stylesheet(QApplication.instance(), theme=new_theme+'.xml')
            except: pass
        save_settings(self.settings)
        QMessageBox.information(self,"Done" if self.lang=='en' else "完成","Saved." if self.lang=='en' else "已保存。")

    def _tree(self, headers, rows):
        t=QTreeWidget(); t.setHeaderLabels(headers); t.setAlternatingRowColors(True)
        for r in rows:
            item=QTreeWidgetItem([str(x) for x in r])
            item.setData(0, Qt.UserRole, r[-1] if r else "")  # Store path for reliable deletion
            t.addTopLevelItem(item)
        t.header().setStretchLastSection(True)
        t.setContextMenuPolicy(Qt.CustomContextMenu); t.customContextMenuRequested.connect(lambda p,tr=t: self._ctx(tr,p))
        t.itemClicked.connect(lambda it: self._show_preview(it)); return t

    def _ctx(self, tree, pos):
        it=tree.itemAt(pos)
        if not it: return
        path=it.data(0, Qt.UserRole)
        if not path: return
        m=QMenu()
        m.addAction("Preview" if self.lang=='en' else "预览",lambda p=path: self._preview_file(p))
        m.addAction("Open folder" if self.lang=='en' else "打开文件夹",lambda p=path: os.startfile(str(Path(p).parent)))
        m.addAction("Delete" if self.lang=='en' else "删除",lambda p=path: self._del([p]))
        m.exec(tree.viewport().mapToGlobal(pos))

    def _show_preview(self, item):
        path=item.data(0, Qt.UserRole)
        if path: self._preview_file(path)

    def _preview_file(self, path):
        if not os.path.exists(path): return
        info=f"📄 {Path(path).name}\n📁 {Path(path).parent}\n📏 {format_size(os.path.getsize(path))}\n📅 {datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M')}"
        self.preview_info.setText(info)
        if Path(path).suffix.lower() in ('.jpg','.jpeg','.png','.gif','.bmp','.webp'):
            try:
                pix=QPixmap(path)
                if not pix.isNull(): self.preview_img.setPixmap(pix); self.preview_img.setVisible(True)
                else: self.preview_img.setVisible(False)
            except: self.preview_img.setVisible(False)
        else: self.preview_img.setVisible(False)
        self.preview_panel.setVisible(True); self._preview_current=path

    def _preview_open(self):
        if hasattr(self,'_preview_current') and os.path.exists(self._preview_current):
            try: os.startfile(self._preview_current)
            except: QMessageBox.information(self,"Info" if self.lang=='en' else "提示","Cannot open this file type." if self.lang=='en' else "无法直接打开此文件类型。")

    def _del_tree(self, tree):
        its=tree.selectedItems()
        if not its: QMessageBox.information(self,"Hint" if self.lang=='en' else "提示","Select files first." if self.lang=='en' else "请先选择文件。"); return
        paths=[it.data(0, Qt.UserRole) for it in its if it.data(0, Qt.UserRole)]
        if paths: self._del(paths)

    def _del(self, paths):
        if not paths: return
        try:
            if not confirm_del(self,paths,self.lang): return
            ok,_=safe_del(paths)
            msg=f"Deleted {ok} files." if self.lang=='en' else f"已删除 {ok} 个文件。"
            QMessageBox.information(self,"Done" if self.lang=='en' else "完成",msg)
            if self.scan_result:
                del_set = set(paths)
                for key in ["cold_files","large_files","temp_files"]:
                    if key in self.scan_result:
                        self.scan_result[key] = [f for f in self.scan_result[key] if f["path"] not in del_set]
                if "cold_files" in self.scan_result:
                    self.scan_result["cold_count"] = len(self.scan_result["cold_files"])
                if "large_files" in self.scan_result:
                    self.scan_result["large_count"] = len(self.scan_result["large_files"])
                if "temp_files" in self.scan_result:
                    self.scan_result["temp_count"] = len(self.scan_result["temp_files"])
                    self.scan_result["temp_size"] = sum(f.get("size",0) for f in self.scan_result["temp_files"])
            self._build()
        except Exception as e:
            QMessageBox.warning(self,"Error",f"Delete failed: {e}")
            try: self._build()
            except: pass

    def _del_dups(self):
        files=[]
        for cb in self.dup_cbs:
            if cb.isChecked(): files.extend(cb.files[1:])
        if not files: QMessageBox.information(self,"Hint" if self.lang=='en' else "提示","Check groups first." if self.lang=='en' else "请先勾选要删除的重复文件组。"); return
        self._del(files)
        # Update duplicate count
        if self.scan_result:
            del_set=set(files)
            self.scan_result["duplicates"]=[d for d in self.scan_result["duplicates"] if not any(f in del_set for f in d["files"])]
            self.scan_result["duplicate_count"]=len(self.scan_result["duplicates"])
            self.scan_result["wasted_space"]=sum(d["wasted"] for d in self.scan_result["duplicates"])
        self._build()

    def _del_nd_tree(self, tree, near_groups):
        its=tree.selectedItems()
        if not its: QMessageBox.information(self,"Hint" if self.lang=='en' else "提示","Select groups first." if self.lang=='en' else "请先选择近似重复组。"); return
        files=[]
        for it in its:
            idx=tree.indexOfTopLevelItem(it)
            if 0<=idx<len(near_groups): files.extend(near_groups[idx]["files"][1:])
        if files:
            self._del(files)
            # Update near-dupe data
            if self.scan_result:
                del_set=set(files)
                self.scan_result["near_duplicates"]=[nd for nd in self.scan_result["near_duplicates"] if not any(f in del_set for f in nd["files"])]
                self.scan_result["near_duplicate_count"]=len(self.scan_result["near_duplicates"])
                self.scan_result["near_wasted_space"]=sum(nd.get("wasted",0) for nd in self.scan_result["near_duplicates"])
            self._build()

    def _del_all_junk(self, temp_files):
        try:
            paths=[f["path"] for f in temp_files if os.path.exists(f["path"])]
            if not paths: return
            total=sum(os.path.getsize(p) for p in paths)
            q=f"Delete {len(paths)} junk files ({format_size(total)})?" if self.lang=='en' else f"删除 {len(paths)} 个垃圾文件（{format_size(total)}）？"
            if QMessageBox.question(self,"Clean junk" if self.lang=='en' else "清理垃圾",q)==QMessageBox.Yes:
                self._del(paths)
        except Exception as e:
            QMessageBox.warning(self,"Error",f"Junk cleanup failed: {e}")

    def _restore(self):
        its=self.restore_tree.selectedItems()
        if not its: QMessageBox.information(self,"Hint" if self.lang=='en' else "提示","Select files first." if self.lang=='en' else "请先选择要恢复的文件。"); return
        recs=[r for r in load_dels() if any(Path(r["original"]).name==it.text(0) for it in its)]
        n=restore_files(recs)
        msg=f"Restored {n} files." if self.lang=='en' else f"已恢复 {n} 个文件。"
        QMessageBox.information(self,"Restored" if self.lang=='en' else "已恢复",msg); self._build()

    def _snap(self):
        r=self.scan_result
        snap={"time":datetime.now().isoformat(),"total_files":r["total_files"],"total_size":r["total_size"],"duplicates":r["duplicate_count"],"wasted":r["wasted_space"],"by_category":r["by_category"],"by_age":r.get("by_age",{}),"temp_count":r.get("temp_count",0)}
        p=PROJ/"snapshots"/f"snap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"; p.parent.mkdir(exist_ok=True); p.write_text(json.dumps(snap,indent=2,ensure_ascii=False))
        msg="Snapshot saved!" if self.lang=='en' else "快照已保存！"
        QMessageBox.information(self,"Saved" if self.lang=='en' else "已保存",msg); self._build()

    def _cmp_snap(self):
        prev=json.loads((PROJ/"snapshots"/f"{self.sc.currentText()}.json").read_text()); curr=self.scan_result
        diff=curr["total_size"]-prev["total_size"]; em="🎉" if diff<0 else "😱" if diff>1024**3 else "🤔"
        sign="-" if diff<0 else "+"
        msg=f"{em} Changes since {prev['time'][:16]}:\n\n  Size: {sign}{format_size(abs(diff))}\n  Files: {curr['total_files']-prev['total_files']:+,}\n  Dups: {prev['duplicates']}→{curr['duplicate_count']}"
        if diff<0: msg+=f"\n\n🎉 Saved {format_size(abs(diff))}!"
        self.sr_lbl.setText(msg)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            delta = 1 if event.angleDelta().y() > 0 else -1
            new_size = max(8, min(18, self.settings.get("font_size",10) + delta))
            self.settings["font_size"] = new_size
            app = QApplication.instance()
            if app: app.setFont(QFont("Segoe UI", new_size))
            if hasattr(self, 'font_label'): self.font_label.setText(f"{'Current:' if self.lang=='en' else '当前：'} {new_size}pt")
            save_settings(self.settings)
        else:
            super().wheelEvent(event)

    def _export_rpt(self):
        r=self.scan_result; ins=generate_insights(r); tips=friendly_tips(r)
        html=f"<html><head><meta charset=utf-8><title>DiskDoctor</title><style>body{{font-family:sans-serif;padding:32px;max-width:800px;margin:0 auto}}h1{{color:#4a90d9}}.card{{background:#f8f9fa;border-left:3px solid #4a90d9;padding:12px;margin:8px 0}}</style></head><body><h1>{health_face(ins['health_score'])} DiskDoctor Report</h1><p>{r['root']} | {datetime.now():%Y-%m-%d %H:%M}</p><h2>Summary</h2><p>{r['total_files']:,} files, {format_size(r['total_size'])}, Health: {ins['health_score']}/100</p><h2>Tips</h2>"+"".join(f"<div class=card><p>• {t}</p></div>" for t in tips)+"</body></html>"
        p=str(PROJ/"reports"/f"report_{datetime.now():%Y%m%d_%H%M%S}.html"); Path(p).parent.mkdir(exist_ok=True); Path(p).write_text(html,encoding='utf-8'); os.startfile(p)

    def _run_ai(self,r,key,provider):
        try:
            tips=online_suggestions(r,key,provider)
            if hasattr(self,'ai_txt'):
                self.ai_txt.setPlainText("\n\n".join(f"💬 {t}" for t in tips))
        except Exception as e:
            if hasattr(self,'ai_txt'):
                self.ai_txt.setPlainText(f"AI error: {e}")


if __name__=="__main__":
    try:
        settings_init=load_settings()
        app=QApplication(sys.argv); app.setFont(QFont("Segoe UI",settings_init.get("font_size",10)))
        try:
            from qt_material import apply_stylesheet
            apply_stylesheet(app, theme='dark_teal.xml')
        except: pass
        w=DiskDoctor(); w.show(); sys.exit(app.exec())
    except Exception as e:
        print(f"Fatal: {e}")
        sys.exit(1)
