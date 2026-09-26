<p align="center">
  <b>ReSubtitle</b>
</p>

<p align="center">
  <img src="src/assets/icon.png" width="128" height="128" alt="ReSubtitle Logo" />
</p>

<p align="center">
  <b>简洁易用，轻巧流畅，基于本地流式 ASR 的桌面实时语音转字幕程序</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows-blue?style=flat-square" alt="Platform" />
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square" alt="Python" />
  <img src="https://img.shields.io/badge/GUI-PySide6-green?style=flat-square" alt="PySide6" />
  <img src="https://img.shields.io/badge/License-MIT-blue?style=flat-square" alt="License" />
</p>

<p align="center">
<b>实时监听正在播放的系统音频，通过本地流式 ASR 毫秒级转文字，类 CC 字幕悬浮叠加，托盘常驻，开箱即用。</b>
</p>

```
正在播放的系统声音
       │
       │  WASAPI Loopback (soundcard)
       ▼
   采集线程 ────▶ 有界队列 ────▶ ASR 识别线程
       │                            │
       │                            │ partial / final
       ▼                            ▼
    实时字幕                    可选转录会话 ────▶ 导出字幕
```

## ✨ 功能/特性

- **实时字幕**：一键唤出透明叠加字幕窗，**随时唤醒，随心拖拽**，类 CC 影视字幕体验。
- **本地流式 ASR**：基于X-ASR，**离线私密，超低延迟，负载平滑**。
- **WASAPI 环回采集**：原生捕获扬声器音频，无需外接麦克风或安装虚拟音频驱动。
- **转录会话记录**：一键启动录制，精准对齐时间轴，实时导出高质量 SRT 与 TXT 字幕文件。
- **能量 VAD & 智能断句**：双重断句机制，杜绝内存累积与延时堆积。
- **全能个性化**：支持自由调节字体、字号、半透明背景条、描边粗细与自适应行数。
- **托盘静默常驻**：开箱即用，后台 0 开销，快捷键或托盘菜单随时唤起。

## 🔧 环境配置

### 直接使用

- Windows **10/11**（x64）
- 下载便携版，双击运行即可

### 源码运行

- Windows **10/11**（x64）
- Python **3.10+**
- 执行 pip install -r requirements.txt 安装环境依赖

## 🚀 快速上手

### 1. 运行 ReSubtitle

- **使用便携版（推荐）**

  双击运行：

  ```text
  dist/ReSubtitle.exe
  ```

- **开发者环境**

  ```bash
  # 1. 创建虚拟环境并安装依赖
  python -m venv .venv
  .venv\Scripts\pip install -r requirements.txt

  # 2. 准备/下载本地语音模型（约 134MB，支持断点续传）
  .venv\Scripts\python scripts/download_model.py

  # 3. 启动开发版
  scripts\run.bat   # 或 .venv\Scripts\python -m resubtitle.main

  # 4. 构建打包单文件便携版
  scripts\build_exe.bat
  ```

### 2. 交互与快捷键

| 操作方式 | 功能说明 |
| :--- | :--- |
| **F9** | 显示 / 隐藏实时字幕叠加窗口 |
| **F10** | 开始 / 停止转录会话，自动导出 SRT + TXT 字幕 |
| **字幕窗左键** | 任意文字区域拖拽移动位置，双击底部快捷复位 |
| **字幕窗右键** | 呼出快捷菜单 |
| **系统托盘图标** | 双击显示窗口，右键呼出菜单 |


## 📄 开源许可证与声明

- ReSubtitle 遵循 [MIT License](LICENSE) 开源协议。
  - 第三方组件遵循各自许可证，详见 [NOTICE.md](NOTICE.md)。