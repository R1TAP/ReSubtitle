"""QApplication 组装、系统托盘常驻、实时字幕核心 + 转录记录附带、全局热键与退出清理。

工作流（核心 = 实时 CC 字幕，转录 = 附带记录）：
  启动 -> 托盘常驻（零 CPU）
  F9 / 托盘/菜单"显示字幕" -> 启动流水线 + 字幕窗出现（随时可用）→ 再按 F9 关闭隐藏
  F10 / "记录" -> 在字幕基础上开始/停止转录（自动保存 SRT+TXT，非模态提示）
  托盘"退出" -> 真正退出
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QMenu, QMessageBox, QSystemTrayIcon,
)

from . import config as C
from .models import ensure_model
from .pipeline import Pipeline
from .recording import RecordingSession
from .subtitle_window import SubtitleWindow

DEMO_PHRASES = [
    "大家好，欢迎来到今天的直播现场。",
    "今天我们聊一聊实时语音识别背后的技术方案。",
    "Hello everyone, this is a live subtitle overlay demo.",
    "音频通过 WASAPI 环回采集，本地模型实时识别。",
    "字幕窗口完全透明，只显示文字，可以随意拖拽。",
]

WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000


class _HotkeyFilter(QAbstractNativeEventFilter):
    """Windows 全局热键：RegisterHotKey 的 WM_HOTKEY 消息经由 nativeEventFilter 分发。

    注意：必须继承 QAbstractNativeEventFilter，否则 installNativeEventFilter 抛 TypeError。
    """

    def __init__(self, on_toggle_subtitle, on_toggle_record, parent=None):
        super().__init__(parent)
        self._on_sub = on_toggle_subtitle
        self._on_rec = on_toggle_record

    def nativeEventFilter(self, eventType, message):  # noqa: N802
        if eventType == b"windows_generic_MSG":
            try:
                msg = wintypes.MSG.from_address(int(message))
            except Exception:  # noqa: BLE001
                return False, 0
            if msg.message == WM_HOTKEY:
                if msg.wParam == 1:      # F9 字幕开关
                    QTimer.singleShot(0, self._on_sub)
                elif msg.wParam == 2:    # F10 记录开关
                    QTimer.singleShot(0, self._on_rec)
        return False, 0


def _register_hotkeys(settings: C.Settings) -> bool:
    try:
        user32 = ctypes.windll.user32
        user32.RegisterHotKey(None, 1, MOD_NOREPEAT, settings.hotkey_start)
        user32.RegisterHotKey(None, 2, MOD_NOREPEAT, settings.hotkey_stop)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[app] 全局热键注册失败: {e}")
        return False


def _unregister_hotkeys():
    try:
        user32 = ctypes.windll.user32
        user32.UnregisterHotKey(None, 1)
        user32.UnregisterHotKey(None, 2)
    except Exception:  # noqa: BLE001
        pass


def _find_logo() -> str:
    """定位应用图标（icon.png / icon.ico / icon.svg，exe 同目录 / assets / 项目根 / PyInstaller 解压目录）。"""
    import pathlib
    cands = [
        getattr(C, "ASSETS_DIR", C.PROJECT_ROOT / "src" / "assets") / "icon.png",
        getattr(C, "ASSETS_DIR", C.PROJECT_ROOT / "src" / "assets") / "icon.ico",
        getattr(C, "ASSETS_DIR", C.PROJECT_ROOT / "src" / "assets") / "icon.svg",
        C.PROJECT_ROOT / "icon.png",
        C.PROJECT_ROOT / "icon.ico",
        C.PROJECT_ROOT / "logo.svg",
        C.PROJECT_ROOT / "logo.png",
    ]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        cands.extend([
            pathlib.Path(meipass) / "icon.png",
            pathlib.Path(meipass) / "icon.ico",
            pathlib.Path(meipass) / "icon.svg",
            pathlib.Path(meipass) / "logo.svg",
        ])
    for c in cands:
        if c.exists():
            return str(c)
    return ""


def _make_tray_icon() -> QIcon:
    """托盘图标：优先使用高清应用图标，缺失时绘制兜底图标。"""
    icon_path = _find_logo()
    if icon_path:
        icon = QIcon(icon_path)
        if not icon.isNull():
            return icon
    # 兜底：深墨蓝底 + 品牌蓝"字"（与主题风格协调）
    from PySide6.QtGui import QColor, QPainter, QPixmap
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#202732"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(4, 4, 56, 56, 14, 14)
    p.setPen(QColor("#2C7DF8"))
    f = p.font()
    f.setPixelSize(30)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "字")
    p.end()
    return QIcon(pm)


def _export_to_disk(session: RecordingSession, settings: C.Settings):
    """把录制会话导出为 SRT + TXT 到「记录」目录。返回 (srt_path, txt_path, 句数)。"""
    from .recording import make_llm_fixer
    llm = None
    if settings.llm_endpoint:
        llm = make_llm_fixer(settings.llm_endpoint, settings.llm_model)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = C.PROJECT_ROOT / "recordings"
    srt_path = out_dir / f"subtitle_{stamp}.srt"
    txt_path = out_dir / f"subtitle_{stamp}.txt"
    n1 = session.export(srt_path, "srt", fix=True, llm_fix=llm)
    session.export(txt_path, "txt", fix=True, llm_fix=llm)
    return srt_path, txt_path, n1


def _run_demo(app: QApplication, window: SubtitleWindow):
    """演示模式：不采集音频，循环模拟"中间结果 → 断句完成"。"""
    idx = 0

    def tick():
        nonlocal idx
        t = DEMO_PHRASES[idx % len(DEMO_PHRASES)]
        mid = max(1, len(t) // 2)
        window.set_partial(t[:mid])
        QTimer.singleShot(700, lambda t=t: window.commit(t))
        idx += 1

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(2600)
    tick()


def run(settings: C.Settings, demo: bool = False) -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ReSubtitle")
    app.setStyle("Fusion")

    settings = C.load_settings(settings)
    window = SubtitleWindow(settings.ui)
    icon = _make_tray_icon()
    window.setWindowIcon(icon)
    if settings.window_pos:
        try:
            x, y = (int(v) for v in settings.window_pos.split(","))
            window.move(x, y)
        except (ValueError, TypeError):
            pass

    # ---------------- 状态 ----------------
    session = RecordingSession()
    pipeline = [None]          # 当前流水线（字幕关闭时为空）
    subtitle_on = [False]      # 字幕开关
    recording = [False]        # 记录开关（转录）

    # ---------------- 核心：字幕开关（F9） ----------------
    def _turn_off_subtitle():
        """关闭字幕并停止流水线（若记录中则一并结束保存）。"""
        if not subtitle_on[0]:
            return
        if recording[0]:
            recording[0] = False
            session.stop()
            window.recording_active = False
            _export_recording(show=False)
        if pipeline[0] is not None:
            pipeline[0].stop()
        pipeline[0] = None
        subtitle_on[0] = False
        window.subtitle_on = False
        window.commit("■ 字幕已关闭")
        _rebuild_tray_menu()
        print("[app] 字幕关闭")

    def _toggle_subtitle():
        if subtitle_on[0]:
            _turn_off_subtitle()
        else:
            # 开启字幕：启动流水线（模型首次加载需数秒）
            # 若处于预览模式则先退出预览（隔离：预览纯设置，字幕模式恢复自动淡出）
            if preview_active[0]:
                preview_active[0] = False
                window.preview_active = False
                C.save_settings(settings, window)
                print("[app] 预览模式退出（开启字幕）")
            model_dir = ensure_model()
            settings.asr_model_dir = str(model_dir)
            pipeline[0] = Pipeline(settings, window, session=session)
            pipeline[0].start()
            subtitle_on[0] = True
            window.subtitle_on = True
            window.show()
            window.commit("▶ 字幕已开启")
            tray.show()
            _rebuild_tray_menu()
            print("[app] 字幕开启")

    # ---------------- 附带：记录开关（F10，转录） ----------------
    # 记录带起的字幕（F10 自动开启）在记录结束时随之关闭淡出；
    # F9 独立开启的字幕不受记录影响。
    record_owns_subtitle = [False]

    def _toggle_record():
        if recording[0]:
            recording[0] = False
            session.stop()
            window.recording_active = False
            window.commit(f"■ 记录结束（{len(session.finals)} 句）")
            print(f"[recording] 记录结束：{len(session.finals)} 句")
            _rebuild_tray_menu()
            QTimer.singleShot(50, lambda: _export_recording(show=True))
            # 记录带起的字幕：显示结束信息后延迟关闭（自然淡出回后台）
            if record_owns_subtitle[0]:
                record_owns_subtitle[0] = False
                QTimer.singleShot(2500, _turn_off_subtitle)
        else:
            was_on = subtitle_on[0]
            if not subtitle_on[0]:
                _toggle_subtitle()          # 记录前确保字幕（流水线）在运行
            if not subtitle_on[0]:
                return
            record_owns_subtitle[0] = not was_on
            session.start()
            recording[0] = True
            window.recording_active = True
            window.show()
            window.commit("▶ 记录开始")
            _rebuild_tray_menu()
            print("[recording] 记录开始（F10）")

    # ---------------- 导出（非模态提示，绝不阻塞） ----------------
    def _export_recording(show: bool = True):
        if not session.finals:
            if show:
                box = QMessageBox(window)
                box.setWindowTitle("ReSubtitle")
                box.setText("本次没有记录到字幕")
                box.setStandardButtons(QMessageBox.Ok)
                box.setWindowModality(Qt.NonModal)
                box.show()
            return
        try:
            srt_path, _txt, n1 = _export_to_disk(session, settings)
        except OSError as e:
            box = QMessageBox(window)
            box.setWindowTitle("ReSubtitle")
            box.setText(f"导出失败：{e}")
            box.setStandardButtons(QMessageBox.Ok)
            box.setWindowModality(Qt.NonModal)
            box.show()
            return
        print(f"[recording] 已导出 {n1} 句 -> {srt_path}")
        if show:
            box = QMessageBox(window)
            box.setWindowTitle("ReSubtitle")
            box.setText(f"记录完成，已导出 {n1} 句：\n{srt_path}\n\n（同时已保存 TXT 文本版）")
            open_btn = box.addButton("打开文件夹", QMessageBox.AcceptRole)
            box.addButton(QMessageBox.Close)
            box.buttonClicked.connect(
                lambda btn: os.startfile(str(srt_path.parent)) if btn is open_btn else None)
            box.setWindowModality(Qt.NonModal)
            box.show()

    # ---------------- 窗口右键菜单信号 ----------------
    window.toggle_subtitle.connect(_toggle_subtitle)
    window.toggle_record.connect(_toggle_record)

    # ---------------- 系统托盘 ----------------
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip("ReSubtitle — 实时字幕")
    tray_menu = QMenu()
    preview_active = [False]

    def _quit_requested():
        window.quit_requested = True
        if recording[0]:
            recording[0] = False
            session.stop()
        if pipeline[0] is not None:
            pipeline[0].stop()
        pipeline[0] = None
        app.quit()

    def _open_preview():
        """预览设置模式：不加载模型，显示示例句子供调节配色/尺寸等；关闭窗口即保存。"""
        if preview_active[0]:
            return
        preview_active[0] = True
        window.preview_active = True
        window.clear()
        window.commit("▦ 预览模式：在字幕窗右键调整字体/配色/尺寸/透明度等")
        for t in DEMO_PHRASES[:2]:
            window.commit(t)
        window.set_partial("正在实时识别的中间结果示例，可在此调节配色与排版……")
        window.show()
        print("[app] 预览设置模式（关闭窗口即保存）")

    def _rebuild_tray_menu():
        tray_menu.clear()
        # 状态同步：开则显示"隐藏字幕"，关则显示"显示字幕"（开关语义不混淆）
        if subtitle_on[0]:
            tray_menu.addAction("隐藏字幕 (F9)", lambda: QTimer.singleShot(0, _toggle_subtitle))
        else:
            tray_menu.addAction("显示字幕 (F9)", lambda: QTimer.singleShot(0, _toggle_subtitle))
        tray_menu.addSeparator()
        if recording[0]:
            tray_menu.addAction("停止记录并保存 (F10)", lambda: QTimer.singleShot(0, _toggle_record))
        else:
            tray_menu.addAction("开始记录 (F10)", lambda: QTimer.singleShot(0, _toggle_record))
        tray_menu.addSeparator()
        tray_menu.addAction("选项…（预览调节）", _open_preview)
        tray_menu.addSeparator()
        tray_menu.addAction("退出", _quit_requested)

    _rebuild_tray_menu()
    tray.setContextMenu(tray_menu)
    tray.activated.connect(lambda reason: window.show()
                           if reason == QSystemTrayIcon.DoubleClick else None)
    tray.show()

    # 预览关闭 -> 保存配置
    window.preview_closed.connect(lambda: (C.save_settings(settings, window),
                                           preview_active.__setitem__(0, False)))

    # ---------------- 全局热键 ----------------
    hotkey_filter = None
    if not demo:
        hotkey_filter = _HotkeyFilter(_toggle_subtitle, _toggle_record)
        app.installNativeEventFilter(hotkey_filter)
        _register_hotkeys(settings)

    def _on_quit():
        if hotkey_filter is not None:
            app.removeNativeEventFilter(hotkey_filter)
            _unregister_hotkeys()
        C.save_settings(settings, window)

    app.aboutToQuit.connect(_on_quit)

    # ---------------- 演示模式 ----------------
    if demo:
        _run_demo(app, window)
        window.show()
        print("[demo] 演示模式运行中（模拟字幕）")

    return app.exec()


def selftest_gui(settings: C.Settings) -> int:
    """GUI 自测：构建窗口与右键菜单、验证热键过滤器后立即退出。"""
    try:
        app = QApplication(sys.argv)
        w = SubtitleWindow(settings.ui)
        menu = w._build_menu()
        fonts = w._cjk_fonts()
        devs = w._list_devices()
        filt = _HotkeyFilter(lambda: None, lambda: None)
        app.installNativeEventFilter(filt)
        app.removeNativeEventFilter(filt)
        icon = _make_tray_icon()
        print(f"[selftest-gui] 菜单构建 OK；中文字体 {len(fonts)} 个；回环设备 {len(devs)} 个；"
              f"热键过滤器 OK；图标 null={icon.isNull()}")
        menu.deleteLater()
        w.close()
        return 0
    except Exception:
        import traceback
        try:
            with open("selftest_gui_error.log", "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
        except Exception:
            pass
        return 2
