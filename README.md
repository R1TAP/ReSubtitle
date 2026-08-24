# LiveLocalSubtitle —— 实时音频转字幕

**简体中文** | [English](README_EN.md)

实时监听正在播放的音频，通过**本地流式 ASR**实时转文字字幕

简单易用，轻巧流畅，在**全可自定义的**的字幕窗口上，实现类 CC 字幕效果。

```
正在播放的声音
      │
      │  WASAPI Loopback
      ▼
  采集线程 ────▶ 有界队列 ────▶ ASR 线程
      │                  │
      │                  │ partial/final
      ▼                  ▼
   实时字幕              可选 ────▶ 转录记录（时间轴+自动断句纠错+SRT/TXT导出）
```

## ✨ 功能/特性

- **实时字幕**：使用快捷键一键显示/隐藏的实时字幕，随时唤醒，随时可用。
- **本地流式ASR**：基于X-ASR 160ms Zipformer Transducer，轻巧流畅，无感运行。
- **自动矫正（Beta）**：基于本地小模型的实时纠正，稳定可靠，杜绝错漏。
- **稳定架构**：
  - 有界队列调度
  - 纯Python线程
  - Partial背压
  - final同步回调
  - **watchdog采集**
- **转录功能**：使用快捷键为视频快速生成字幕文件，精确的到句的时间轴，通过本地小模型实现**自动矫正（Beta）**。
- **托盘常驻**：启动后无感后台，轻巧架构，随时唤醒
- **窗口个性化**：从字体到色彩全可调的CC字幕窗口，新潮搭配，时刻随行。

## 🔧 环境配置

### 适配环境

- Windows **10/11**（x64）
- Python **3**

## ⚙️ 安装步骤

> 使用Release的稳定发布版，或基于源码构建

```bat
:: 1. 创建环境
python -m venv --without-pip .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

:: 2. 下载模型（约 134MB，首次运行自动下载；支持断点续传）
.venv\Scripts\python.exe scripts\download_model.py

:: 3. 运行
run.bat
```

### 调试

> 若 ensurepip 报错，可在用 `--without-pip` 后运行 `.venv\Scripts\python.exe get-pip.py` 引导 pip。


## 🚀 使用指南

| 快捷键 | 功能 |
|---|---|
| **F9** | 显示/隐藏实时字幕 |
| **F10** | 开始/停止转录记录 |
| 托盘图标 | 显示/隐藏字幕、开始/停止记录、选项调节、退出应用程序 |
| 字幕窗口 | 显示/隐藏字幕、开始/停止记录、选择监听设备、个性化设置、退出应用程序 |

> 快捷键修改： `config.ini` 中可修改 `hotkey_start` / `hotkey_stop`。

## 📦 自封装与打包

本程序基于开源协议，可在自行修改调整后自行打包

```bat
:: 通过预制脚本一键打包
scripts\build_exe.bat

:: 或手动：
.venv\Scripts\python.exe -m pip install pyinstaller pillow
.venv\Scripts\python.exe scripts\make_icon.py
.venv\Scripts\pyinstaller --noconfirm --clean --onefile --windowed ^
    --name LiveSubtitle --icon logo.ico --paths src ^
    --collect-all sherpa_onnx --collect-all sherpa_onnx_core --collect-all soundcard ^
    --add-data "logo.svg;." build_entry.py
xcopy /E /I /Y models dist\models
```

## 📁 项目结构

```
LiveSubtitle/
├── run.bat / run.ps1        启动脚本
├── requirements.txt
├── build_entry.py           PyInstaller
├── logo.svg                 程序图标
├── scripts/
│   ├── download_model.py    模型下载
│   ├── e2e_test.py          端到端自测
│   ├── make_icon.py         图标生成
│   └── build_exe.bat        一键打包
└── src/livesub/
    ├── main.py              程序入口
    ├── config.py            配置与持久化
    ├── models.py            模型与下载
    ├── audio.py             WASAPI采集
    ├── asr.py               流式识别/VAD/句长保护
    ├── recording.py         转录会话
    ├── subtitle_window.py   字幕窗口
    ├── pipeline.py          线程优化
    ├── app.py               常驻与状态机
    └── selftest.py          自测试
```

## 🗺️ Roadmap

- [ ] 本地 LLM 重排/纠错
- [ ] GPU（CUDA）推理
- [ ] 历史字幕记录
- [ ] 自适应排版优化
- [ ] MSI 安装包
