"""透明、可拖拽、置顶的类 CC 字幕叠加窗口（PySide6）。

- 窗口完全透明，仅绘制文字（可配描边色/填充色/中间结果色），每行底部可选半透明背景条
- 长文本自动按窗口宽度换行；固定行数时只绘制窗口内容纳得下的行数
- 右键菜单：监听设备 / 宽度滑条 / 透明度滑条 / 描边滑条 / 配色方案 / 自定义颜色 / 字体字号
- 左键拖拽 / 双击复位 / 无新文字自动淡出
"""
from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QLabel, QMenu, QSlider, QVBoxLayout, QWidget, QWidgetAction,
)

from . import config as C


class SubtitleWindow(QWidget):
    request_set_device = Signal(str)   # 请求切换监听设备（名称子串，空串=自动）
    toggle_subtitle = Signal()         # F9：字幕开关（显示/隐藏）
    toggle_record = Signal()           # F10：记录开关（开始/停止转录）
    preview_closed = Signal()          # 预览设置模式关闭（保存配置）

    def __init__(self, cfg: C.UIConfig, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.current_device_substr = ""        # 当前监听设备（用于菜单勾选显示）
        self.recording_active = False          # 记录状态（菜单项文字）
        self.subtitle_on = False               # 字幕状态（菜单项文字）
        self.quit_requested = False            # True=真正退出（托盘"退出"），否则关闭=隐藏到托盘
        self.preview_active = False            # 预览设置模式（关闭窗口=保存并退出预览）
        self._lines: list[tuple[str, bool]] = []   # (text, is_partial)，旧 -> 新
        self._drag_offset = None
        self._anim: QPropertyAnimation | None = None
        self._last_resize_ts = 0.0             # resize 防抖时间戳

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)   # 叠加窗不抢焦点
        self.setWindowOpacity(cfg.window_opacity)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)

        self._apply_geometry()

    # ------------------------------------------------------------------
    # 字体 / 布局工具
    # ------------------------------------------------------------------
    def _font(self) -> QFont:
        f = QFont(self.cfg.font_family)
        f.setPixelSize(self.cfg.font_size)
        f.setWeight(QFont.Weight.DemiBold)
        return f

    @staticmethod
    def _wrap_text(text: str, font: QFont, fm: QFontMetrics, max_w: int) -> list[str]:
        """按可用宽度做字符级折行（中英文混排均适用）。"""
        if not text:
            return []
        lines: list[str] = []
        cur = ""
        for ch in text:
            if cur and fm.horizontalAdvance(cur + ch) > max_w:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        if cur:
            lines.append(cur)
        return lines

    def _layout_lines(self) -> list[tuple[str, bool]]:
        """按当前窗口宽度折行，返回视觉顺序（旧 -> 新）的行列表。

        长文本超出 max_wrap_lines 时**保留最新行**（从新句、句内最新行优先累积，
        封顶后翻转）——窄窗口/长句下字幕始终显示最新内容，而不是卡在句子开头。
        """
        font = self._font()
        fm = QFontMetrics(font)
        max_w = max(60, self.width() - 2 * self.cfg.margin)
        newest_first: list[tuple[str, bool]] = []
        for text, is_partial in reversed(self._lines):        # 新句优先
            ws = self._wrap_text(text, font, fm, max_w)
            for wl in reversed(ws):                           # 句内最新行优先
                newest_first.append((wl, is_partial))
                if len(newest_first) >= self.cfg.max_wrap_lines:
                    return list(reversed(newest_first))       # 翻转回 旧->新
        return list(reversed(newest_first))

    def _apply_height(self):
        """窗口高度：固定行数或随内容自适应（保持底部边缘不动）。带 500ms 防抖，避免高频 resize。"""
        if self.cfg.fixed_height_lines > 0:
            n = self.cfg.fixed_height_lines
        else:
            n = max(1, len(self._layout_lines()))
        fm = QFontMetrics(self._font())
        line_h = fm.height() + self.cfg.line_spacing
        needed = n * line_h + 2 * self.cfg.margin - self.cfg.line_spacing
        if abs(self.height() - needed) <= 2:
            return
        import time as _t
        now = _t.monotonic()
        if now - self._last_resize_ts < 0.5:
            return                      # 防抖：高度最多滞后 0.5s
        self._last_resize_ts = now
        old_bottom = self.y() + self.height()
        self.resize(self.width(), needed)
        self.move(self.x(), old_bottom - needed)

    # ------------------------------------------------------------------
    # 几何 / 布局
    # ------------------------------------------------------------------
    def _apply_geometry(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        w = int(geo.width() * self.cfg.window_width_ratio)
        self.resize(w, 100)                  # 初始高度，随后按内容调整
        self._apply_height()
        x = geo.x() + (geo.width() - w) // 2
        y = geo.bottom() - self.height() - self.cfg.bottom_offset
        self.move(x, y)

    def _clamp_to_screen(self):
        screen = self.screen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        g = self.frameGeometry()
        x = min(max(g.x(), geo.left()), geo.right() - g.width() + 1)
        y = min(max(g.y(), geo.top()), geo.bottom() - g.height() + 1)
        self.move(x, y)

    # ------------------------------------------------------------------
    # 绘制：背景条 + 描边 + 填充（CC 字幕风格）
    # ------------------------------------------------------------------
    def paintEvent(self, event):  # noqa: N802
        lines = self._layout_lines()
        # 固定行数模式：只绘制窗口能容纳的行数（最新行优先），避免"多出半行"被裁剪
        if self.cfg.fixed_height_lines > 0:
            lines = lines[-self.cfg.fixed_height_lines:]

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        font = self._font()
        p.setFont(font)
        fm = QFontMetrics(font)
        line_h = fm.height() + self.cfg.line_spacing

        x = self.cfg.margin
        y = self.height() - self.cfg.margin
        bg_alpha = min(0.85, max(0.0, self.cfg.bg_alpha))
        outline_w = max(0.0, self.cfg.outline_width)

        for text, is_partial in reversed(lines):   # 从底部向上绘制（最新在底部）
            # 半透明背景条（条高 < 行距，上下留 2px 空隙，避免相邻行重叠）
            if bg_alpha > 0:
                tw = fm.horizontalAdvance(text)
                bar = QRectF(x - 12, y - fm.ascent() - 2, tw + 24, fm.height() + 4)
                bg = QColor(self.cfg.bg_color)
                bg.setAlphaF(bg_alpha)
                p.setPen(Qt.NoPen)
                p.setBrush(bg)
                p.drawRoundedRect(bar, self.cfg.bg_corner, self.cfg.bg_corner)

            color = QColor(self.cfg.partial_color if is_partial else self.cfg.text_color)
            if is_partial:
                color.setAlpha(220)

            path = QPainterPath()
            path.addText(x, y, font, text)
            if outline_w > 0:                    # 描边（0 = 无描边）
                pen = QPen(QColor(self.cfg.outline_color), outline_w)
                pen.setJoinStyle(Qt.RoundJoin)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawPath(path)
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawPath(path)          # 填充

            y -= line_h
        p.end()

    # ------------------------------------------------------------------
    # 文本更新接口（由 ASR 信号驱动）
    # ------------------------------------------------------------------
    def set_partial(self, text: str):
        """实时中间结果：替换当前 partial 行。传空串则清除。"""
        self._lines = [item for item in self._lines if not item[1]]
        if text:
            self._lines.append((text, True))
        self._poke()

    def commit(self, text: str):
        """一句话识别完成：固化为正式字幕行（超过 max_lines 自动归档旧句）。"""
        if not text:
            return
        self._lines = [item for item in self._lines if not item[1]]
        self._lines.append((text, False))
        del self._lines[:-self.cfg.max_lines]
        self._poke()

    def clear(self):
        self._lines.clear()
        self._poke()

    # ------------------------------------------------------------------
    # 显示 / 自动隐藏
    # ------------------------------------------------------------------
    def _poke(self):
        if self._anim is not None:
            self._anim.stop()
            self._anim = None
        self.setWindowOpacity(self.cfg.window_opacity)
        self._apply_height()
        if not self.isVisible():
            self.show()                # 已显示时跳过，避免重复 show 开销
        self.update()
        if not self.preview_active:    # 预览模式保持显示，不自动淡出
            self._hide_timer.start(self.cfg.idle_hide_ms)

    def _fade_out(self):
        if not self.isVisible():
            return
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.setDuration(self.cfg.fade_ms)
        self._anim.setStartValue(self.windowOpacity())
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self._after_fade)
        self._anim.start()

    def _after_fade(self):
        self._anim = None
        self.hide()
        self.setWindowOpacity(self.cfg.window_opacity)

    # ------------------------------------------------------------------
    # 鼠标交互
    # ------------------------------------------------------------------
    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton:
            self._drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        elif e.button() == Qt.RightButton:
            self._show_menu(e.globalPosition().toPoint())
        self._poke()

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._drag_offset is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_offset)
            self._clamp_to_screen()

    def mouseReleaseEvent(self, e):  # noqa: N802
        self._drag_offset = None

    def mouseDoubleClickEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton:
            self._apply_geometry()

    def closeEvent(self, e):  # noqa: N802
        """关闭窗口：
        - 预览设置模式：保存配置并退出预览（无感确认）
        - 普通模式：隐藏到系统托盘（常驻后台）；托盘"退出"才真正关闭。
        """
        if self.preview_active:
            self.preview_active = False
            self.hide()
            self.preview_closed.emit()
            e.accept()
            return
        if not self.quit_requested:
            e.ignore()
            self.hide()
        else:
            e.accept()

    # ------------------------------------------------------------------
    # 右键菜单
    # ------------------------------------------------------------------
    @staticmethod
    def _color_icon(hex_color: str, size: int = 16) -> QIcon:
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(hex_color))
        p.setPen(QColor("#000000"))
        p.drawRoundedRect(0, 0, size - 1, size - 1, 3, 3)
        p.end()
        return QIcon(pm)

    @staticmethod
    def _cjk_fonts() -> list[str]:
        db = QFontDatabase.families()
        known = [
            "Microsoft YaHei UI", "Microsoft YaHei", "SimHei", "SimSun", "NSimSun",
            "KaiTi", "FangSong", "DengXian", "Microsoft JhengHei",
            "Noto Sans CJK SC", "Source Han Sans SC",
            "STXihei", "STKaiti", "STSong", "STZhongsong",
        ]
        out = [f for f in known if f in db]
        for f in db:
            if f not in out and any("\u4e00" <= ch <= "\u9fff" for ch in f):
                out.append(f)
        return out

    def _list_devices(self) -> list[str]:
        try:
            import soundcard as sc
            return [m.name for m in sc.all_microphones(include_loopback=True)]
        except Exception:
            return []

    def _slider_action(self, menu: QMenu, title: str, lo: int, hi: int, cur: int,
                       callback, suffix: str = "") -> QWidgetAction:
        """在菜单中内嵌一个滑条（无极调节，实时生效）。"""
        wa = QWidgetAction(menu)
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(2)
        lab = QLabel(f"{title}: {cur}{suffix}")
        s = QSlider(Qt.Horizontal)
        s.setRange(lo, hi)
        s.setValue(cur)

        def on_change(v: int):
            lab.setText(f"{title}: {v}{suffix}")
            callback(v)

        s.valueChanged.connect(on_change)
        lay.addWidget(lab)
        lay.addWidget(s)
        wa.setDefaultWidget(box)
        menu.addAction(wa)
        return wa

    def _build_menu(self) -> QMenu:
        """构建右键菜单（拆出以便自测）。"""
        m = QMenu(self)

        # ---- 预览设置模式：提供明确的退出途径 ----
        if self.preview_active:
            m.addAction("✓ 完成预览并保存", self.close)
            m.addSeparator()

        # ---- 实时字幕（核心）与转录记录（附带） ----
        sub_act = m.addAction("隐藏字幕 (F9)" if self.subtitle_on else "显示字幕 (F9)")
        sub_act.triggered.connect(self.toggle_subtitle.emit)
        rec_act = m.addAction("停止记录并保存 (F10)" if self.recording_active else "开始记录 (F10)")
        rec_act.triggered.connect(self.toggle_record.emit)
        m.addSeparator()

        # ---- 监听设备 ----
        dev = m.addMenu("监听设备")
        auto = dev.addAction("跟随默认输出（自动）")
        auto.setCheckable(True)
        auto.setChecked(not self.current_device_substr)
        auto.triggered.connect(lambda: self.request_set_device.emit(""))
        for name in self._list_devices():
            act = dev.addAction(name)
            act.setCheckable(True)
            act.setChecked(bool(self.current_device_substr) and self.current_device_substr in name)
            act.triggered.connect(lambda _, n=name: self.request_set_device.emit(n))

        # ---- 无极滑条：宽度 / 透明度 / 描边 / 字号 ----
        self._slider_action(m, "窗口宽度", 30, 100, int(self.cfg.window_width_ratio * 100),
                            lambda v: self._set_width_ratio(v / 100.0), "%")
        self._slider_action(m, "背景不透明度", 0, 85, int(self.cfg.bg_alpha * 100),
                            lambda v: self._set_bg_alpha(v / 100.0), "%")
        self._slider_action(m, "描边粗细", 0, 10, int(self.cfg.outline_width),
                            lambda v: self._set_outline_width(v), "px")
        self._slider_action(m, "字号", 14, 64, self.cfg.font_size,
                            lambda v: self._set_size(v), "pt")

        # ---- 窗口高度（离散档位） ----
        hm = m.addMenu("窗口高度")
        for lines in self.cfg.height_presets:
            label = "自动" if lines == 0 else f"{lines} 行"
            act = hm.addAction(label)
            act.setCheckable(True)
            act.setChecked(lines == self.cfg.fixed_height_lines)
            act.triggered.connect(lambda _, l=lines: self._set_height_lines(l))

        # ---- 配色方案（一键套用） ----
        cm = m.addMenu("配色方案")
        for name, (fill, partial, outline) in C.COLOR_SCHEMES.items():
            act = cm.addAction(name)
            act.setIcon(self._color_icon(fill))
            act.triggered.connect(lambda _, n=name: self._apply_scheme(n))

        # ---- 自定义颜色：填充 / 中间结果 / 描边 ----
        def _add_color_submenu(parent: QMenu, title: str, current: str, setter):
            sm = parent.addMenu(title)
            for cname, chex in C.COLOR_PICKER.items():
                act = sm.addAction(cname)
                act.setIcon(self._color_icon(chex))
                act.setCheckable(True)
                act.setChecked(chex.lower() == current.lower())
                act.triggered.connect(lambda _, h=chex: setter(h))
            return sm

        _add_color_submenu(m, "填充颜色", self.cfg.text_color, self._set_text_color)
        _add_color_submenu(m, "中间颜色", self.cfg.partial_color, self._set_partial_color)
        _add_color_submenu(m, "描边颜色", self.cfg.outline_color, self._set_outline_color)

        # ---- 字体 ----
        fm = m.addMenu("字体")
        for fam in self._cjk_fonts():
            a = fm.addAction(fam)
            a.setCheckable(True)
            a.setChecked(fam == self.cfg.font_family)
            a.triggered.connect(lambda _, f=fam: self._set_font(f))

        m.addSeparator()
        m.addAction("重置位置", self._apply_geometry)
        act = m.addAction("固定在最前")
        act.setCheckable(True)
        act.setChecked(bool(self.windowFlags() & Qt.WindowStaysOnTopHint))
        act.toggled.connect(self._toggle_top)
        m.addSeparator()

        def _quit_app():
            self.quit_requested = True
            QApplication.instance().quit()

        m.addAction("退出程序", _quit_app)
        return m

    def _show_menu(self, pos):
        self._build_menu().exec(pos)

    # ---- 各设置项 ----
    def _set_width_ratio(self, ratio: float):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        self.cfg.window_width_ratio = min(1.0, max(0.2, ratio))
        geo = screen.availableGeometry()
        w = int(geo.width() * self.cfg.window_width_ratio)
        bottom = self.y() + self.height()
        x = geo.x() + (geo.width() - w) // 2
        self.setGeometry(x, bottom - self.height(), w, self.height())
        self._apply_height()
        self.update()

    def _set_height_lines(self, lines: int):
        self.cfg.fixed_height_lines = max(0, int(lines))
        self._apply_height()
        self.update()

    def _set_bg_alpha(self, a: float):
        self.cfg.bg_alpha = min(0.85, max(0.0, a))
        self.update()

    def _set_outline_width(self, w: float):
        self.cfg.outline_width = max(0.0, float(w))
        self.update()

    def _apply_scheme(self, name: str):
        if name in C.COLOR_SCHEMES:
            fill, partial, outline = C.COLOR_SCHEMES[name]
            self.cfg.text_color = fill
            self.cfg.partial_color = partial
            self.cfg.outline_color = outline
            self.update()

    def _set_text_color(self, h: str):
        self.cfg.text_color = h
        self.update()

    def _set_partial_color(self, h: str):
        self.cfg.partial_color = h
        self.update()

    def _set_outline_color(self, h: str):
        self.cfg.outline_color = h
        self.update()

    def _set_font(self, fam: str):
        self.cfg.font_family = fam
        self._apply_height()
        self.update()

    def _set_size(self, s: int):
        self.cfg.font_size = int(s)
        self._apply_height()
        self.update()

    def _toggle_top(self, on: bool):
        flags = self.windowFlags()
        if on:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()
