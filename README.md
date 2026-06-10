# DiskDoctor — 磁盘小医生

磁盘空间分析 + 清理建议 + AI 辅助。帮你找到重复文件、冷文件、垃圾文件，告诉你怎么清理。

## 下载

[蓝奏云下载 DiskDoctor.exe](https://www.ilanzou.com/s/GDs1TK5S)

## 功能

- 🔍 全盘扫描，自动分类（图片/视频/文档/代码/安装包...）
- 🔄 感知哈希去重——找出一模一样和几乎一样的文件
- ❄️ 冷文件检测——半年没动过的文件帮你找出来
- 🗑️ 垃圾文件识别——临时文件、缓存、日志
- 📊 三种可视化：方块图 / 甜甜圈 / 柱状图
- 🤖 AI 建议：本地规则 / DeepSeek / OpenAI / Ollama
- 🛡️ 安全删除：备份恢复 + 系统文件多重警告
- 🌐 中英文双语 + 19 种主题可切换

## 运行

下载 exe，双击即可。或从源码运行：

```bash
pip install PySide6 qt-material imagehash pillow
python main.py
```

## 技术栈

Python + PySide6 + ScanEngine v2 + imagehash + qt-material

## 作者

张嘉文 | 哈尔滨华德学院 | 计算机科学与技术
