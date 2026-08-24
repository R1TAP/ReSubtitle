"""全局配置：路径、模型、音频、ASR、UI 参数。"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

# PyInstaller 冻结（exe）时以 exe 所在目录为根；源码运行时以项目根为根
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # LiveSubtitle/
SRC_DIR = Path(__file__).resolve().parent.parent              # LiveSubtitle/src/
MODELS_DIR = PROJECT_ROOT / "models"

# 主模型：X-ASR 160ms 流式 Zipformer Transducer（中英双语 + 标点，int8，2026-06-05 发布）
# 160ms 档：出字更即时、CPU 负载更平滑（960ms 档每 0.96s 才推进解码，短气口场景出字滞后）
MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-x-asr-160ms-streaming-zipformer-transducer-zh-en-punct-int8-2026-06-05.tar.bz2"
)
MODEL_DIR_NAME = "sherpa-onnx-x-asr-160ms-streaming-zipformer-transducer-zh-en-punct-int8-2026-06-05"

# 备用模型：960ms 档（更准，出字略慢）
ALT_MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-x-asr-960ms-streaming-zipformer-transducer-zh-en-punct-int8-2026-06-05.tar.bz2"
)

# 备用模型：2023 中英双语流式 Zipformer（旧）
FALLBACK_MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2"
)

# 预设配色方案：name -> (填充色 final, 中间结果色 partial, 描边色 outline)
# 设计原则：final 淡雅白亮（完成态、低干扰）；partial 高饱和暖/彩色（进行态、一眼可辨）；
#           outline 深色相（保证任意背景下的对比度）。
COLOR_SCHEMES: dict[str, tuple[str, str, str]] = {
    "经典白":   ("#FFFFFF", "#7CFFB2", "#000000"),   # 纯白 / 亮绿 / 黑
    "护眼绿":   ("#F1F8E9", "#FFD54F", "#1B5E20"),   # 淡绿白 / 暖黄 / 深绿
    "暖金":     ("#FFF8E1", "#FF8A65", "#5D4037"),   # 米白 / 珊瑚橙 / 深棕
    "水蓝":     ("#E1F5FE", "#FFB74D", "#01579B"),   # 淡蓝白 / 琥珀 / 深蓝
    "暮紫":     ("#F3E5F5", "#80DEEA", "#4A148C"),   # 淡紫白 / 亮青 / 深紫
    "日落橙":   ("#FFF3E0", "#4FC3F7", "#BF360C"),   # 淡橙白 / 亮蓝 / 深橙棕
    "烟灰":     ("#F5F5F5", "#FFEE58", "#37474F"),   # 冷白 / 亮黄 / 深灰
    "高对比黄": ("#FFFDE7", "#FF7043", "#000000"),   # 米黄白 / 橙红 / 黑
}

# 单色选择（自由搭配填充/中间/描边色）
COLOR_PICKER: dict[str, str] = {
    "白": "#FFFFFF", "黑": "#000000", "灰": "#B0BEC5", "深灰": "#455A64",
    "红": "#EF5350", "橙": "#FFA726", "黄": "#FFEE58", "绿": "#66BB6A",
    "护眼绿": "#C8E6C9", "青": "#4DD0E1", "蓝": "#42A5F5", "深蓝": "#1565C0",
    "紫": "#AB47BC", "深紫": "#6A1B9A", "粉": "#EC407A", "棕": "#8D6E63",
    "深绿": "#2E7D32", "米白": "#FFF8E1", "淡蓝": "#E3F2FD", "淡绿": "#E8F5E9",
    "亮绿": "#7CFFB2", "暖黄": "#FFD54F", "珊瑚橙": "#FF8A65", "琥珀": "#FFB74D",
    "亮青": "#80DEEA", "亮蓝": "#4FC3F7", "亮黄": "#FFEE58", "橙红": "#FF7043",
}


def _looks_like_model_dir(p: Path) -> bool:
    """模型目录判据：有 tokens.txt 且至少一个 .onnx 模型文件。"""
    if not p.is_dir():
        return False
    if not (p / "tokens.txt").exists():
        return False
    return any(p.glob("*.onnx"))


def find_model_dir(prefer: str | None = None) -> Path | None:
    """在 MODELS_DIR 下寻找已解压且文件完整的模型目录。

    prefer 传入目录名前缀时**只**匹配该前缀（如 'x-asr'），不匹配则返回 None；
    未指定 prefer 时返回第一个合法目录。
    """
    if not MODELS_DIR.exists():
        return None
    candidates = [p for p in sorted(MODELS_DIR.iterdir()) if _looks_like_model_dir(p)]
    if not candidates:
        return None
    if prefer:
        for p in candidates:
            if prefer.lower() in p.name.lower():
                return p
        return None
    return candidates[0]


@dataclass
class AudioConfig:
    """WASAPI 环回采集配置。"""

    sample_rate: int = 16000      # ASR 统一用 16k（soundcard 内部重采样）
    chunk_ms: int = 160           # 每块时长，与 X-ASR 160ms 模型 chunk 对齐（减少无效解码）
    device_substr: str = ""       # 为空则自动选择默认输出的环回设备；可填名称子串指定
    level_scale: float = 4.0      # RMS -> 0~1 电平指示的放大系数


@dataclass
class ASRConfig:
    """sherpa-onnx 流式识别配置。"""

    sample_rate: int = 16000
    num_threads: int = 2          # 推理线程（int8 小模型 2 线程即可实时，降低 CPU 占用）
    # modified_beam_search 相比 greedy 显著减少重复字、提升准确率
    decoding_method: str = "modified_beam_search"
    max_active_paths: int = 5
    enable_endpoint_detection: bool = True
    rule1_min_trailing_silence: float = 1.0   # 静音 1.0s 断句
    rule2_min_trailing_silence: float = 0.5   # 较长句子静音 0.5s 断句
    rule3_min_utterance_length: int = 30      # 帧数（10ms/帧）：超过 0.3s 启用 rule2

    # 应用层能量 VAD：不依赖 sherpa 的端点规则，静音超时强制断句（环回场景更可靠）
    vad_enabled: bool = True
    vad_silence_rms: float = 0.004    # 块 RMS 低于此值视为静音
    vad_commit_ms: int = 500           # 连续静音超过此毫秒数 -> 提交当前句子（短气口也能断句）

    # 最长单句时长：连续语音（无静音停顿）超过此毫秒数也强制提交+reset，
    # 防止流式流内部状态无限增长导致 CPU/内存随时间飙升；同时避免 partial 文本过长
    max_utterance_ms: int = 8000


@dataclass
class UIConfig:
    """字幕窗口外观配置。"""

    font_family: str = "Microsoft YaHei UI"
    font_size: int = 30
    text_color: str = "#FFFFFF"      # 已确认句子
    partial_color: str = "#D8FFE8"   # 实时中间结果（带透明度）
    outline_color: str = "#000000"   # CC 描边
    outline_width: float = 3.5
    bg_color: str = "#0E1419"        # 每行背景条颜色（深色）
    bg_alpha: float = 0.35           # 背景条不透明度（0=无背景，最高 0.85）
    bg_corner: int = 8               # 背景条圆角半径
    window_width_ratio: float = 0.72 # 窗口宽度 = 屏幕宽度的比例
    width_presets: tuple = (0.4, 0.55, 0.7, 0.85, 1.0)   # 右键菜单宽度预设
    fixed_height_lines: int = 0      # 0=高度随内容自适应；>0 固定显示行数
    height_presets: tuple = (0, 2, 3, 4, 5, 6)           # 右键菜单高度预设（0=自动）
    margin: int = 24                 # 左右/底部边距
    line_spacing: int = 6
    max_lines: int = 3               # 归档：最多保留的句子条数
    max_wrap_lines: int = 6          # 显示：所有句子折行后的最大总行数
    window_opacity: float = 0.95
    idle_hide_ms: int = 3500         # 无新文字多久后自动淡出
    fade_ms: int = 500
    bottom_offset: int = 48          # 距屏幕底部像素


@dataclass
class Settings:
    audio: AudioConfig = field(default_factory=AudioConfig)
    asr: ASRConfig = field(default_factory=ASRConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    asr_model_dir: str | None = None
    window_pos: str = ""          # "x,y"，持久化的窗口位置（空=默认底部居中）
    # 转录录制
    hotkey_start: int = 0x78      # F9  VK_F9
    hotkey_stop: int = 0x79       # F10 VK_F10
    llm_endpoint: str = ""        # 可选纠错 LLM（如 ollama http://127.0.0.1:11434），空=不启用
    llm_model: str = "qwen2.5:4b"


# ---------------------------------------------------------------------------
# 配置持久化（QSettings，注册表；exe 与源码均可用）
# ---------------------------------------------------------------------------
_UI_FIELDS = (
    "font_family", "font_size", "text_color", "partial_color", "outline_color",
    "outline_width", "bg_color", "bg_alpha", "window_width_ratio",
    "fixed_height_lines", "window_opacity",
)
_UI_CASTS = {
    "font_size": int, "outline_width": float, "bg_alpha": float,
    "window_width_ratio": float, "fixed_height_lines": int, "window_opacity": float,
}


def _qsettings():
    """配置文件：exe/source 旁的 config.ini（IniFormat，随程序走，便携）。"""
    from PySide6.QtCore import QSettings
    return QSettings(str(PROJECT_ROOT / "config.ini"), QSettings.IniFormat)


def load_settings(settings: Settings) -> Settings:
    """从 config.ini 读取上次保存的配置（需在 QApplication 创建后调用）。"""
    qs = _qsettings()
    ui = settings.ui
    for f in _UI_FIELDS:
        v = qs.value(f)
        if v is None:
            continue
        cast = _UI_CASTS.get(f, str)
        try:
            setattr(ui, f, cast(v))
        except (TypeError, ValueError):
            pass
    dev = qs.value("device_substr", "")
    if dev:
        settings.audio.device_substr = str(dev)
    pos = qs.value("window_pos", "")
    if pos:
        settings.window_pos = str(pos)
    return settings


def save_settings(settings: Settings, window=None) -> None:
    """保存全部可调配置到 config.ini。window 提供时同时保存其位置。"""
    qs = _qsettings()
    ui = settings.ui
    for f in _UI_FIELDS:
        qs.setValue(f, getattr(ui, f))
    qs.setValue("device_substr", settings.audio.device_substr)
    if window is not None:
        qs.setValue("window_pos", f"{window.x()},{window.y()}")
    qs.sync()
