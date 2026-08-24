# LiveSubtitle —— 桌面实时音频转字幕

**简体中文** | [English](README_EN.md)

实时监听电脑正在播放的音频，通过**本地流式 ASR**（sherpa-onnx X-ASR 中英双语 + 标点）实时转成文字，
叠加在**透明、可拖拽、置顶**的字幕窗口上，实现类 CC 字幕效果。全程离线，音频不出本机。

```
系统正在播放的声音
        │  WASAPI Loopback（soundcard 采集，16kHz 单声道）
        ▼
  采集线程 ──有界队列(满丢旧帧)──▶ ASR 线程（X-ASR 160ms 流式解码）
        │                              │ partial(节流合并)/final(同步回调)
        ▼                              ▼
  透明字幕叠加窗（PySide6）    ──可选──▶ 转录记录（时间轴+纠错+SRT/TXT 导出）
```

## ✨ 功能特性

- ✅ **实时 CC 字幕（核心）**：F9 一键显示/隐藏，随时可用；透明背景 + 黑色描边 + 可调半透明背景条
- ✅ **本地流式 ASR**：X-ASR 160ms Zipformer Transducer（中英双语 + 标点，int8，~134MB），CPU 实时（约 3~4 核）
- ✅ **自动断句**：能量 VAD（静音 0.5s 强制提交）+ sherpa 端点规则 + 最长单句 15s 强制重置（防流状态膨胀）
- ✅ **稳定性架构**：有界队列防积压、纯 Python 线程、partial 背压（主线程慢时事件不积压 + 超时自动恢复）、
  final 同步回调（主线程阻塞不丢句）、**采集 watchdog（蓝牙/虚拟声卡等设备长时间 WASAPI 采集退化时自动重启采集自愈）**、
  窗口 resize 防抖；**30 分钟全链路真实采集长测通过（全程字幕最大停顿 2 秒）**
- ✅ **转录记录（附带）**：F10 开始/停止记录，每句 `[mm.ss.mmm]` 时间轴，规则纠错压缩流式重复字
  （"所所所以以"→"所以"，不误伤叠词），自动保存 **SRT 字幕 + TXT 文本**到 `recordings` 文件夹；可选 LLM 纠错（ollama）
- ✅ **系统托盘常驻**：启动即驻留托盘（零 CPU），托盘右键菜单**状态同步**（字幕开则显示"隐藏字幕"）、
  **选项…（预览调节：不加载模型，示例句子直接调配色/尺寸，关闭窗口即保存）**、退出；关闭字幕窗=隐藏到托盘
- ✅ **窄窗口自适应**：长句折行超出 6 行时**保留最新行**（字幕始终显示最新内容，不卡在句子开头）——任意窗口宽度持续流畅
- ✅ **个性化**：右键菜单可调字体/字号（滑条）、配色方案（8 套）+ 三色自由搭配、窗口宽度/高度、背景不透明度、
  描边粗细、监听设备切换（运行中热切换）；全部配置自动记忆（`config.ini`）
- ✅ **自定义图标**：使用 `logo.svg`（托盘 + exe 图标，可自行替换）

## 🔧 环境配置

### 环境要求

- Windows 10/11（x64）
- Python **3.10 ~ 3.13**（开发验证于 3.13）
- 无 GPU 要求（CPU 推理即可）

### 安装步骤

```bat
:: 1. 克隆/下载源码后，创建虚拟环境
python -m venv --without-pip .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

:: 2. 下载模型（约 134MB，首次运行也会自动下载；支持断点续传）
.venv\Scripts\python.exe scripts\download_model.py

:: 3. 运行
run.bat                          :: 托盘常驻（F9 显示字幕，F10 记录）
run.bat --demo                   :: 演示模式（无需音频/模型，模拟字幕）
```

> 若 `python -m venv` 的 ensurepip 报错（沙箱/企业环境），可用 `--without-pip` 后
> 运行 `.venv\Scripts\python.exe get-pip.py` 引导 pip。

### 自测命令

```bat
run.bat --selftest-asr       :: ASR 自测：离线识别模型自带 wav（退出码 0=OK）
run.bat --selftest-gui       :: GUI 自测：构建菜单/热键/图标后退出（退出码 0=OK）
run.bat --selftest-capture   :: 采集自测：打印 5 秒环回电平
.venv\Scripts\python.exe scripts\e2e_test.py   :: 端到端：播放测试语音->环回采集->实时识别
```

## 🚀 使用

| 按键 | 功能 |
|---|---|
| **F9** | 显示/隐藏实时字幕（核心，随时可用） |
| **F10** | 开始/停止转录记录（自动保存 SRT+TXT） |
| 托盘图标 | 右键菜单：显示/隐藏字幕（状态同步）、开始/停止记录、选项…（预览调节）、退出；双击显示窗口 |
| 字幕窗右键 | 显示/隐藏字幕、记录开关、监听设备、宽度/高度/透明度/描边滑条、配色、字体字号、退出 |

快捷键可在 `config.ini` 中修改 `hotkey_start` / `hotkey_stop`（Windows 虚拟键码）。

## 📦 打包为 EXE

```bat
:: 一键打包（自动装 PyInstaller、打包含 livesub、复制模型与图标）
scripts\build_exe.bat

:: 或手动：
.venv\Scripts\python.exe -m pip install pyinstaller pillow
.venv\Scripts\python.exe scripts\make_icon.py        :: 生成 logo.png/ico
.venv\Scripts\pyinstaller --noconfirm --clean --onefile --windowed ^
    --name LiveSubtitle --icon logo.ico --paths src ^
    --collect-all sherpa_onnx --collect-all sherpa_onnx_core --collect-all soundcard ^
    --add-data "logo.svg;." build_entry.py
xcopy /E /I /Y models dist\models
```

产物 `dist\LiveSubtitle.exe`：单文件、无控制台。`dist\models` 为模型（缺失时自动下载）。

## 📁 项目结构

```
LiveSubtitle/
├── run.bat / run.ps1        启动脚本
├── requirements.txt
├── build_entry.py           PyInstaller 打包入口
├── logo.svg                 程序图标（可替换）
├── scripts/
│   ├── download_model.py    模型下载（断点续传）
│   ├── e2e_test.py          端到端自测
│   ├── make_icon.py         SVG -> PNG/ICO 图标生成
│   └── build_exe.bat        一键打包
└── src/livesub/
    ├── main.py              入口 / 参数 / 异常兜底
    ├── config.py            配置 + 配色方案 + 持久化
    ├── models.py            模型查找/下载
    ├── audio.py             WASAPI 环回采集（有界队列）
    ├── asr.py               sherpa-onnx 流式识别 + VAD + 最长句长保护
    ├── recording.py         转录会话（时间轴/纠错/导出）
    ├── subtitle_window.py   透明字幕窗（换行/配色/菜单）
    ├── pipeline.py          线程装配（防积压/节流/同步回调）
    ├── app.py               托盘常驻/热键/状态机
    └── selftest.py          无 GUI 自测
```

## ⚠️ 已知限制

- 环回采集默认输出设备；多输出设备用右键菜单「监听设备」或 `--device 设备名子串` 指定
- 只采集系统播放的声音（不含麦克风，除非开启"立体声混音"）
- 流式模型为 int8 量化，短句偶有识别误差；长句偶有字词重复（纠错规则可压缩）
- GPU 加速需官方发布 CUDA wheel（当前 pip 包未编译 GPU，CPU 已实时）

## 🗺️ Roadmap

- [ ] 本地 LLM 句子重排与纠错（如 Qwen2.5-4B via ollama，自动修正错别字/重排句子）
- [ ] GPU（CUDA）推理（等官方 wheel）
- [ ] 历史字幕记录查看器
- [ ] 多行自适应排版优化
- [ ] MSI 安装包
