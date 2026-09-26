"""字幕录制会话：记录句子时间轴、规则纠错、可选 LLM 纠错、导出 SRT/TXT。"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
import wave
from pathlib import Path

import numpy as np


# ---------------------------------------------------------------------------
# 时间轴格式
# ---------------------------------------------------------------------------
def fmt_ts(sec: float) -> str:
    """[mm.ss.mmm] 格式，如 [01.23.456]。"""
    sec = max(0.0, sec)
    m = int(sec // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    return f"[{m:02d}.{s:02d}.{ms:03d}]"


def srt_ts(sec: float) -> str:
    """SRT 时间轴 HH:MM:SS,mmm。"""
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ---------------------------------------------------------------------------
# 文本纠错
# ---------------------------------------------------------------------------
# 流式 ASR 高频重复字（恰好出现 2 次时也压缩；避免误伤"天天""人人"等真实叠词）
_COMMON_REPEAT_CHARS = frozenset(
    "的了是在和所这那就都也很我你他她它不有没上下中把被让给从对向以与及或而且但如若虽然因为于之其此该每各"
    "要来去出到看说想知着过会能应可再又还只多多少"
)


def fix_text(text: str) -> str:
    """规则纠错：针对流式 ASR 常见问题。

    - 压缩连续重复字符：>=3 个相同直接压为 1；恰好 2 个仅在字符为高频虚词时压缩
      （如"所所所以以" -> "所以"，但"天天""人人"等真实叠词保留）
    - 规整多余空白
    """
    if not text:
        return text
    t = re.sub(r"(.)\1{2,}", r"\1", text)          # >=3 连续重复 -> 1
    out: list[str] = []
    i = 0
    while i < len(t):
        ch = t[i]
        if i + 1 < len(t) and t[i + 1] == ch and ch in _COMMON_REPEAT_CHARS:
            out.append(ch)
            i += 2
        else:
            out.append(ch)
            i += 1
    t = "".join(out)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def make_llm_fixer(endpoint: str, model: str):
    """构造 LLM 纠错回调（ollama OpenAI 兼容 /api/generate）。失败时原样返回。"""
    def fix(text: str) -> str:
        prompt = (
            "你是字幕纠错助手。修正下面语音识别文本中的错别字与多余重复字，"
            "保持原意，只输出修正后的文本：\n" + text
        )
        payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
        try:
            req = urllib.request.Request(
                endpoint.rstrip("/") + "/api/generate",
                data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r).get("response", "").strip() or text
        except Exception as e:  # noqa: BLE001
            print(f"[recording] LLM 纠错失败: {e}")
            return text
    return fix


# ---------------------------------------------------------------------------
# 录制会话
# ---------------------------------------------------------------------------
class RecordingSession:
    """记录每句 final 的相对时间戳；可选同时保存 16k 单声道 wav。

    线程安全：on_final 由 ASR 线程直接调用（不依赖主线程事件循环，主线程阻塞也不丢句子）。
    """

    def __init__(self):
        self.finals: list[tuple[float, str]] = []   # (相对秒, 文本)
        self._lock = threading.Lock()               # 保护 finals 与 _t0
        self._t0: float | None = None
        self._wav: wave.Wave_write | None = None
        self._wav_path: Path | None = None

    @property
    def active(self) -> bool:
        return self._t0 is not None

    @property
    def duration(self) -> float:
        return (time.monotonic() - self._t0) if self._t0 is not None else 0.0

    # ---------------- 生命周期 ----------------
    def start(self, wav_path: str | Path | None = None):
        with self._lock:
            self.finals.clear()
            self._t0 = time.monotonic()
        if wav_path:
            self._wav_path = Path(wav_path)
            self._wav = wave.open(str(self._wav_path), "wb")
            self._wav.setnchannels(1)
            self._wav.setsampwidth(2)
            self._wav.setframerate(16000)

    def stop(self):
        if self._wav is not None:
            try:
                self._wav.close()
            finally:
                self._wav = None
        with self._lock:
            self._t0 = None

    # ---------------- 数据入口 ----------------
    def on_final(self, text: str):
        """ASR 每句完成时调用（ASR 线程，同步）。"""
        with self._lock:
            if self._t0 is not None and text:
                self.finals.append((time.monotonic() - self._t0, text))

    def feed_audio(self, samples: np.ndarray):
        """录制中把音频写入 wav（可选）。"""
        if self._wav is not None and samples is not None and samples.size:
            pcm = np.clip(np.asarray(samples) * 32767.0, -32768, 32767).astype(np.int16)
            self._wav.writeframes(pcm.tobytes())

    # ---------------- 导出 ----------------
    def export(self, path: str | Path, fmt: str = "srt", fix: bool = True,
               llm_fix=None) -> int:
        """导出字幕。fmt: 'srt' | 'txt'。返回句数。"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        entries: list[tuple[float, str]] = []
        for t, text in self.finals:
            t2 = fix_text(text) if fix else text
            if llm_fix is not None:
                t2 = llm_fix(t2)
            entries.append((t, t2))

        if fmt == "srt":
            body: list[str] = []
            prev_end = 0.0
            for i, (t, text) in enumerate(entries, 1):
                start = prev_end
                end = t if t > prev_end else prev_end + 1.0
                prev_end = end
                body.append(f"{i}\n{srt_ts(start)} --> {srt_ts(end)}\n{text}\n")
            path.write_text("\n".join(body), encoding="utf-8")
        else:
            path.write_text(
                "\n".join(f"{fmt_ts(t)} {text}" for t, text in entries),
                encoding="utf-8")
        return len(entries)

    def preview(self, fix: bool = True, max_lines: int = 5) -> str:
        """导出内容预览（对话框用）。"""
        lines = [
            f"{fmt_ts(t)} {(fix_text(text) if fix else text)}"
            for t, text in self.finals[:max_lines]
        ]
        more = f"... 共 {len(self.finals)} 句，{self.duration:.1f}s" if self.finals else "（无记录）"
        return "\n".join(lines) + "\n" + more
