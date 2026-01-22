#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""文件自动重命名工具（GUI）

在原版（rename_files_gui.py）基础上做了代码与界面的系统优化：
- 线程安全：后台线程只做文件操作，通过 Queue 给主线程发 UI 事件
- 更稳健的“已有日期前缀”判断：匹配 ^\\d{8}_
- 新增：递归子文件夹、仅预览(Dry-run)、取消处理、进度条与状态栏
- 界面：响应式布局、更一致的间距/字体、按钮 hover

依赖：tkinterdnd2
"""

from __future__ import annotations

__version__ = "2.0"

import os
import re
import time
import queue
import threading
from dataclasses import dataclass
from datetime import datetime
import difflib
import json
import sqlite3
import subprocess
import shutil
from uuid import uuid4
from pathlib import Path

# Optional: EXIF support for photos (Pillow). If unavailable, EXIF mode falls back to mtime.
try:
    from PIL import Image, ExifTags  # type: ignore
except Exception:  # pragma: no cover
    Image = None  # type: ignore
    ExifTags = None  # type: ignore

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import tkinter.font as tkfont


# Optional: drag & drop support via tkinterdnd2. If unavailable, the app still runs (without DnD).
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore
    _BaseTk = TkinterDnD.Tk
except Exception:  # pragma: no cover
    DND_FILES = None  # type: ignore
    _BaseTk = tk.Tk


# ------------------------- Theme -------------------------
COLORS = {
    # Backgrounds
    'bg_main': '#F3F4FF',         # soft lavender like the reference UI
    'bg_card': '#FFFFFF',
    'bg_drop': '#EEF1FF',
    'bg_drop_hover': '#E5E9FF',

    # Accents
    'bg_button': '#6C5CE7',       # primary purple
    'bg_button_hover': '#5847D6',
    'bg_danger': '#FF5C8A',       # soft pink/red
    'bg_danger_hover': '#E84C79',

    # Text
    'text_primary': '#1C1B1F',
    'text_secondary': '#6E6C7A',
    'text_button': '#FFFFFF',

    # Lines / misc
    'border': '#E3E6F0',

    # Soft shadows (3-layer faux box-shadow)
    'shadow_1': '#E1E4FA',
    'shadow_2': '#E9EBFD',
    'shadow_3': '#F0F2FF',
    'shadow': '#DADCF0',

    # Status
    'success': '#2ECC71',
    'warning': '#F5A623',
    'error': '#FF4D4F',

    # Scrollbars (single-color pill look)
    'scroll_thumb': '#C7C9D9',
    'scroll_thumb_hover': '#B1B3C5',
}


TEXTS = {
    'zh': {
        'title': '文件自动重命名',
        'subtitle': '根据所选时间添加日期前缀',
        'drop_area': '拖放文件夹或单个文件到这里\n或点击选择',
        'pick_folder': '选择文件夹',
        'pick_file': '选择文件',
        'pick_hint': '或',
        'selected_folder': '已选择文件夹：{}',
        'selected_file': '已选择文件：{}',
        'start_process': '开始处理',
        'cancel': '取消',
        'clear_log': '清空日志',
        'undo_last': '撤销上一次',
        'undo_confirm_title': '撤销确认',
        'undo_confirm_msg': '将撤销上一次改名操作（共 {n} 个文件）。继续吗？',
        'undo_no_history': '没有可撤销的记录。',
        'undo_started': '开始撤销上一次操作（共 {n} 个文件）…',
        'undo_skip_missing': '撤销跳过：找不到 {}',
        'undo_skip_conflict': '撤销跳过：已存在 {}，无法恢复 {}',
        'undo_success': '↩ {} → {}',
        'undo_error': "撤销错误：处理 '{}' 时出错：{}",
        'undo_dialog_title': '撤销完成',
        'undo_ok_label': '已恢复',
        'undo_skip_label': '撤销跳过',
        'undo_cancelled': '撤销已取消。',
        'status_undoing': '撤销中：{}/{}',
        'options': '选项',
        'include_subfolders': '包含子文件夹',
        'dry_run': '仅预览（不真正重命名）',
        'date_source': '日期来源',
        'date_source_mtime': '修改时间（mtime）',
        'date_source_ctime': '创建时间（ctime）',
        'date_source_exif': 'EXIF 拍摄时间',
        'source_mtime': 'mtime',
        'source_ctime': 'ctime',
        'source_exif': 'EXIF',
        'summary_prefix_source': '日期前缀（{source}）',
        'summary_exif_fallback': 'EXIF→mtime',
        'summary_meta_fallback': 'META→mtime',
        'summary_meta_fallback': '元数据→mtime',
        'exif_missing_fallback': 'EXIF 缺失：使用修改时间（mtime）',
        'exif_unavailable_fallback': '无法读取 EXIF：使用修改时间（mtime）',
        'meta_missing_fallback': '元数据缺失：使用修改时间（mtime）',
        'meta_unavailable_fallback': '无法读取元数据：使用修改时间（mtime）',
        'filters': '过滤器',
        'filters_clear': '清空',
        'filter_exts': '扩展名（逗号/空格分隔）',
        'filter_include': '包含关键词（文件名包含）',
        'filter_exclude': '排除关键词（文件名包含）',
        'no_files_after_filter': '筛选后没有匹配的文件。',
        'filter_summary': '过滤器：从 {before} 个文件中筛选出 {after} 个（排除 {filtered} 个）',
        'filtered_label': '过滤排除',
        'conflict_unknown': '预计冲突：—',
        'conflict_calc': '预计冲突：计算中…',
        'conflict_estimate': '预计冲突：{n} 项',
        'conflict_view': '查看列表',
        'conflict_preview_title': '冲突预览',
        'conflict_preview_subtitle': '以下文件的目标名已存在，已按 _001/_002 规则自动编号：',
        'conflict_col_folder': '文件夹',
        'conflict_col_original': '原文件名',
        'conflict_col_base': '目标名（未编号）',
        'conflict_col_final': '最终名（自动编号）',
        'conflict_resolved': '冲突：{} 已存在，自动编号为：{}',
        'conflict_label': '冲突已处理',
        'preview_button': 'Diff 预览',
        'preview_title': '改名预览（Diff）',
        'preview_subtitle': '开始前确认将要发生的改名；支持搜索、只看变化/冲突；点击行可查看高亮差异。',
        'preview_search': '搜索',
        'preview_only_changed': '只看有变化的',
        'preview_only_conflict': '只看冲突的',
        'preview_col_old': '原文件名',
        'preview_col_new': '新文件名',
        'preview_col_summary': '变化摘要',
        'preview_count': '显示 {shown}/{total}',
        'preview_calculating': '正在计算预览…',
        'preview_no_data': '没有可预览的数据。',
        'summary_prefix': '日期前缀',
        'summary_auto_index': '自动序号 {suffix}',
        'summary_skip_prefix': '跳过：已有日期前缀',
        'log_title': '处理日志',
        'status_ready': '就绪',
        'status_idle': '就绪',
        'status_processing': '处理中：{}/{}',
        'status_cancelled': '已取消',
        'processing_single': '处理单个文件：{}',
        'processing_folder': '找到 {} 个文件，开始处理…',
        'no_files': '文件夹中没有文件。',
        'skip': '跳过：{}（已有日期前缀）',
        'warning_exists': '已存在：{}，跳过：{}',
        'preview_rename': '预览：{} → {}',
        'success_rename': '✓ {} → {}',
        'error': "错误：处理 '{}' 时出错：{}",
        'processing_complete': '处理完成！',
        'processing_cancelled': '处理已取消。',
        'dialog_title': '处理完成',
        'dialog_title_cancel': '已取消',
        'success_rename_label': '成功重命名',
        'skip_label': '跳过',
        'error_label': '错误',
        'time_label': '处理用时',
        'time_unit': ' 秒',
        'close': '关闭',
        'language_switch': 'English',
        'select_type_title': '选择类型',
        'select_type_message': '选择文件还是文件夹？\n\n点击“是”选择文件夹\n点击“否”选择单个文件',
        'select_folder_title': '选择要处理的文件夹',
        'select_file_title': '选择要处理的文件',
        'error_path_not_exist': '路径不存在：\n{}',
        'error_invalid_path': '无效的路径：\n{}',
        'drop_multi': '检测到多个拖放项，仅使用第一个：{}',
    },
    'en': {
        'title': 'File Auto Rename',
        'subtitle': 'Add date prefix based on selected time source (YYYYMMDD_)',
        'drop_area': 'Drag & drop a folder or a file here\nor click to select',
        'pick_folder': 'Choose Folder',
        'pick_file': 'Choose File',
        'pick_hint': 'or',
        'selected_folder': 'Selected folder: {}',
        'selected_file': 'Selected file: {}',
        'start_process': 'Start',
        'cancel': 'Cancel',
        'clear_log': 'Clear Log',
        'undo_last': 'Undo last',
        'undo_confirm_title': 'Undo',
        'undo_confirm_msg': 'Undo the last rename operation ({n} files). Continue?',
        'undo_no_history': 'No undo history available.',
        'undo_started': 'Undoing last operation ({n} files)…',
        'undo_skip_missing': 'Undo skip: missing {}',
        'undo_skip_conflict': 'Undo skip: {} exists, cannot restore {}',
        'undo_success': '↩ {} → {}',
        'undo_error': "Undo error processing '{}': {}",
        'undo_dialog_title': 'Undo complete',
        'undo_ok_label': 'Restored',
        'undo_skip_label': 'Skipped',
        'undo_cancelled': 'Undo cancelled.',
        'status_undoing': 'Undoing: {}/{}',
        'options': 'Options',
        'include_subfolders': 'Include subfolders',
        'dry_run': 'Dry-run (no rename)',
        'date_source': 'Date source',
        'date_source_mtime': 'Modified time (mtime)',
        'date_source_ctime': 'Created time (ctime)',
        'date_source_exif': 'EXIF taken time',
        'source_mtime': 'mtime',
        'source_ctime': 'ctime',
        'source_exif': 'EXIF',
        'summary_prefix_source': 'Date prefix ({source})',
        'summary_exif_fallback': 'EXIF→mtime',
        'exif_missing_fallback': 'EXIF missing: using modified time (mtime)',
        'exif_unavailable_fallback': 'Cannot read EXIF: using modified time (mtime)',
        'meta_missing_fallback': 'Metadata missing: using modified time (mtime)',
        'meta_unavailable_fallback': 'Cannot read metadata: using modified time (mtime)',

        'filters': 'Filters',
        'filters_clear': 'Clear',
        'filter_exts': 'Extensions (e.g. jpg,png,pdf)',
        'filter_include': 'Contains',
        'filter_exclude': 'Excludes',
        'no_files_after_filter': 'No files match the filters.',
        'filter_summary': 'Filters: {after} matched out of {before} (excluded {filtered})',
        'filtered_label': 'Filtered out',
        'conflict_unknown': 'Expected conflicts: —',
        'conflict_calc': 'Expected conflicts: calculating…',
        'conflict_estimate': 'Expected conflicts: {n}',
        'conflict_view': 'View',
        'conflict_preview_title': 'Conflict Preview',
        'conflict_preview_subtitle': 'These files had name conflicts. Auto-numbered with _001/_002:',
        'conflict_col_folder': 'Folder',
        'conflict_col_original': 'Original',
        'conflict_col_base': 'Target (base)',
        'conflict_col_final': 'Target (final)',
        'conflict_resolved': 'Conflict: {} exists, auto-numbered to: {}',
        'conflict_label': 'Conflicts handled',
        'preview_button': 'Diff Preview',
        'preview_title': 'Rename Preview (Diff)',
        'preview_subtitle': 'Review changes before applying. Supports search, only-changed/only-conflict. Select a row to see highlighted diff.',
        'preview_search': 'Search',
        'preview_only_changed': 'Only changed',
        'preview_only_conflict': 'Only conflicts',
        'preview_col_old': 'Original',
        'preview_col_new': 'New',
        'preview_col_summary': 'Summary',
        'preview_count': 'Showing {shown}/{total}',
        'preview_calculating': 'Calculating preview…',
        'preview_no_data': 'No preview data.',
        'summary_prefix': 'Date prefix',
        'summary_auto_index': 'Auto index {suffix}',
        'summary_skip_prefix': 'Skip: already has date prefix',
        'log_title': 'Processing Log',
        'status_ready': 'Ready',
        'status_idle': 'Ready',
        'status_processing': 'Processing: {}/{}',
        'status_cancelled': 'Cancelled',
        'processing_single': 'Processing single file: {}',
        'processing_folder': 'Found {} files, starting…',
        'no_files': 'No files in folder.',
        'skip': 'Skip: {} (already has date prefix)',
        'warning_exists': 'Exists: {}, skipping: {}',
        'preview_rename': 'Preview: {} → {}',
        'success_rename': '✓ {} → {}',
        'error': "Error processing '{}': {}",
        'processing_complete': 'Processing complete!',
        'processing_cancelled': 'Cancelled.',
        'dialog_title': 'Done',
        'dialog_title_cancel': 'Cancelled',
        'success_rename_label': 'Renamed',
        'skip_label': 'Skipped',
        'error_label': 'Errors',
        'time_label': 'Time',
        'time_unit': ' seconds',
        'close': 'Close',
        'language_switch': '中文',
        'select_type_title': 'Select Type',
        'select_type_message': 'Select file or folder?\n\nClick Yes for folder\nClick No for single file',
        'select_folder_title': 'Select folder',
        'select_file_title': 'Select file',
        'error_path_not_exist': 'Path does not exist:\n{}',
        'error_invalid_path': 'Invalid path:\n{}',
        'drop_multi': 'Multiple items dropped. Using the first: {}',
    },
}



# ========================= UI Skin Layer =========================
# 只想改“外观（颜色/字体/间距/圆角/阴影）”的时候，尽量只改这里：
# - COLORS：色板
# - UI_METRICS：尺寸/间距/字号
# - SkinLayer：把窗口设置、字体选择、ttk 样式集中在一起（不碰重命名逻辑）

@dataclass(frozen=True)
class UIMetrics:
    # Window
    window_w: int = 1200
    window_h: int = 820
    min_w: int = 1080
    min_h: int = 700

    # Common paddings
    page_pad_x: int = 24
    page_pad_y: int = 20
    section_gap_y: int = 12

    # Typography
    title_size: int = 26
    subtitle_size: int = 12
    body_size: int = 11
    small_size: int = 10

    # Radii
    card_radius: int = 16
    pill_radius: int = 16

    # Controls
    progress_thickness: int = 10
    tree_rowheight: int = 26
    scrollbar_width: int = 10
    round_indicator_size: int = 16


UI_METRICS = UIMetrics()


class SkinLayer:
    """集中管理 UI 皮肤层：字体、窗口尺寸、ttk 样式、圆形勾选框等。"""

    def __init__(self, language: str = 'zh', colors: dict[str, str] | None = None, metrics: UIMetrics = UI_METRICS):
        self.language = language
        self.colors = colors or COLORS
        self.metrics = metrics
        self.font_zh = 'Arial'
        self.font_en = 'Arial'

    # ---- fonts ----
    def init_fonts(self, root: tk.Tk) -> None:
        try:
            families = set(tkfont.families(root))
        except Exception:
            families = set()

        def pick(cands: list[str], fallback: str) -> str:
            for c in cands:
                if c in families:
                    return c
            return fallback

        self.font_zh = pick(
            ['Microsoft YaHei UI', 'Microsoft YaHei', 'PingFang SC', 'Noto Sans CJK SC', 'SimHei', '等线', 'Arial'],
            'Arial',
        )
        self.font_en = pick(['Segoe UI', 'Arial', 'Helvetica'], 'Arial')

    def font(self, size: int, weight: str = 'normal'):
        family = self.font_zh if self.language == 'zh' else self.font_en
        return (family, size, weight)

    # ---- window ----
    def apply_window(self, root: tk.Tk, title: str) -> None:
        root.title(title)
        root.configure(bg=self.colors['bg_main'])
        root.geometry(f"{self.metrics.window_w}x{self.metrics.window_h}")
        root.minsize(self.metrics.min_w, self.metrics.min_h)

    # ---- ttk style ----
    def apply_ttk_style(self, root: tk.Tk) -> None:
        """ttk 样式：尽量做成干净、扁平、低对比的 Apple 风格。"""
        try:
            style = ttk.Style(root)
            if 'clam' in style.theme_names():
                style.theme_use('clam')

            self.ensure_round_checkbuttons(root, style)

            style.configure('TCheckbutton', background=self.colors['bg_main'], font=self.font(self.metrics.body_size))
            style.configure('Card.TCheckbutton', background=self.colors['bg_card'], font=self.font(self.metrics.body_size))

            style.configure('TProgressbar', thickness=self.metrics.progress_thickness)

            # Scrollbar：单色胶囊感（去掉箭头，缩窄宽度）
            style.layout(
                'Pill.Vertical.TScrollbar',
                [('Vertical.Scrollbar.trough', {
                    'sticky': 'ns',
                    'children': [('Vertical.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})]
                })]
            )
            style.configure(
                'Pill.Vertical.TScrollbar',
                troughcolor=self.colors['bg_main'],
                background=self.colors['scroll_thumb'],
                bordercolor=self.colors['bg_main'],
                lightcolor=self.colors['bg_main'],
                darkcolor=self.colors['bg_main'],
                arrowcolor=self.colors['bg_main'],
                gripcount=0,
                width=self.metrics.scrollbar_width,
            )
            style.map(
                'Pill.Vertical.TScrollbar',
                background=[('active', self.colors['scroll_thumb_hover'])]
            )

            style.configure(
                'Treeview',
                background=self.colors['bg_card'],
                fieldbackground=self.colors['bg_card'],
                foreground=self.colors['text_primary'],
                borderwidth=0,
                relief='flat',
                font=self.font(self.metrics.small_size),
                rowheight=self.metrics.tree_rowheight,
            )
            style.map(
                'Treeview',
                background=[('selected', '#DCEBFF')],
                foreground=[('selected', self.colors['text_primary'])],
            )

            style.configure(
                'Treeview.Heading',
                background=self.colors['bg_main'],
                foreground=self.colors['text_secondary'],
                relief='flat',
                font=self.font(self.metrics.body_size, 'bold'),
                padding=(10, 8),
            )
            style.map('Treeview.Heading', background=[('active', self.colors['bg_main'])])
        except Exception:
            pass

    def ensure_round_checkbuttons(self, root: tk.Tk, style: ttk.Style) -> None:
        """把默认方形勾选框替换成“圆形 + 主题色圆点”的指示器（仍然是 Checkbutton 行为）。"""
        if getattr(root, '_round_cb_ready', False):
            return

        c = self.colors
        size = self.metrics.round_indicator_size

        def make_images(bg: str, outline: str, dot: str, outline_dis: str, dot_dis: str):
            imgs = [tk.PhotoImage(master=root, width=size, height=size) for _ in range(4)]
            for im in imgs:
                im.put(bg, to=(0, 0, size, size))

            cx = cy = size / 2.0
            radius = size / 2.0 - 2.0
            thick = 1.15
            dot_r = max(2.0, radius * 0.45)

            for y in range(size):
                for x in range(size):
                    dx = (x + 0.5) - cx
                    dy = (y + 0.5) - cy
                    d = (dx * dx + dy * dy) ** 0.5

                    if abs(d - radius) <= thick:
                        imgs[0].put(outline, (x, y))
                        imgs[1].put(outline, (x, y))
                        imgs[2].put(outline_dis, (x, y))
                        imgs[3].put(outline_dis, (x, y))
                        continue

                    if d <= dot_r:
                        imgs[1].put(dot, (x, y))
                        imgs[3].put(dot_dis, (x, y))

            return imgs[0], imgs[1], imgs[2], imgs[3]

        off_card, on_card, off_card_dis, on_card_dis = make_images(
            c['bg_card'], c['border'], c['bg_button'], c['scroll_thumb'], c['scroll_thumb']
        )
        off_main, on_main, off_main_dis, on_main_dis = make_images(
            c['bg_main'], c['border'], c['bg_button'], c['scroll_thumb'], c['scroll_thumb']
        )

        # 防止图片被垃圾回收
        root._round_cb_imgs = (off_card, on_card, off_card_dis, on_card_dis, off_main, on_main, off_main_dis, on_main_dis)

        try:
            style.element_create(
                'RoundCard.indicator',
                'image',
                off_card,
                ('selected', on_card),
                ('disabled', off_card_dis),
                ('selected', 'disabled', on_card_dis),
            )
        except tk.TclError:
            pass

        try:
            style.element_create(
                'RoundMain.indicator',
                'image',
                off_main,
                ('selected', on_main),
                ('disabled', off_main_dis),
                ('selected', 'disabled', on_main_dis),
            )
        except tk.TclError:
            pass

        layout_card = [
            ('Checkbutton.padding', {
                'sticky': 'nswe',
                'children': [
                    ('RoundCard.indicator', {'side': 'left', 'sticky': '', 'padx': (0, 6)}),
                    ('Checkbutton.focus', {
                        'side': 'left',
                        'sticky': 'w',
                        'children': [('Checkbutton.label', {'sticky': 'nswe'})]
                    }),
                ]
            }),
        ]
        layout_main = [
            ('Checkbutton.padding', {
                'sticky': 'nswe',
                'children': [
                    ('RoundMain.indicator', {'side': 'left', 'sticky': '', 'padx': (0, 6)}),
                    ('Checkbutton.focus', {
                        'side': 'left',
                        'sticky': 'w',
                        'children': [('Checkbutton.label', {'sticky': 'nswe'})]
                    }),
                ]
            }),
        ]

        try:
            style.layout('Card.TCheckbutton', layout_card)
        except tk.TclError:
            pass
        try:
            style.layout('TCheckbutton', layout_main)
        except tk.TclError:
            pass

        try:
            style.configure('Card.TCheckbutton', foreground=c['text_primary'])
            style.map('Card.TCheckbutton', foreground=[('disabled', c['text_secondary'])])
            style.configure('TCheckbutton', foreground=c['text_primary'])
            style.map('TCheckbutton', foreground=[('disabled', c['text_secondary'])])
        except Exception:
            pass

        root._round_cb_ready = True

# ------------------------- Helpers -------------------------
DATE_PREFIX_RE = re.compile(r'^\d{8}_')


@dataclass(frozen=True)
class RenameOptions:
    include_subfolders: bool = False
    dry_run: bool = False
    date_source: str = 'mtime'  # mtime / ctime / exif
    filter_exts: str = ''
    filter_include: str = ''
    filter_exclude: str = ''


@dataclass
class RenameResult:
    renamed: int = 0
    skipped: int = 0
    filtered: int = 0
    conflicts: int = 0
    errors: int = 0
    elapsed: float = 0.0
    total: int = 0
    cancelled: bool = False




@dataclass
class UndoResult:
    restored: int = 0
    skipped: int = 0
    errors: int = 0
    elapsed: float = 0.0
    total: int = 0
    cancelled: bool = False
    no_history: bool = False


@dataclass
class PlanItem:
    path: Path
    original_name: str
    base_name: str | None = None
    final_name: str | None = None
    status: str = 'rename'  # rename / skip_prefix / skip_filter / error
    note_code: str | None = None
    conflict_index: int = 0
    summary: str = ''
    error: str | None = None

    @property
    def changed(self) -> bool:
        return (self.final_name is not None) and (self.final_name != self.original_name)


@dataclass
class RenamePlan:
    items: list[PlanItem]
    scanned: int
    matched: int
    filtered_out: int
    scan_errors: list[str]
    cancelled: bool = False

def _has_any_date_prefix(filename: str) -> bool:
    """判断文件名是否已带任意日期前缀（YYYYMMDD_）"""
    return bool(DATE_PREFIX_RE.match(filename))


def _parse_dnd_paths(tk_root: tk.Tk, data: str) -> list[str]:
    """解析 TkinterDnD 的拖放 data（可能包含 { } 以及多个路径）"""
    raw = tk_root.tk.splitlist(data)
    paths: list[str] = []
    for p in raw:
        p = p.strip('{}')
        if p:
            paths.append(p)
    return paths


def _bind_hover(btn: tk.Widget, normal_bg: str, hover_bg: str) -> None:
    def _on_enter(_):
        if str(btn['state']) != 'disabled':
            btn.configure(bg=hover_bg)

    def _on_leave(_):
        if str(btn['state']) != 'disabled':
            btn.configure(bg=normal_bg)

    btn.bind('<Enter>', _on_enter)
    btn.bind('<Leave>', _on_leave)


def _parse_exts(raw: str) -> set[str]:
    """Parse extension filter like 'jpg,png,.pdf' into a set of lower-case suffixes (with leading dots)."""
    raw = (raw or '').strip()
    if not raw:
        return set()
    parts = re.split(r"[\s,;]+", raw)
    exts: set[str] = set()
    for p in parts:
        p = p.strip().lower()
        if not p:
            continue
        if p == '*':
            return set()
        if not p.startswith('.'):
            p = '.' + p
        exts.add(p)
    return exts


def _is_windows() -> bool:
    return os.name == 'nt'


def _name_key(name: str) -> str:
    """Normalize filename for comparisons.

    Windows is case-insensitive by default; use casefold() to make conflict
    detection and auto-indexing consistent across machines.
    """
    return name.casefold() if _is_windows() else name


def _win_extended_path(path_str: str) -> str:
    """Return a Windows extended-length path (\\?\ prefix) when needed.

    This improves robustness for long paths on Windows.
    """
    if not _is_windows():
        return path_str

    p = os.path.abspath(path_str)
    # Already extended?
    if p.startswith('\\\\?\\'):
        return p
    # UNC path: \\server\share\...
    if p.startswith('\\\\'):
        return '\\\\?\\UNC\\' + p.lstrip('\\')
    return '\\\\?\\' + p


def _safe_rename(src: Path, dst: Path) -> None:
    """Robust rename with Windows long-path support."""
    if _is_windows():
        os.rename(_win_extended_path(str(src)), _win_extended_path(str(dst)))
    else:
        src.rename(dst)


def _iter_files_tolerant(folder: Path, include_subfolders: bool) -> tuple[list[Path], list[str]]:
    """Tolerant file scan.

    Returns (files, scan_errors). The scan never aborts the whole run because of
    one unreadable directory or a permission error.
    """
    files: list[Path] = []
    errors: list[str] = []

    if include_subfolders:
        def _onerror(e: OSError):
            errors.append(str(e))

        for root, _dirs, filenames in os.walk(str(folder), topdown=True, onerror=_onerror):
            for fn in filenames:
                files.append(Path(root) / fn)
    else:
        try:
            with os.scandir(folder) as it:
                for entry in it:
                    try:
                        if entry.is_file():
                            files.append(Path(entry.path))
                    except Exception as e:
                        errors.append(f"{entry.path}: {e}")
        except Exception as e:
            errors.append(f"{folder}: {e}")

    # Stable ordering for deterministic auto-indexing.
    files.sort(key=lambda p: str(p).casefold() if _is_windows() else str(p))
    return files, errors


def _resolve_conflict_auto_index(
    base_name: str,
    existing_keys: set[str],
    reserved_keys: set[str],
    *,
    key_func=_name_key,
    max_tries: int = 999,
) -> tuple[str, int]:
    """Resolve name conflicts by appending _001/_002... before extension.

    Returns: (resolved_name, index). index==0 means no conflict (base_name used).
    """
    if key_func(base_name) not in existing_keys and key_func(base_name) not in reserved_keys:
        return base_name, 0

    stem, suffix = os.path.splitext(base_name)
    for i in range(1, max_tries + 1):
        cand = f"{stem}_{i:03d}{suffix}"
        if key_func(cand) not in existing_keys and key_func(cand) not in reserved_keys:
            return cand, i

    raise RuntimeError(f"Too many conflicts when resolving: {base_name}")



# ------------------------- Date Source -------------------------
_EXIF_DT_TAG_IDS = (36867, 36868, 306)  # DateTimeOriginal, DateTimeDigitized, DateTime


def _read_exif_datetime(p: Path) -> tuple[datetime | None, str | None]:
    """Read EXIF capture time.

    Returns: (datetime, note_code)
    - datetime: parsed EXIF datetime if available
    - note_code: None when success; otherwise 'exif_missing' or 'exif_unavailable'
    """
    if Image is None:
        return None, 'exif_unavailable'

    try:
        with Image.open(p) as im:
            if not hasattr(im, 'getexif'):
                return None, 'exif_unavailable'
            ex = im.getexif()
            if not ex:
                return None, 'exif_missing'

            for tag_id in _EXIF_DT_TAG_IDS:
                v = ex.get(tag_id)
                if not v:
                    continue

                if isinstance(v, bytes):
                    try:
                        v = v.decode(errors='ignore')
                    except Exception:
                        v = ''

                if isinstance(v, str):
                    s = v.strip()
                    if not s:
                        continue
                    # common format: 'YYYY:MM:DD HH:MM:SS'
                    try:
                        return datetime.strptime(s, '%Y:%m:%d %H:%M:%S'), None
                    except Exception:
                        # ignore timezone / subsec if present
                        try:
                            return datetime.strptime(s[:19], '%Y:%m:%d %H:%M:%S'), None
                        except Exception:
                            return None, 'exif_missing'

            return None, 'exif_missing'
    except Exception:
        return None, 'exif_unavailable'


# Video metadata support (optional)
_VIDEO_META_SUFFIXES = {'.mp4', '.mov', '.m4v', '.avi', '.mkv'}


def _parse_iso_datetime(s: str) -> datetime | None:
    """Parse common ISO 8601 datetime strings from media metadata."""
    s = (s or '').strip()
    if not s:
        return None
    if s.endswith('Z'):
        s = s[:-1] + '+00:00'
    try:
        return datetime.fromisoformat(s)
    except Exception:
        pass
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(s[:19], fmt)
        except Exception:
            continue
    return None


def _read_video_datetime_ffprobe(p: Path) -> tuple[datetime | None, str | None]:
    """Try reading video creation time using ffprobe (if available)."""
    try:
        ffprobe = shutil.which('ffprobe')
        if not ffprobe:
            return None, 'ffprobe_missing'

        cmd = [
            ffprobe, '-v', 'error',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            str(p),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        if proc.returncode != 0:
            return None, 'ffprobe_failed'
        data = json.loads(proc.stdout or '{}')

        candidates: list[str] = []
        fmt = data.get('format') or {}
        tags = (fmt.get('tags') or {}) if isinstance(fmt, dict) else {}
        if isinstance(tags, dict):
            ct = tags.get('creation_time') or tags.get('com.apple.quicktime.creationdate')
            if isinstance(ct, str):
                candidates.append(ct)

        streams = data.get('streams') or []
        if isinstance(streams, list):
            for s in streams:
                if not isinstance(s, dict):
                    continue
                stags = s.get('tags') or {}
                if isinstance(stags, dict):
                    ct = stags.get('creation_time') or stags.get('com.apple.quicktime.creationdate')
                    if isinstance(ct, str):
                        candidates.append(ct)

        for ct in candidates:
            dt = _parse_iso_datetime(ct)
            if dt:
                return dt, None

        return None, 'video_meta_missing'
    except Exception:
        return None, 'video_meta_unavailable'


def _read_video_datetime_hachoir(p: Path) -> tuple[datetime | None, str | None]:
    """Try reading video creation time using hachoir (optional dependency)."""
    try:
        try:
            from hachoir.metadata import extractMetadata  # type: ignore
            from hachoir.parser import createParser  # type: ignore
        except Exception:
            return None, 'hachoir_missing'

        parser = createParser(str(p))
        if not parser:
            return None, 'video_meta_unavailable'
        with parser:
            metadata = extractMetadata(parser)
        if not metadata:
            return None, 'video_meta_missing'

        for key in ('creation_date', 'creation_datetime'):
            try:
                if metadata.has(key):  # type: ignore
                    v = metadata.get(key)  # type: ignore
                    if isinstance(v, datetime):
                        return v, None
                    vv = getattr(v, 'value', None)
                    if isinstance(vv, datetime):
                        return vv, None
            except Exception:
                continue

        try:
            lines = metadata.exportPlaintext()  # type: ignore
            for ln in lines or []:
                if not isinstance(ln, str):
                    continue
                if 'creation' in ln.lower() and ':' in ln:
                    dt = _parse_iso_datetime(ln.split(':', 1)[-1].strip())
                    if dt:
                        return dt, None
        except Exception:
            pass

        return None, 'video_meta_missing'
    except Exception:
        return None, 'video_meta_unavailable'


def _read_video_datetime(p: Path) -> tuple[datetime | None, str | None]:
    """Read video creation time with best-effort fallbacks."""
    dt, note = _read_video_datetime_ffprobe(p)
    if dt is not None:
        return dt, None
    if note in ('ffprobe_missing', 'ffprobe_failed', 'video_meta_missing', 'video_meta_unavailable'):
        dt2, note2 = _read_video_datetime_hachoir(p)
        if dt2 is not None:
            return dt2, None
        return None, (note2 or note)
    return None, note


def _get_date_prefix(p: Path, date_source: str) -> tuple[str | None, str | None]:
    """Return (YYYYMMDD, note_code) based on selected date source.

    note_code is only meaningful for EXIF mode:
    - None: EXIF datetime found and used
    - 'exif_missing': no usable EXIF datetime, fallback to mtime
    - 'exif_unavailable': cannot read EXIF, fallback to mtime
    """
    try:
        if date_source == 'ctime':
            ts = os.path.getctime(p)
            return datetime.fromtimestamp(ts).strftime('%Y%m%d'), None

        if date_source == 'exif':
            # Photo EXIF
            dt, note_code = _read_exif_datetime(p)
            if dt is not None:
                return dt.strftime('%Y%m%d'), None

            # Video metadata (mp4/mov/...)
            v_note: str | None = None
            if p.suffix.lower() in _VIDEO_META_SUFFIXES:
                vdt, v_note = _read_video_datetime(p)
                if vdt is not None:
                    return vdt.strftime('%Y%m%d'), None

            # fallback to mtime
            fallback_note = v_note or note_code or 'meta_missing'
            try:
                ts = p.stat().st_mtime
                return datetime.fromtimestamp(ts).strftime('%Y%m%d'), fallback_note
            except Exception:
                return None, fallback_note

        # default: mtime
        ts = p.stat().st_mtime
        return datetime.fromtimestamp(ts).strftime('%Y%m%d'), None
    except Exception:
        return None, None


def _build_rename_plan(
    *,
    target_path: str,
    is_single_file: bool,
    opts: RenameOptions,
    language: str,
    cancel_event: threading.Event | None = None,
) -> RenamePlan:
    """Build a single source of truth: old -> new mapping with reasons.

    This plan is used by:
    - precheck (conflict estimate)
    - preview (diff rendering)
    - run (actual renaming)
    """
    t = TEXTS.get(language, TEXTS['zh'])

    scan_errors: list[str] = []

    # 1) Scan
    if is_single_file:
        files = [Path(target_path)]
    else:
        folder = Path(target_path)
        files, scan_errors = _iter_files_tolerant(folder, opts.include_subfolders)

    scanned = len(files)

    # 2) Filter
    exts = _parse_exts(opts.filter_exts)
    inc = (opts.filter_include or '').strip().lower()
    exc = (opts.filter_exclude or '').strip().lower()

    kept: list[Path] = []
    filtered_out = 0
    if exts or inc or exc:
        for p in files:
            if cancel_event and cancel_event.is_set():
                return RenamePlan(items=[], scanned=scanned, matched=0, filtered_out=scanned, scan_errors=scan_errors, cancelled=True)
            name_lower = p.name.lower()
            if exts and p.suffix.lower() not in exts:
                filtered_out += 1
                continue
            if inc and inc not in name_lower:
                filtered_out += 1
                continue
            if exc and exc in name_lower:
                filtered_out += 1
                continue
            kept.append(p)
    else:
        kept = files

    matched = len(kept)

    # 3) Build mapping with per-directory collision simulation
    existing_keys_by_dir: dict[Path, set[str]] = {}
    reserved_keys_by_dir: dict[Path, set[str]] = {}
    items: list[PlanItem] = []

    for p in kept:
        if cancel_event and cancel_event.is_set():
            return RenamePlan(items=items, scanned=scanned, matched=matched, filtered_out=filtered_out, scan_errors=scan_errors, cancelled=True)

        original = p.name
        parent = p.parent
        item = PlanItem(path=p, original_name=original)

        # Already has date prefix
        if _has_any_date_prefix(original):
            item.status = 'skip_prefix'
            item.final_name = original
            item.summary = t['summary_skip_prefix']
            items.append(item)
            continue

        date_prefix, note_code = _get_date_prefix(p, opts.date_source)
        if not date_prefix:
            item.status = 'error'
            item.final_name = original
            item.error = 'stat() failed'
            item.summary = item.error
            items.append(item)
            continue

        base_name = f"{date_prefix}_{original}"
        item.base_name = base_name
        item.note_code = note_code

        existing_keys = existing_keys_by_dir.get(parent)
        if existing_keys is None:
            try:
                existing_names = os.listdir(parent)
            except Exception as e:
                existing_names = []
                scan_errors.append(f"listdir {parent}: {e}")
            existing_keys = {_name_key(n) for n in existing_names}
            existing_keys_by_dir[parent] = existing_keys

        reserved_keys = reserved_keys_by_dir.setdefault(parent, set())

        try:
            final_name, idx = _resolve_conflict_auto_index(
                base_name,
                existing_keys,
                reserved_keys,
                key_func=_name_key,
            )
        except Exception as e:
            item.status = 'error'
            item.final_name = original
            item.error = str(e)
            item.summary = item.error
            items.append(item)
            continue

        item.final_name = final_name
        item.conflict_index = idx

        # Reserve + simulate apply
        reserved_keys.add(_name_key(final_name))
        existing_keys.discard(_name_key(original))
        existing_keys.add(_name_key(final_name))

        # Summary
        summary_parts = [t['summary_prefix_source'].format(
            source=t.get(f"source_{opts.date_source}", opts.date_source)
        )]
        if note_code:
            if str(note_code).startswith(('video_', 'ffprobe_', 'hachoir_', 'meta_')):
                summary_parts.append(t.get('summary_meta_fallback', t['summary_exif_fallback']))
            else:
                summary_parts.append(t['summary_exif_fallback'])
        if idx > 0:
            summary_parts.append(t['summary_auto_index'].format(suffix=f"_{idx:03d}"))
        item.summary = ' + '.join(summary_parts)
        item.status = 'rename'
        items.append(item)

    return RenamePlan(items=items, scanned=scanned, matched=matched, filtered_out=filtered_out, scan_errors=scan_errors)



# ------------------------- Undo History -------------------------
_HISTORY_DIRNAME = '.file_auto_rename'
_HISTORY_DB_FILENAME = 'history.db'
_HISTORY_JSON_FILENAME = 'history.json'  # legacy (will be migrated)
_HISTORY_MAX_ENTRIES = 30


def _history_dir_path() -> Path:
    """Persistent history directory for undo (user home)."""
    base = Path.home() / _HISTORY_DIRNAME
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        base = Path('.')  # last resort
    return base


def _history_db_path() -> Path:
    return _history_dir_path() / _HISTORY_DB_FILENAME


def _history_json_path() -> Path:
    return _history_dir_path() / _HISTORY_JSON_FILENAME


def _init_history_db(conn: sqlite3.Connection) -> None:
    """Initialize sqlite schema and safe pragmas."""
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA synchronous=NORMAL;')
    conn.execute('PRAGMA busy_timeout=2000;')
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rename_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id TEXT UNIQUE,
            created_at TEXT,
            status TEXT,
            entry_json TEXT,
            undone_at TEXT,
            undo_summary_json TEXT
        )
        """
    )
    conn.execute('CREATE INDEX IF NOT EXISTS idx_rename_history_created_at ON rename_history(created_at);')
    conn.commit()


def _with_history_conn() -> sqlite3.Connection:
    db = _history_db_path()
    conn = sqlite3.connect(str(db))
    _init_history_db(conn)
    return conn


def _migrate_history_json_to_db_if_needed() -> None:
    """One-time best-effort migration from legacy JSON history to sqlite."""
    json_path = _history_json_path()
    if not json_path.exists():
        return

    try:
        legacy = json.loads(json_path.read_text(encoding='utf-8'))
        if not isinstance(legacy, list) or not legacy:
            return
    except Exception:
        return

    try:
        conn = _with_history_conn()
        try:
            row = conn.execute('SELECT COUNT(1) FROM rename_history').fetchone()
            cnt = int(row[0] if row else 0)
            if cnt > 0:
                return  # already migrated/has data

            with conn:
                for e in legacy:
                    if not isinstance(e, dict):
                        continue
                    entry_id = str(e.get('id') or uuid4())
                    created_at = str(e.get('created_at') or datetime.now().isoformat(timespec='seconds'))
                    status = str(e.get('status') or 'done')
                    conn.execute(
                        'INSERT OR IGNORE INTO rename_history(entry_id, created_at, status, entry_json) VALUES (?,?,?,?)',
                        (entry_id, created_at, status, json.dumps(e, ensure_ascii=False)),
                    )
        finally:
            conn.close()

        try:
            json_path.rename(json_path.with_suffix('.json.bak'))
        except Exception:
            pass
    except Exception:
        return


def _load_history() -> list[dict]:
    """Load undo history (latest up to max entries)."""
    _migrate_history_json_to_db_if_needed()
    try:
        conn = _with_history_conn()
        try:
            rows = conn.execute('SELECT entry_json FROM rename_history ORDER BY id ASC').fetchall()
        finally:
            conn.close()

        items: list[dict] = []
        for (entry_json,) in rows[-_HISTORY_MAX_ENTRIES:]:
            try:
                e = json.loads(entry_json or '{}')
                if isinstance(e, dict):
                    items.append(e)
            except Exception:
                continue
        return items
    except Exception:
        # fallback to legacy JSON (best effort)
        p = _history_json_path()
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding='utf-8'))
                if isinstance(data, list):
                    return [x for x in data if isinstance(x, dict)]
            except Exception:
                pass
        return []


def _append_history_entry(entry: dict) -> None:
    """Append a history entry (sqlite transaction)."""
    _migrate_history_json_to_db_if_needed()
    try:
        conn = _with_history_conn()
        try:
            entry_id = str(entry.get('id') or uuid4())
            entry = dict(entry)
            entry['id'] = entry_id
            created_at = str(entry.get('created_at') or datetime.now().isoformat(timespec='seconds'))
            entry['created_at'] = created_at
            status = str(entry.get('status') or 'done')

            with conn:
                conn.execute(
                    'INSERT OR REPLACE INTO rename_history(entry_id, created_at, status, entry_json) VALUES (?,?,?,?)',
                    (entry_id, created_at, status, json.dumps(entry, ensure_ascii=False)),
                )
                row = conn.execute('SELECT COUNT(1) FROM rename_history').fetchone()
                cnt = int(row[0] if row else 0)
                if cnt > _HISTORY_MAX_ENTRIES:
                    to_del = cnt - _HISTORY_MAX_ENTRIES
                    conn.execute(
                        'DELETE FROM rename_history WHERE id IN (SELECT id FROM rename_history ORDER BY id ASC LIMIT ?)',
                        (to_del,),
                    )
        finally:
            conn.close()
    except Exception:
        # last resort fallback to JSON
        try:
            p = _history_json_path()
            items = []
            if p.exists():
                try:
                    items = json.loads(p.read_text(encoding='utf-8'))
                except Exception:
                    items = []
            if not isinstance(items, list):
                items = []
            items.append(entry)
            items = items[-_HISTORY_MAX_ENTRIES:]
            p.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception:
            pass


def _find_last_undoable(items: list[dict]) -> tuple[int | None, dict | None]:
    for i in range(len(items) - 1, -1, -1):
        e = items[i]
        if e.get('status') != 'done':
            continue
        ops = e.get('ops') or []
        if isinstance(ops, list) and ops:
            return i, e
    return None, None


def _mark_history_undone(entry_id: str, summary: dict) -> None:
    """Mark a history entry undone (sqlite transaction)."""
    _migrate_history_json_to_db_if_needed()
    try:
        conn = _with_history_conn()
        try:
            row = conn.execute('SELECT entry_json FROM rename_history WHERE entry_id=?', (entry_id,)).fetchone()
            if not row:
                return
            try:
                e = json.loads(row[0] or '{}')
            except Exception:
                e = {}
            if not isinstance(e, dict):
                e = {}
            e['status'] = 'undone'
            e['undone_at'] = datetime.now().isoformat(timespec='seconds')
            e['undo_summary'] = summary

            with conn:
                conn.execute(
                    'UPDATE rename_history SET status=?, entry_json=?, undone_at=?, undo_summary_json=? WHERE entry_id=?',
                    ('undone', json.dumps(e, ensure_ascii=False), e.get('undone_at'), json.dumps(summary, ensure_ascii=False), entry_id),
                )
        finally:
            conn.close()
    except Exception:
        # fallback update legacy JSON
        try:
            items = _load_history()
            for e in items:
                if e.get('id') == entry_id:
                    e['status'] = 'undone'
                    e['undone_at'] = datetime.now().isoformat(timespec='seconds')
                    e['undo_summary'] = summary
                    break
            p = _history_json_path()
            p.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception:
            pass

# ------------------------- UI Components -------------------------

class RoundedFrame(tk.Frame):
    """圆角卡片容器（更接近 Apple/现代 Dashboard 风格）

    改进点（为了解决“卡片内容被裁切/高度不自适应”的问题）：
    - 默认 autosize=True：卡片高度会根据 inner_frame 的真实内容高度自动调整（更适合左侧卡片）
    - autosize=False：卡片跟随父容器拉伸（适合右侧预览/日志这种需要占满的区域）
    - Canvas 自绘圆角矩形（smooth polygon），避免 arc+rect 拼接导致的“十字线/锯齿”
    - 3 层柔化阴影（faux box-shadow）：不同偏移+不同浅色模拟扩散
    """

    def __init__(
        self,
        parent: tk.Widget,
        radius: int = UI_METRICS.card_radius,
        bg_color: str = COLORS['bg_card'],
        border_color: str = COLORS['border'],
        shadow: bool = True,
        autosize: bool = True,
        margin: int = 12,
        **kwargs,
    ):
        super().__init__(parent, bg=parent.cget('bg'), **kwargs)
        self.radius = radius
        self.bg_color = bg_color
        self.border_color = border_color
        self.shadow = shadow
        self.autosize = autosize
        self.margin = margin

        self._in_autosize = False

        self.canvas = tk.Canvas(self, bg=parent.cget('bg'), highlightthickness=0, bd=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.inner_frame = tk.Frame(self.canvas, bg=bg_color)
        self._win_id = self.canvas.create_window(0, 0, window=self.inner_frame, anchor='nw')

        self.canvas.bind('<Configure>', self._on_canvas_configure)
        # 当内容高度变化时（尤其是 Entry 换行/字体变化），自动调整卡片高度
        self.inner_frame.bind('<Configure>', self._on_inner_configure)

    def _rounded_poly_points(self, x1: float, y1: float, x2: float, y2: float, r: float) -> list[float]:
        # clamp radius
        w = max(1.0, x2 - x1)
        h = max(1.0, y2 - y1)
        r = max(1.0, min(r, w / 2.0, h / 2.0))

        # smooth polygon trick: duplicate points at corners
        return [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1,
        ]

    def _draw_rounded_rect(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        r: float,
        *,
        fill: str,
        outline: str = '',
        width: int = 1,
        tags: str = 'bg_layer',
    ):
        if x2 <= x1 or y2 <= y1:
            return
        pts = self._rounded_poly_points(x1, y1, x2, y2, r)
        self.canvas.create_polygon(
            pts,
            smooth=True,
            splinesteps=48,  # 更平滑一点（高分屏观感更好）
            fill=fill,
            outline=outline,
            width=width if outline else 0,
            tags=tags,
        )

    def _sync_from_content(self):
        """在内容高度变化后同步 Canvas window 尺寸与背景重绘（避免内容被裁切）。"""
        if not self.autosize:
            return
        try:
            self._on_canvas_configure(None)
        except Exception:
            pass

    def _on_inner_configure(self, _e=None):
        if not self.autosize:
            return
        if self._in_autosize:
            return
        # 让卡片高度跟随内容：解决“内容变多后卡片裁切”
        try:
            req_h = max(self.inner_frame.winfo_reqheight(), 1)
            # 阴影主要向下扩散，额外留一点底部空间
            extra_shadow = 8 if self.shadow else 0
            desired = req_h + self.margin * 2 + extra_shadow

            self._in_autosize = True
            # 仅在变化时更新，减少闪动
            try:
                cur_h = int(float(self.canvas.cget('height')))
            except Exception:
                cur_h = -1
            if cur_h != int(desired):
                self.canvas.configure(height=desired)

            # 关键：同步 window item 的高度与背景重绘，否则只改 canvas 高度会导致内部内容被裁切
            self.canvas.after_idle(self._sync_from_content)
        finally:
            self._in_autosize = False

    def _on_canvas_configure(self, event=None):
        w = max(self.canvas.winfo_width() if event is None else event.width, 1)
        h = max(self.canvas.winfo_height() if event is None else event.height, 1)

        margin = self.margin
        self.canvas.coords(self._win_id, margin, margin)

        # autosize 时：窗口高度用内容真实高度；否则填满
        if self.autosize:
            inner_h = max(self.inner_frame.winfo_reqheight(), 1)
            win_h = inner_h
        else:
            win_h = max(1, h - margin * 2)

        self.canvas.itemconfigure(
            self._win_id,
            width=max(1, w - margin * 2),
            height=win_h,
        )

        self._draw_bg(w, h, margin)

    def _draw_bg(self, w: int, h: int, m: int):
        self.canvas.delete('bg_layer')
        r = self.radius

        # 更柔和的阴影：偏移更小一点，观感更“轻”
        if self.shadow:
            self._draw_rounded_rect(m + 2, m + 4, w - m + 2, h - m + 4, r, fill=COLORS['shadow_1'], outline='', width=0)
            self._draw_rounded_rect(m + 1, m + 3, w - m + 1, h - m + 3, r, fill=COLORS['shadow_2'], outline='', width=0)
            self._draw_rounded_rect(m + 0, m + 2, w - m + 0, h - m + 2, r, fill=COLORS['shadow_3'], outline='', width=0)

        # 主体卡片
        self._draw_rounded_rect(m, m, w - m, h - m, r, fill=self.bg_color, outline=self.border_color, width=1)

class PillButton(tk.Canvas):
    """胶囊按钮（Canvas 自绘 smooth polygon）

    目标：
    - 实心填充（无内部拼接线/杂边）
    - Hover + 按压反馈：按压时颜色轻微加深、文字下沉 1px
    - .config(...) 兼容旧用法
    """

    def __init__(
        self,
        parent: tk.Widget,
        text: str = '',
        command=None,
        *,
        height: int = 40,
        radius: int = UI_METRICS.pill_radius,
        fill: str = '#FFFFFF',
        fill_hover: str | None = None,
        fill_active: str | None = None,
        outline: str = '',
        outline_width: int = 0,
        fg: str = COLORS['text_primary'],
        fg_disabled: str = COLORS['text_secondary'],
        font=None,
        cursor: str = 'hand2',
        state: str = tk.NORMAL,
        shadow: bool = True,
        **kwargs,
    ):
        super().__init__(
            parent,
            height=height,
            highlightthickness=0,
            bd=0,
            bg=parent.cget('bg'),
            **kwargs,
        )
        self._text = text
        self._command = command
        self._height = height
        self._radius = radius
        self._fill = fill
        self._fill_hover = fill if fill_hover is None else fill_hover
        self._fill_active = fill_active  # optional override (pressed)
        self._outline = outline
        self._outline_width = outline_width
        self._fg = fg
        self._fg_disabled = fg_disabled
        self._font = font
        self._state = state
        self._shadow = shadow

        super().configure(cursor=(cursor if state != tk.DISABLED else ''))

        self._hover = False
        self._pressed = False

        self.bind('<Configure>', lambda _e: self._redraw())
        self.bind('<Enter>', self._on_enter)
        self.bind('<Leave>', self._on_leave)
        self.bind('<ButtonPress-1>', self._on_press)
        self.bind('<ButtonRelease-1>', self._on_release)

        self._redraw()

    def cget(self, key):
        if key == 'text':
            return self._text
        if key == 'state':
            return self._state
        if key == 'font':
            return self._font
        if key == 'fg':
            return self._fg
        if key == 'fill':
            return self._fill
        return super().cget(key)

    def configure(self, cnf=None, **kw):
        cnf = cnf or {}
        if isinstance(cnf, dict):
            kw = {**cnf, **kw}

        if 'text' in kw:
            self._text = kw.pop('text')
        if 'command' in kw:
            self._command = kw.pop('command')
        if 'state' in kw:
            self._state = kw.pop('state')
            super().configure(cursor=('hand2' if self._state != tk.DISABLED else ''))
        if 'font' in kw:
            self._font = kw.pop('font')
        if 'fg' in kw:
            self._fg = kw.pop('fg')
        if 'fill' in kw:
            self._fill = kw.pop('fill')
        if 'fill_hover' in kw:
            self._fill_hover = kw.pop('fill_hover')
        if 'fill_active' in kw:
            self._fill_active = kw.pop('fill_active')
        if 'outline' in kw:
            self._outline = kw.pop('outline')
        if 'outline_width' in kw:
            self._outline_width = kw.pop('outline_width')
        if 'shadow' in kw:
            self._shadow = kw.pop('shadow')

        super().configure(**kw)
        self._redraw()

    config = configure  # alias

    @staticmethod
    def _shade(hex_color: str, factor: float) -> str:
        """Return a darker shade of a hex color. factor < 1 darker, > 1 lighter."""
        try:
            c = hex_color.lstrip('#')
            r = int(c[0:2], 16)
            g = int(c[2:4], 16)
            b = int(c[4:6], 16)
            r = max(0, min(255, int(r * factor)))
            g = max(0, min(255, int(g * factor)))
            b = max(0, min(255, int(b * factor)))
            return f"#{r:02X}{g:02X}{b:02X}"
        except Exception:
            return hex_color

    def _pill_points(self, w: int, h: int, r: int, pad: int = 1) -> list[int]:
        x1, y1 = pad, pad
        x2, y2 = w - pad, h - pad
        r = max(1, min(r, (x2 - x1) // 2, (y2 - y1) // 2))
        return [
            x1 + r, y1,
            x2 - r, y1, x2 - r, y1,
            x2, y1, x2, y1 + r, x2, y1 + r,
            x2, y2 - r,
            x2, y2 - r, x2, y2,
            x2 - r, y2, x2 - r, y2,
            x1 + r, y2,
            x1 + r, y2, x1, y2,
            x1, y2 - r, x1, y2 - r,
            x1, y1 + r,
            x1, y1 + r, x1, y1,
            x1 + r, y1
        ]

    def _redraw(self):
        self.delete('all')
        w = max(self.winfo_width(), 1)
        h = max(self.winfo_height(), 1)
        r = max(1, min(self._radius, h // 2, w // 2))

        # state-based fills
        base = self._fill_hover if (self._hover and self._state != tk.DISABLED) else self._fill
        if self._state == tk.DISABLED:
            fill = COLORS['bg_drop']
        else:
            if self._pressed:
                fill = self._fill_active if self._fill_active else self._shade(base, 0.92)
            else:
                fill = base

        pts = self._pill_points(w, h, r, pad=1)

        # subtle shadow under pill (no outline)
        if self._shadow:
            sdx, sdy = 0, 2
            pts_shadow = [pts[i] + (sdx if i % 2 == 0 else sdy) for i in range(len(pts))]
            self.create_polygon(
                pts_shadow,
                smooth=True,
                splinesteps=36,
                fill=COLORS['shadow_2'],
                outline='',
            )

        # main pill
        self.create_polygon(
            pts,
            smooth=True,
            splinesteps=36,
            fill=fill,
            outline=self._outline,
            width=(self._outline_width if self._outline and self._outline_width > 0 else 0),
        )

        fg = self._fg_disabled if self._state == tk.DISABLED else self._fg
        y_off = 1 if (self._pressed and self._state != tk.DISABLED) else 0
        self.create_text(w // 2, h // 2 + y_off, text=self._text, fill=fg, font=self._font)

    def _on_enter(self, _e=None):
        self._hover = True
        self._redraw()

    def _on_leave(self, _e=None):
        self._hover = False
        self._pressed = False
        self._redraw()

    def _on_press(self, e=None):
        if self._state == tk.DISABLED:
            return
        self._pressed = True
        self._redraw()

    def _on_release(self, e=None):
        if self._state == tk.DISABLED:
            return
        was_pressed = self._pressed
        self._pressed = False
        self._redraw()

        if not was_pressed:
            return

        # Only trigger when releasing inside the widget bounds
        if e is None:
            if callable(self._command):
                self._command()
            return

        if 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            if callable(self._command):
                self._command()

    # Backward compatible alias
    def _on_click(self, e=None):
        self._on_release(e)

# ------------------------- App -------------------------
class RenameApp(_BaseTk):
    def __init__(self):
        super().__init__()

        # state
        self.language = 'zh'

        # UI skin layer (外观集中管理，不碰重命名逻辑)
        self.skin = SkinLayer(language=self.language)
        self.target_path: str | None = None
        self.is_single_file: bool = False
        self.processing: bool = False
        self._progress_mode: str = 'rename'  # 'rename' | 'undo'

        # options
        self.var_include_subfolders = tk.BooleanVar(value=False)
        self.var_dry_run = tk.BooleanVar(value=False)
        self.var_date_source = tk.StringVar(value='mtime')

        # filters
        self.var_filter_exts = tk.StringVar(value='')
        self.var_filter_include = tk.StringVar(value='')
        self.var_filter_exclude = tk.StringVar(value='')

        # thread/queue
        self._q: queue.Queue[dict] = queue.Queue()
        self._cancel_event = threading.Event()
        self._worker: threading.Thread | None = None

        # precheck (conflict estimate)
        self._precheck_token: int = 0
        self._precheck_after_id: str | None = None
        self._preview_after_id: str | None = None
        self._last_conflicts: list[dict] = []  # each: {folder, original, base, final}
        self._conflict_count: int | None = None
        self._precheck_inflight: bool = False

        # diff preview state
        self._preview_token: int = 0
        self._preview_inflight: bool = False
        self._preview_rows: list[dict] = []
        self._preview_dialog: tk.Toplevel | None = None
        self._preview_tree: ttk.Treeview | None = None
        self._preview_detail: tk.Text | None = None
        self._preview_var_query: tk.StringVar | None = None
        self._preview_var_only_changed: tk.BooleanVar | None = None
        self._preview_var_only_conflict: tk.BooleanVar | None = None
        self._preview_count_label: tk.Label | None = None

        self._init_fonts()
        self._setup_window()
        self._init_ttk_style()
        self._create_widgets()
        self._setup_traces()
        self._update_texts()
        self._center_window()
        self._refresh_undo_state()

    # ---------- fonts / style ----------

    def _init_fonts(self):
        self.skin.init_fonts(self)
        # 保持旧属性，避免其他地方引用
        self.font_zh = self.skin.font_zh
        self.font_en = self.skin.font_en



    def _font(self, size: int, weight: str = 'normal'):
        return self.skin.font(size, weight)



    def _setup_window(self):
        self.skin.apply_window(self, TEXTS[self.language]['title'])


    def _center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f'{w}x{h}+{x}+{y}')


    def _center_dialog(self, dialog: tk.Toplevel):
        """Center a toplevel dialog relative to the main window."""
        dialog.update_idletasks()
        w = max(dialog.winfo_width(), 1)
        h = max(dialog.winfo_height(), 1)
        try:
            px = self.winfo_rootx()
            py = self.winfo_rooty()
            pw = self.winfo_width()
            ph = self.winfo_height()
            x = px + (pw // 2) - (w // 2)
            y = py + (ph // 2) - (h // 2)
        except Exception:
            x = (dialog.winfo_screenwidth() // 2) - (w // 2)
            y = (dialog.winfo_screenheight() // 2) - (h // 2)
        dialog.geometry(f'+{x}+{y}')

    def _init_ttk_style(self):
        self.skin.language = self.language
        self.skin.apply_ttk_style(self)



    def _ensure_round_checkbuttons(self, style: ttk.Style):
        self.skin.ensure_round_checkbuttons(self, style)


    def _toggle_language(self):
        self.language = 'en' if self.language == 'zh' else 'zh'
        self.skin.language = self.language
        self._init_ttk_style()
        self._update_texts()

    def _update_texts(self):
        t = TEXTS[self.language]

        self.title(t['title'])
        self.title_label.config(text=t['title'], font=self._font(26, 'bold'))
        self.subtitle_label.config(text=t['subtitle'], font=self._font(12))

        self.drop_area.config(text=t['drop_area'], font=self._font(13))
        if hasattr(self, 'btn_pick_folder'):
            self.btn_pick_folder.config(text=t.get('pick_folder', 'Choose Folder'), font=self._font(11))
        if hasattr(self, 'btn_pick_file'):
            self.btn_pick_file.config(text=t.get('pick_file', 'Choose File'), font=self._font(11))

        self.btn_lang.config(text=t['language_switch'], font=self._font(12))

        # left: options / filters
        self.options_title.config(text=t['options'], font=self._font(13, 'bold'))
        self.chk_subfolders.config(text=t['include_subfolders'])
        self.chk_dryrun.config(text=t['dry_run'])

        if hasattr(self, 'date_source_label'):
            self.date_source_label.config(text=t['date_source'], font=self._font(11))
            self.rb_mtime.config(text=t['date_source_mtime'], font=self._font(11))
            self.rb_ctime.config(text=t['date_source_ctime'], font=self._font(11))
            self.rb_exif.config(text=t['date_source_exif'], font=self._font(11))

        self.filters_title.config(text=t['filters'], font=self._font(11, 'bold'))
        if hasattr(self, 'btn_filters_clear'):
            self.btn_filters_clear.config(text=t.get('filters_clear', 'Clear'), font=self._font(11, 'bold'))
        self.lbl_filter_exts.config(text=t['filter_exts'], font=self._font(11))
        self.lbl_filter_include.config(text=t['filter_include'], font=self._font(11))
        self.lbl_filter_exclude.config(text=t['filter_exclude'], font=self._font(11))

        self.btn_start.config(text=t['start_process'], font=self._font(14, 'bold'))
        self.btn_cancel.config(text=t['cancel'], font=self._font(14, 'bold'))
        self.btn_undo.config(text=t['undo_last'], font=self._font(12))

        self.btn_preview_diff.config(text=t['preview_button'], font=self._font(11, 'bold'))
        self.btn_preview_conflict.config(text=t['conflict_view'], font=self._font(11, 'bold'))

        # right: preview
        self.preview_title.config(text=t['preview_title'], font=self._font(13, 'bold'))
        self._preview_tree.heading('old', text=t['preview_col_old'])
        self._preview_tree.heading('new', text=t['preview_col_new'])
        self._preview_tree.heading('summary', text=t['preview_col_summary'])
        self.preview_chk_changed.config(text=t['preview_only_changed'])
        self.preview_chk_conflict.config(text=t['preview_only_conflict'])

        # log
        self.log_title.config(text=t['log_title'], font=self._font(13, 'bold'))
        self.btn_clear.config(text=t['clear_log'], font=self._font(12))

        if not self.target_path:
            self._set_conflict_display(t['conflict_unknown'], conflicts=[])
            if self._preview_count_label is not None:
                self._preview_count_label.config(text=t['preview_no_data'], font=self._font(11))

        # status
        if not self.processing:
            self.status_label.config(text=t.get('status_idle', t.get('status_ready', 'Ready')), font=self._font(12))

    def _create_widgets(self):
        # Root container
        root = tk.Frame(self, bg=COLORS['bg_main'])
        root.pack(fill=tk.BOTH, expand=True, padx=24, pady=20)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(1, weight=1)

        # ---------------- Top bar ----------------
        top = tk.Frame(root, bg=COLORS['bg_main'])
        top.grid(row=0, column=0, sticky='ew')
        top.grid_columnconfigure(0, weight=1)

        left_top = tk.Frame(top, bg=COLORS['bg_main'])
        left_top.grid(row=0, column=0, sticky='w')

        self.title_label = tk.Label(left_top, text='', bg=COLORS['bg_main'], fg=COLORS['text_primary'])
        self.title_label.pack(anchor=tk.W)

        self.subtitle_label = tk.Label(left_top, text='', bg=COLORS['bg_main'], fg=COLORS['text_secondary'])
        self.subtitle_label.pack(anchor=tk.W, pady=(4, 0))

        right_top = tk.Frame(top, bg=COLORS['bg_main'])
        right_top.grid(row=0, column=1, sticky='e')

        self.btn_lang = PillButton(
            right_top,
            text='',
            height=34,
            radius=17,
            fill=COLORS['bg_card'],
            fill_hover=COLORS['bg_drop_hover'],
            outline=COLORS['border'],
            outline_width=1,
            fg=COLORS['text_secondary'],
            font=self._font(11),
            command=self._toggle_language,
        )
        self.btn_lang.pack(side=tk.RIGHT)

        # ---------------- Workbench ----------------
        wb = tk.Frame(root, bg=COLORS['bg_main'])
        wb.grid(row=1, column=0, sticky='nsew', pady=(16, 14))
        wb.grid_columnconfigure(0, weight=0, minsize=380)
        wb.grid_columnconfigure(1, weight=1)
        wb.grid_rowconfigure(0, weight=1)

        # Left (fixed width) with scrollable cards + fixed action bar
        left_outer = tk.Frame(wb, bg=COLORS['bg_main'], width=380)
        left_outer.grid(row=0, column=0, sticky='nsw', padx=(0, 16))
        left_outer.grid_propagate(False)
        left_outer.grid_rowconfigure(0, weight=1)
        left_outer.grid_rowconfigure(1, weight=0)
        left_outer.grid_columnconfigure(0, weight=1)

        left_scroll = tk.Frame(left_outer, bg=COLORS['bg_main'])
        left_scroll.grid(row=0, column=0, sticky='nsew')
        left_scroll.grid_rowconfigure(0, weight=1)
        left_scroll.grid_columnconfigure(0, weight=1)

        self._left_canvas = tk.Canvas(left_scroll, bg=COLORS['bg_main'], highlightthickness=0, bd=0)
        self._left_canvas.grid(row=0, column=0, sticky='nsew')

        self._left_vsb = ttk.Scrollbar(left_scroll, orient='vertical', style='Pill.Vertical.TScrollbar', command=self._left_canvas.yview)
        self._left_vsb.grid(row=0, column=1, sticky='ns', padx=(6, 0))
        self._left_canvas.configure(yscrollcommand=self._left_vsb.set)

        left = tk.Frame(self._left_canvas, bg=COLORS['bg_main'])
        self._left_window = self._left_canvas.create_window((0, 0), window=left, anchor='nw')

        def _left_on_frame_configure(_e=None):
            try:
                self._left_canvas.configure(scrollregion=self._left_canvas.bbox('all'))
            except Exception:
                pass

        def _left_on_canvas_configure(e):
            try:
                self._left_canvas.itemconfigure(self._left_window, width=e.width)
            except Exception:
                pass

        left.bind('<Configure>', _left_on_frame_configure)
        self._left_canvas.bind('<Configure>', _left_on_canvas_configure)

        def _left_on_mousewheel(e):
            try:
                d = getattr(e, 'delta', 0)
                if d:
                    self._left_canvas.yview_scroll(int(-1 * (d / 120)), 'units')
            except Exception:
                pass

        def _left_on_wheel_up(_e):
            try:
                self._left_canvas.yview_scroll(-1, 'units')
            except Exception:
                pass

        def _left_on_wheel_down(_e):
            try:
                self._left_canvas.yview_scroll(1, 'units')
            except Exception:
                pass

        self._left_canvas.bind('<Enter>', lambda _e: self._left_canvas.focus_set())
        for _w in (self._left_canvas, left):
            _w.bind('<MouseWheel>', _left_on_mousewheel)
            _w.bind('<Button-4>', _left_on_wheel_up)   # Linux
            _w.bind('<Button-5>', _left_on_wheel_down) # Linux

        # Right (preview)
        right = tk.Frame(wb, bg=COLORS['bg_main'])
        right.grid(row=0, column=1, sticky='nsew')
        right.grid_rowconfigure(0, weight=3)
        right.grid_rowconfigure(1, weight=2)
        right.grid_columnconfigure(0, weight=1)

# ---- Target card ----
        card_drop = RoundedFrame(left, radius=16)
        card_drop.pack(fill=tk.X, pady=(0, 12))

        inner = tk.Frame(card_drop.inner_frame, bg=COLORS['bg_card'], padx=14, pady=14)
        inner.pack(fill=tk.BOTH, expand=True)

        self.path_label = tk.Label(
            inner,
            text='',
            bg=COLORS['bg_card'],
            fg=COLORS['text_secondary'],
            anchor='w',
            justify=tk.LEFT,
            wraplength=310,
        )
        self.path_label.pack(fill=tk.X, pady=(0, 10))

        # Quick pick buttons (Folder / File)
        pick_row = tk.Frame(inner, bg=COLORS['bg_card'])
        pick_row.pack(fill=tk.X, pady=(0, 10))

        self.btn_pick_folder = PillButton(
            pick_row,
            text='',
            height=42,
            radius=21,
            fill=COLORS['bg_card'],
            fill_hover=COLORS['bg_drop_hover'],
            outline=COLORS['border'],
            outline_width=1,
            fg=COLORS['text_primary'],
            font=self._font(11, 'bold'),
            command=self._choose_folder,
        )
        self.btn_pick_folder.pack(side=tk.LEFT, fill=tk.X, expand=True)

        sep_lbl = tk.Label(pick_row, text='', bg=COLORS['bg_card'])
        sep_lbl.pack(side=tk.LEFT, padx=10)

        self.btn_pick_file = PillButton(
            pick_row,
            text='',
            height=42,
            radius=21,
            fill=COLORS['bg_card'],
            fill_hover=COLORS['bg_drop_hover'],
            outline=COLORS['border'],
            outline_width=1,
            fg=COLORS['text_primary'],
            font=self._font(11, 'bold'),
            command=self._choose_file,
        )
        self.btn_pick_file.pack(side=tk.LEFT, fill=tk.X, expand=True)

        drop_box = RoundedFrame(
            inner,
            radius=18,
            bg_color=COLORS['bg_drop'],
            border_color=COLORS['border'],
            shadow=False,
        )
        drop_box.pack(fill=tk.X, expand=False)

        self.drop_area = tk.Label(
            drop_box.inner_frame,
            text='',
            bg=COLORS['bg_drop'],
            fg=COLORS['text_secondary'],
            relief=tk.FLAT,
            padx=14,
            pady=18,
            cursor='hand2',
            justify=tk.CENTER,
        )
        self.drop_area.pack(fill=tk.X)
        _bind_hover(self.drop_area, COLORS['bg_drop'], COLORS['bg_drop_hover'])
        self.drop_area.bind('<Button-1>', lambda _e: self._on_click_select())

        try:
            self.drop_area.drop_target_register(DND_FILES)
            self.drop_area.dnd_bind('<<Drop>>', self._on_drop)
        except Exception:
            pass

        # ---- Options / Filters / Conflicts ----
        opt_card = RoundedFrame(left, radius=16)
        opt_card.pack(fill=tk.X, pady=(0, 12))

        opt_inner = tk.Frame(opt_card.inner_frame, bg=COLORS['bg_card'], padx=16, pady=14)
        opt_inner.pack(fill=tk.BOTH, expand=True)

        self.options_title = tk.Label(opt_inner, text='', bg=COLORS['bg_card'], fg=COLORS['text_primary'])
        self.options_title.pack(anchor=tk.W)

        self.chk_subfolders = ttk.Checkbutton(opt_inner, variable=self.var_include_subfolders, style='Card.TCheckbutton')
        self.chk_subfolders.pack(anchor=tk.W, pady=(8, 0))

        self.chk_dryrun = ttk.Checkbutton(opt_inner, variable=self.var_dry_run, style='Card.TCheckbutton')
        self.chk_dryrun.pack(anchor=tk.W, pady=(6, 0))

        # date source (mtime / ctime / EXIF)
        self.date_source_label = tk.Label(
            opt_inner, text='', bg=COLORS['bg_card'], fg=COLORS['text_secondary'], font=self._font(11)
        )
        self.date_source_label.pack(anchor=tk.W, pady=(10, 0))

        ds_row = tk.Frame(opt_inner, bg=COLORS['bg_card'])
        ds_row.pack(fill=tk.X, pady=(6, 0))

        rb_kwargs = dict(
            variable=self.var_date_source,
            bg=COLORS['bg_card'],
            fg=COLORS['text_primary'],
            activebackground=COLORS['bg_card'],
            activeforeground=COLORS['text_primary'],
            selectcolor=COLORS['bg_card'],
            highlightthickness=0,
            bd=0,
            font=self._font(11),
        )
        self.rb_mtime = tk.Radiobutton(ds_row, value='mtime', **rb_kwargs)
        self.rb_ctime = tk.Radiobutton(ds_row, value='ctime', **rb_kwargs)
        self.rb_exif = tk.Radiobutton(ds_row, value='exif', **rb_kwargs)
        self.rb_mtime.pack(anchor=tk.W, pady=(0, 2))
        self.rb_ctime.pack(anchor=tk.W, pady=(0, 2))
        self.rb_exif.pack(anchor=tk.W)

        sep = tk.Frame(opt_inner, bg=COLORS['border'], height=1)
        sep.pack(fill=tk.X, pady=(12, 10))

        self.filters_title_row = tk.Frame(opt_inner, bg=COLORS['bg_card'])
        self.filters_title_row.pack(fill=tk.X, pady=(0, 8))

        self.filters_title = tk.Label(
            self.filters_title_row,
            text='',
            bg=COLORS['bg_card'],
            fg=COLORS['text_primary'],
        )
        self.filters_title.pack(side=tk.LEFT, anchor='w')

        self.btn_filters_clear = PillButton(
            self.filters_title_row,
            text='',
            height=32,
            radius=16,
            fill=COLORS['bg_card'],
            fill_hover=COLORS['bg_drop_hover'],
            outline=COLORS['border'],
            outline_width=1,
            fg=COLORS['bg_button'],
            font=self._font(11, 'bold'),
            command=self._clear_filters,
        )
        self.btn_filters_clear.pack(side=tk.RIGHT)

        filters_grid = tk.Frame(opt_inner, bg=COLORS['bg_card'])
        filters_grid.pack(fill=tk.X)

        filters_grid.grid_columnconfigure(0, minsize=86)
        filters_grid.grid_columnconfigure(1, weight=1)

        # Filters (compact two-column layout)
        def _mk_entry(parent, var):
            ent = tk.Entry(
                parent,
                textvariable=var,
                bg=COLORS['bg_card'],
                fg=COLORS['text_primary'],
                relief=tk.FLAT,
                highlightthickness=1,
                highlightbackground=COLORS['border'],
                highlightcolor=COLORS['bg_button'],
                insertbackground=COLORS['text_primary'],
            )
            return ent

        self.lbl_filter_exts = tk.Label(
            filters_grid,
            text='',
            bg=COLORS['bg_card'],
            fg=COLORS['text_secondary'],
            anchor='w',
        )
        self.lbl_filter_exts.grid(row=0, column=0, sticky='w', padx=(0, 10), pady=(0, 10))
        self.ent_filter_exts = _mk_entry(filters_grid, self.var_filter_exts)
        self.ent_filter_exts.grid(row=0, column=1, sticky='ew', pady=(0, 10))

        self.lbl_filter_include = tk.Label(
            filters_grid,
            text='',
            bg=COLORS['bg_card'],
            fg=COLORS['text_secondary'],
            anchor='w',
        )
        self.lbl_filter_include.grid(row=1, column=0, sticky='w', padx=(0, 10), pady=(0, 10))
        self.ent_filter_include = _mk_entry(filters_grid, self.var_filter_include)
        self.ent_filter_include.grid(row=1, column=1, sticky='ew', pady=(0, 10))

        self.lbl_filter_exclude = tk.Label(
            filters_grid,
            text='',
            bg=COLORS['bg_card'],
            fg=COLORS['text_secondary'],
            anchor='w',
        )
        self.lbl_filter_exclude.grid(row=2, column=0, sticky='w', padx=(0, 10))
        self.ent_filter_exclude = _mk_entry(filters_grid, self.var_filter_exclude)
        self.ent_filter_exclude.grid(row=2, column=1, sticky='ew')

        sep2 = tk.Frame(opt_inner, bg=COLORS['border'], height=1)
        sep2.pack(fill=tk.X, pady=(12, 10))

        conflict_row = tk.Frame(opt_inner, bg=COLORS['bg_card'])
        conflict_row.pack(fill=tk.X)

        self.conflict_label = tk.Label(conflict_row, text='', bg=COLORS['bg_card'], fg=COLORS['text_secondary'])
        self.conflict_label.pack(side=tk.LEFT)

        self.btn_preview_conflict = PillButton(
            conflict_row,
            text='',
            height=30,
            radius=15,
            fill=COLORS['bg_card'],
            fill_hover=COLORS['bg_drop_hover'],
            outline=COLORS['border'],
            outline_width=1,
            fg=COLORS['bg_button'],
            font=self._font(11, 'bold'),
            command=self._open_conflict_preview,
        )
        self.btn_preview_conflict.pack(side=tk.RIGHT, padx=(10, 0))

        self.btn_preview_diff = PillButton(
            conflict_row,
            text='',
            height=30,
            radius=15,
            fill=COLORS['bg_card'],
            fill_hover=COLORS['bg_drop_hover'],
            outline=COLORS['border'],
            outline_width=1,
            fg=COLORS['bg_button'],
            font=self._font(11, 'bold'),
            command=self._open_diff_preview,
        )
        self.btn_preview_diff.pack(side=tk.RIGHT)

        # ---- Actions (fixed bottom) ----
        act_card = RoundedFrame(left_outer, radius=16)
        act_card.grid(row=1, column=0, sticky='ew', pady=(12, 0))

        act = tk.Frame(act_card.inner_frame, bg=COLORS['bg_card'], padx=16, pady=14)
        act.pack(fill=tk.BOTH, expand=True)

        # 主按钮：白底 + 彩色描边（更接近参考 UI 的“胶囊”风格）
        self.btn_start = PillButton(
            act,
            text='',
            height=54,
            radius=27,
            fill=COLORS['bg_button'],
            fill_hover=COLORS['bg_button_hover'],
            outline='',
            outline_width=0,
            fg=COLORS['text_button'],
            font=self._font(13, 'bold'),
            state=tk.DISABLED,
            command=self._start_processing,
        )
        self.btn_start.pack(fill=tk.X)

        self.btn_cancel = PillButton(
            act,
            text='',
            height=54,
            radius=27,
            fill=COLORS['bg_danger'],
            fill_hover=COLORS['bg_danger_hover'],
            outline='',
            outline_width=0,
            fg=COLORS['text_button'],
            font=self._font(13, 'bold'),
            state=tk.DISABLED,
            command=self._cancel_processing,
        )
        self.btn_cancel.pack(fill=tk.X, pady=(12, 0))

        self.btn_undo = PillButton(
            act,
            text='',
            height=50,
            radius=25,
            fill=COLORS['bg_drop'],
            fill_hover=COLORS['bg_drop_hover'],
            outline='',
            outline_width=0,
            fg=COLORS['text_primary'],
            font=self._font(12),
            state=tk.DISABLED,
            command=self._start_undo,
        )
        self.btn_undo.pack(fill=tk.X, pady=(12, 0))

        # ---- Right: Preview (always visible) ----
        preview_card = RoundedFrame(right, radius=16, autosize=False)
        preview_card.grid(row=0, column=0, sticky='nsew')
        prev = tk.Frame(preview_card.inner_frame, bg=COLORS['bg_card'], padx=12, pady=12)
        prev.pack(fill=tk.BOTH, expand=True)
        prev.grid_rowconfigure(2, weight=1)
        prev.grid_columnconfigure(0, weight=1)

        header = tk.Frame(prev, bg=COLORS['bg_card'])
        header.grid(row=0, column=0, sticky='ew')
        header.grid_columnconfigure(0, weight=1)

        self.preview_title = tk.Label(header, text='', bg=COLORS['bg_card'], fg=COLORS['text_primary'])
        self.preview_title.grid(row=0, column=0, sticky='w')

        self._preview_count_label = tk.Label(header, text='', bg=COLORS['bg_card'], fg=COLORS['text_secondary'])
        self._preview_count_label.grid(row=0, column=1, sticky='e')

        tb = tk.Frame(prev, bg=COLORS['bg_card'])
        tb.grid(row=1, column=0, sticky='ew', pady=(10, 10))
        tb.grid_columnconfigure(0, weight=1)

        self._preview_var_query = tk.StringVar(value='')
        self._preview_var_only_changed = tk.BooleanVar(value=True)
        self._preview_var_only_conflict = tk.BooleanVar(value=False)

        self.preview_search = tk.Entry(
            tb,
            textvariable=self._preview_var_query,
            bg=COLORS['bg_card'],
            fg=COLORS['text_primary'],
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=COLORS['border'],
            highlightcolor=COLORS['bg_button'],
            insertbackground=COLORS['text_primary'],
        )
        self.preview_search.grid(row=0, column=0, sticky='ew')

        self.preview_chk_changed = ttk.Checkbutton(tb, variable=self._preview_var_only_changed, style='Card.TCheckbutton')
        self.preview_chk_changed.grid(row=0, column=1, sticky='e', padx=(10, 0))

        self.preview_chk_conflict = ttk.Checkbutton(tb, variable=self._preview_var_only_conflict, style='Card.TCheckbutton')
        self.preview_chk_conflict.grid(row=0, column=2, sticky='e', padx=(10, 0))

        table = tk.Frame(prev, bg=COLORS['bg_card'])
        table.grid(row=2, column=0, sticky='nsew')
        table.grid_rowconfigure(0, weight=1)
        table.grid_columnconfigure(0, weight=1)

        columns = ('old', 'new', 'summary')
        tree = ttk.Treeview(table, columns=columns, show='headings', selectmode='browse')
        self._preview_tree = tree

        tree.heading('old', text='')
        tree.heading('new', text='')
        tree.heading('summary', text='')

        tree.column('old', width=340, anchor='w')
        tree.column('new', width=520, anchor='w')
        tree.column('summary', width=200, anchor='w')

        vsb = ttk.Scrollbar(table, orient='vertical', style='Pill.Vertical.TScrollbar', command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)

        tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')

        try:
            tree.tag_configure('rename', background='#FFFBEB')
            tree.tag_configure('conflict', background='#FFF1F0')
            tree.tag_configure('skip', foreground=COLORS['text_secondary'])
        except Exception:
            pass

        tree.bind('<<TreeviewSelect>>', self._preview_on_select)

        detail = tk.Text(
            prev,
            height=4,
            bg=COLORS['bg_card'],
            fg=COLORS['text_primary'],
            relief=tk.FLAT,
            borderwidth=0,
            wrap=tk.WORD,
            padx=10,
            pady=8,
        )
        self._preview_detail = detail
        detail.grid(row=3, column=0, sticky='ew', pady=(12, 0))
        detail.tag_config('title', font=self._font(10, 'bold'), foreground=COLORS['text_primary'])
        detail.tag_config('muted', font=self._font(10), foreground=COLORS['text_secondary'])
        detail.tag_config('diff_old', background='#FFE5E5')
        detail.tag_config('diff_new', background='#E8FFF1')
        detail.configure(state=tk.DISABLED)

        self._preview_var_query.trace_add('write', lambda *_: self._preview_apply_filters())
        self._preview_var_only_changed.trace_add('write', lambda *_: self._preview_apply_filters())
        self._preview_var_only_conflict.trace_add('write', lambda *_: self._preview_apply_filters())

        # ---------------- Right: Log card (aligned under preview) ----------------
        log_card = RoundedFrame(right, radius=16, autosize=False)
        log_card.grid(row=1, column=0, sticky='nsew', pady=(12, 0))
        log_inner = tk.Frame(log_card.inner_frame, bg=COLORS['bg_card'], padx=14, pady=12)
        log_inner.pack(fill=tk.BOTH, expand=True)

        title_row = tk.Frame(log_inner, bg=COLORS['bg_card'])
        title_row.pack(fill=tk.X)

        self.log_title = tk.Label(title_row, text='', bg=COLORS['bg_card'], fg=COLORS['text_primary'])
        self.log_title.pack(side=tk.LEFT)

        self.btn_clear = PillButton(
            title_row,
            text='',
            height=30,
            radius=15,
            fill=COLORS['bg_card'],
            fill_hover=COLORS['bg_drop_hover'],
            outline=COLORS['border'],
            outline_width=1,
            fg=COLORS['bg_button'],
            font=self._font(11, 'bold'),
            command=self._clear_log,
        )
        self.btn_clear.pack(side=tk.RIGHT)

        self.status_label = tk.Label(title_row, text='', bg=COLORS['bg_card'], fg=COLORS['text_secondary'])
        self.status_label.pack(side=tk.RIGHT, padx=(0, 10))

        self.progress = ttk.Progressbar(log_inner, mode='determinate')
        self.progress.pack(fill=tk.X, pady=(10, 10))

        log_text_wrap = tk.Frame(log_inner, bg=COLORS['bg_card'])
        log_text_wrap.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(
            log_text_wrap,
            bg=COLORS['bg_card'],
            fg=COLORS['text_primary'],
            relief=tk.FLAT,
            borderwidth=0,
            wrap=tk.WORD,
            padx=10,
            pady=8,
            state=tk.DISABLED,
        )
        log_vsb = ttk.Scrollbar(
            log_text_wrap,
            orient='vertical',
            style='Pill.Vertical.TScrollbar',
            command=self.log_text.yview,
        )
        self.log_text.configure(yscrollcommand=log_vsb.set)

        self.log_text.grid(row=0, column=0, sticky='nsew')
        log_vsb.grid(row=0, column=1, sticky='ns', padx=(8, 0))

        log_text_wrap.grid_rowconfigure(0, weight=1)
        log_text_wrap.grid_columnconfigure(0, weight=1)

        self.log_text.tag_config('success', foreground=COLORS['success'])
        self.log_text.tag_config('error', foreground=COLORS['error'])
        self.log_text.tag_config('warning', foreground=COLORS['warning'])
        self.log_text.tag_config('skip', foreground=COLORS['text_secondary'])
        self.log_text.tag_config('info', foreground=COLORS['text_primary'])
        self.log_text.tag_config('preview', foreground=COLORS['warning'])

    def _setup_traces(self):
        # re-calc conflict estimate when options/filters change
        vars_to_watch = [
            self.var_include_subfolders,
            self.var_dry_run,
            self.var_date_source,
            self.var_filter_exts,
            self.var_filter_include,
            self.var_filter_exclude,
        ]
        for v in vars_to_watch:
            try:
                v.trace_add('write', lambda *_args: (self._schedule_precheck(), self._schedule_preview()))
            except Exception:
                pass

    def _set_conflict_display(self, text: str, conflicts: list[dict] | None = None):
        if conflicts is not None:
            self._last_conflicts = conflicts
            self._conflict_count = len(conflicts)

        self.conflict_label.config(text=text, font=self._font(11))
        if self.target_path and (not self.processing):
            self.btn_preview_diff.config(state=tk.NORMAL)
        else:
            self.btn_preview_diff.config(state=tk.DISABLED)

        if self._last_conflicts and (not self.processing):
            self.btn_preview_conflict.config(state=tk.NORMAL)
        else:
            self.btn_preview_conflict.config(state=tk.DISABLED)

    def _schedule_precheck(self):
        if self.processing:
            return

        t = TEXTS[self.language]

        if not self.target_path:
            self._last_conflicts = []
            self._conflict_count = None
            self._set_conflict_display(t['conflict_unknown'], conflicts=[])
            return

        # debounce
        if self._precheck_after_id:
            try:
                self.after_cancel(self._precheck_after_id)
            except Exception:
                pass
            self._precheck_after_id = None

        self.conflict_label.config(text=t['conflict_calc'], font=self._font(11))
        self.btn_preview_conflict.config(state=tk.DISABLED)

        self._precheck_after_id = self.after(250, self._run_precheck_async)

    def _schedule_preview(self):
        """预览刷新防抖：避免输入时频繁启动线程。"""
        if self.processing:
            return
        if not self.target_path:
            self._preview_rows = []
            self._preview_set_data([])
            return

        if getattr(self, '_preview_after_id', None):
            try:
                self.after_cancel(self._preview_after_id)
            except Exception:
                pass
            self._preview_after_id = None

        t = TEXTS[self.language]
        if self._preview_count_label is not None:
            self._preview_count_label.config(text=t['preview_calculating'], font=self._font(11))

        self._preview_after_id = self.after(250, self._start_preview_async)

    def _run_precheck_async(self):
        if self.processing or not self.target_path:
            return

        self._precheck_token += 1
        token = self._precheck_token

        opts = RenameOptions(
            include_subfolders=bool(self.var_include_subfolders.get()),
            dry_run=False,
            date_source=str(self.var_date_source.get()).strip() or 'mtime',
            filter_exts=str(self.var_filter_exts.get()).strip(),
            filter_include=str(self.var_filter_include.get()).strip(),
            filter_exclude=str(self.var_filter_exclude.get()).strip(),
        )
        th = threading.Thread(
            target=self._precheck_worker,
            args=(token, self.target_path, self.is_single_file, opts),
            daemon=True,
        )
        self._precheck_inflight = True
        th.start()

        # ensure queue is drained even when not processing
        self.after(60, self._drain_queue)

    def _precheck_worker(self, token: int, target_path: str, is_single_file: bool, opts: RenameOptions):
        """Estimate conflicts based on a single RenamePlan."""
        try:
            plan = _build_rename_plan(
                target_path=target_path,
                is_single_file=is_single_file,
                opts=opts,
                language=self.language,
            )

            conflicts: list[dict] = []
            for it in plan.items:
                if it.status != 'rename':
                    continue
                if (it.conflict_index or 0) > 0 and it.base_name and it.final_name:
                    conflicts.append({
                        'folder': str(it.path.parent),
                        'original': it.original_name,
                        'base': it.base_name,
                        'final': it.final_name,
                    })

            self._q_put({'type': 'precheck', 'token': token, 'conflicts': conflicts})
        except Exception as e:
            self._q_put({'type': 'precheck', 'token': token, 'conflicts': [], 'error': str(e)})

    def _open_conflict_preview(self):
        """切到“只看冲突”，并在预览表格中定位。"""
        try:
            self._preview_var_only_conflict.set(True)
            self._preview_var_only_changed.set(True)
            self._preview_apply_filters()
            if self._preview_tree is not None:
                kids = self._preview_tree.get_children('')
                if kids:
                    self._preview_tree.selection_set(kids[0])
                    self._preview_tree.focus(kids[0])
                    self._preview_tree.see(kids[0])
        except Exception:
            pass

    def _open_diff_preview(self):
        """刷新预览（工作台右侧始终可见，无需弹窗）。"""
        self._start_preview_async()

    def _start_preview_async(self):
        if self.processing or not self.target_path:
            return

        self._preview_token += 1
        token = self._preview_token

        # options snapshot (same as rename run)
        opts = RenameOptions(
            include_subfolders=bool(self.var_include_subfolders.get()),
            dry_run=bool(self.var_dry_run.get()),
            date_source=str(self.var_date_source.get()).strip() or 'mtime',
            filter_exts=str(self.var_filter_exts.get()).strip(),
            filter_include=str(self.var_filter_include.get()).strip(),
            filter_exclude=str(self.var_filter_exclude.get()).strip(),
        )        # show calculating state
        t = TEXTS[self.language]
        if self._preview_count_label is not None:
            self._preview_count_label.config(text=t['preview_calculating'], font=self._font(11))

        # clear table
        if self._preview_tree is not None:
            for iid in self._preview_tree.get_children(''):
                self._preview_tree.delete(iid)

        if self._preview_detail is not None:
            self._preview_detail.configure(state=tk.NORMAL)
            self._preview_detail.delete('1.0', tk.END)
            self._preview_detail.insert(tk.END, t['preview_calculating'], 'muted')
            self._preview_detail.configure(state=tk.DISABLED)

        th = threading.Thread(
            target=self._preview_worker,
            args=(token, self.target_path, self.is_single_file, opts),
            daemon=True,
        )
        self._preview_inflight = True
        th.start()
        self.after(60, self._drain_queue)

    def _preview_worker(self, token: int, target_path: str, is_single_file: bool, opts: RenameOptions):
        """Build preview rows based on a single RenamePlan."""
        try:
            plan = _build_rename_plan(
                target_path=target_path,
                is_single_file=is_single_file,
                opts=opts,
                language=self.language,
            )

            rows: list[dict] = []
            for it in plan.items:
                final = it.final_name or it.original_name
                conflict = (it.conflict_index or 0) > 0
                suffix = f"_{it.conflict_index:03d}" if conflict else ''
                rows.append({
                    'original': it.original_name,
                    'final': final,
                    'summary': it.summary or it.error or '',
                    'changed': (it.status == 'rename') and (final != it.original_name),
                    'conflict': conflict,
                    'folder': str(it.path.parent),
                    'suffix': suffix,
                })

            self._q_put({'type': 'preview', 'token': token, 'rows': rows})
        except Exception as e:
            self._q_put({'type': 'preview', 'token': token, 'rows': [], 'error': str(e)})

    def _preview_set_data(self, rows: list[dict]):
        self._preview_rows = rows
        self._preview_apply_filters()

    def _preview_apply_filters(self):
        if self._preview_tree is None:
            return
        rows = self._preview_rows or []

        query = ''
        only_changed = True
        only_conflict = False

        if self._preview_var_query is not None:
            query = str(self._preview_var_query.get() or '').strip().lower()
        if self._preview_var_only_changed is not None:
            only_changed = bool(self._preview_var_only_changed.get())
        if self._preview_var_only_conflict is not None:
            only_conflict = bool(self._preview_var_only_conflict.get())

        filtered: list[dict] = []
        for r in rows:
            if only_conflict and not r.get('conflict'):
                continue
            if only_changed and not r.get('changed'):
                continue
            if query:
                hay = f"{r.get('original','')} {r.get('final','')} {r.get('summary','')} {r.get('folder','')}".lower()
                if query not in hay:
                    continue
            filtered.append(r)

        self._preview_populate_tree(filtered, total=len(rows))

    def _preview_populate_tree(self, rows: list[dict], total: int):
        if self._preview_tree is None:
            return
        tree = self._preview_tree

        # clear
        for iid in tree.get_children(''):
            tree.delete(iid)

        for r in rows:
            original = r.get('original', '')
            final = r.get('final', '')
            summary = r.get('summary', '')
            tag = 'skip'
            if r.get('changed'):
                tag = 'rename'
            if r.get('conflict'):
                tag = 'conflict'
            tree.insert('', 'end', values=(original, final, summary), tags=(tag,))

        # count label
        if self._preview_count_label is not None:
            t = TEXTS[self.language]
            self._preview_count_label.config(text=t['preview_count'].format(shown=len(rows), total=total), font=self._font(11))

        # detail default
        if self._preview_detail is not None:
            self._preview_detail.configure(state=tk.NORMAL)
            self._preview_detail.delete('1.0', tk.END)
            if rows:
                self._preview_detail.insert(tk.END, TEXTS[self.language]['preview_subtitle'], 'muted')
            else:
                self._preview_detail.insert(tk.END, TEXTS[self.language]['preview_no_data'], 'muted')
            self._preview_detail.configure(state=tk.DISABLED)

    def _preview_on_select(self, _event=None):
        if self._preview_tree is None or self._preview_detail is None:
            return
        sel = self._preview_tree.selection()
        if not sel:
            return
        iid = sel[0]
        vals = self._preview_tree.item(iid, 'values')
        if not vals or len(vals) < 3:
            return
        old_name, new_name, summary = vals[0], vals[1], vals[2]
        self._preview_render_detail_diff(old_name, new_name, summary)

    def _preview_render_detail_diff(self, old_name: str, new_name: str, summary: str):
        if self._preview_detail is None:
            return

        txt = self._preview_detail
        txt.configure(state=tk.NORMAL)
        txt.delete('1.0', tk.END)

        # OLD
        txt.insert(tk.END, 'OLD: ', 'muted')
        old_start = txt.index(tk.END)
        txt.insert(tk.END, old_name)
        txt.insert(tk.END, '\n')

        # NEW
        txt.insert(tk.END, 'NEW: ', 'muted')
        new_start = txt.index(tk.END)
        txt.insert(tk.END, new_name)
        txt.insert(tk.END, '\n')

        # SUMMARY
        t = TEXTS[self.language]
        txt.insert(tk.END, f"{t['preview_col_summary']}: ", 'muted')
        txt.insert(tk.END, summary)

        # Highlight diffs using SequenceMatcher
        try:
            sm = difflib.SequenceMatcher(a=old_name, b=new_name)
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag in ('delete', 'replace') and i2 > i1:
                    txt.tag_add('diff_old', f"{old_start}+{i1}c", f"{old_start}+{i2}c")
                if tag in ('insert', 'replace') and j2 > j1:
                    txt.tag_add('diff_new', f"{new_start}+{j1}c", f"{new_start}+{j2}c")
        except Exception:
            pass

        txt.configure(state=tk.DISABLED)


    # ---------- events ----------
    def _on_drop(self, event):
        if self.processing:
            return
        paths = _parse_dnd_paths(self, event.data)
        if not paths:
            return
        if len(paths) > 1:
            self._append_log(TEXTS[self.language]['drop_multi'].format(Path(paths[0]).name), 'warning')
        self._select_path(paths[0])

    def _on_click_select(self, _event=None):
        if self.processing:
            return
        from tkinter import filedialog

        t = TEXTS[self.language]
        choice = messagebox.askyesnocancel(t['select_type_title'], t['select_type_message'])
        if choice is True:
            path = filedialog.askdirectory(title=t['select_folder_title'])
        elif choice is False:
            path = filedialog.askopenfilename(title=t['select_file_title'])
        else:
            return

        if path:
            self._select_path(path)


    def _choose_folder(self):
        if self.processing:
            return
        from tkinter import filedialog
        t = TEXTS[self.language]
        path = filedialog.askdirectory(title=t['select_folder_title'])
        if path:
            self._select_path(path)

    def _choose_file(self):
        if self.processing:
            return
        from tkinter import filedialog
        t = TEXTS[self.language]
        path = filedialog.askopenfilename(title=t['select_file_title'])
        if path:
            self._select_path(path)

    def _choose_path(self):
        # Backward-compatible alias for older bindings
        return self._on_click_select()
    def _select_path(self, path_str: str):
        p = Path(path_str)
        t = TEXTS[self.language]

        if not p.exists():
            messagebox.showerror('Error', t['error_path_not_exist'].format(path_str))
            return

        if p.is_dir():
            self.target_path = str(p)
            self.is_single_file = False
            self.path_label.config(text=t['selected_folder'].format(str(p)), fg=COLORS['success'], font=self._font(12))
        elif p.is_file():
            self.target_path = str(p)
            self.is_single_file = True
            self.path_label.config(text=t['selected_file'].format(p.name), fg=COLORS['success'], font=self._font(12))
        else:
            messagebox.showerror('Error', t['error_invalid_path'].format(path_str))
            return

        self.btn_start.config(state=tk.NORMAL)
        self._progress_mode = 'rename'
        self._clear_log()
        self._schedule_precheck()
        self._schedule_preview()

    # ---------- log helpers ----------


    def _clear_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete('1.0', tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _clear_filters(self):
        """Clear filter fields (extensions / include / exclude)."""
        try:
            self.var_filter_exts.set('')
            self.var_filter_include.set('')
            self.var_filter_exclude.set('')
        except Exception:
            pass

        # refresh preview/conflict estimation
        try:
            self._schedule_precheck()
            self._schedule_preview()
        except Exception:
            pass

        try:
            self.ent_filter_exts.focus_set()
        except Exception:
            pass


    def _append_log(self, msg: str, tag: str = 'info'):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + '\n', tag)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)


    # ---------- processing ----------


    def _refresh_undo_state(self):
        """Enable/disable undo button based on persistent history."""
        try:
            if not hasattr(self, 'btn_undo'):
                return
            if self.processing:
                self.btn_undo.config(state=tk.DISABLED)
                return
            items = _load_history()
            _, entry = _find_last_undoable(items)
            self.btn_undo.config(state=(tk.NORMAL if entry else tk.DISABLED))
        except Exception:
            try:
                self.btn_undo.config(state=tk.DISABLED)
            except Exception:
                pass
    def _undo_last(self):
        """Alias kept for older UI bindings (undo last rename batch)."""
        return self._start_undo()



    def _start_undo(self):
        if self.processing:
            return

        t = TEXTS[self.language]
        items = _load_history()
        _idx, entry = _find_last_undoable(items)
        if not entry:
            try:
                messagebox.showinfo(t['undo_confirm_title'], t['undo_no_history'])
            except Exception:
                pass
            self._refresh_undo_state()
            return

        ops = entry.get('ops') or []
        if not isinstance(ops, list) or not ops:
            try:
                messagebox.showinfo(t['undo_confirm_title'], t['undo_no_history'])
            except Exception:
                pass
            self._refresh_undo_state()
            return

        n = len(ops)
        try:
            ok = messagebox.askyesno(t['undo_confirm_title'], t['undo_confirm_msg'].format(n=n))
        except Exception:
            ok = False
        if not ok:
            return

        self._progress_mode = 'undo'
        self._clear_log()
        self._cancel_event.clear()
        self.progress['value'] = 0
        self.progress['maximum'] = max(n, 1)

        self._set_processing_ui(True)
        self._q_put({'type': 'log', 'tag': 'info', 'msg': t['undo_started'].format(n=n)})

        entry_id = str(entry.get('id') or '')
        th = threading.Thread(target=self._worker_undo, args=(entry_id, ops), daemon=True)
        self._worker = th
        th.start()

        self.after(60, self._drain_queue)

    def _worker_undo(self, entry_id: str, ops: list[dict]):
        t = TEXTS[self.language]
        start = time.time()
        result = UndoResult(total=len(ops))

        try:
            self._q_put({'type': 'progress', 'current': 0, 'total': result.total})

            for idx, op in enumerate(reversed(ops), start=1):
                if self._cancel_event.is_set():
                    result.cancelled = True
                    self._q_put({'type': 'log', 'tag': 'warning', 'msg': t['undo_cancelled']})
                    break

                try:
                    new_path = Path(str(op.get('new') or ''))
                    old_path = Path(str(op.get('old') or ''))

                    if not new_path.exists():
                        result.skipped += 1
                        self._q_put({'type': 'log', 'tag': 'skip', 'msg': t['undo_skip_missing'].format(str(new_path))})
                        self._q_put({'type': 'progress', 'current': idx, 'total': result.total})
                        continue

                    if old_path.exists():
                        result.skipped += 1
                        self._q_put({'type': 'log', 'tag': 'warning', 'msg': t['undo_skip_conflict'].format(str(old_path), str(new_path))})
                        self._q_put({'type': 'progress', 'current': idx, 'total': result.total})
                        continue

                    _safe_rename(new_path, old_path)
                    result.restored += 1
                    self._q_put({'type': 'log', 'tag': 'success', 'msg': t['undo_success'].format(new_path.name, old_path.name)})

                except Exception as e:
                    result.errors += 1
                    self._q_put({'type': 'log', 'tag': 'error', 'msg': t['undo_error'].format(str(op.get('new') or op), str(e))})

                self._q_put({'type': 'progress', 'current': idx, 'total': result.total})

        finally:
            result.elapsed = time.time() - start

            if entry_id:
                try:
                    _mark_history_undone(entry_id, {
                        'restored': result.restored,
                        'skipped': result.skipped,
                        'errors': result.errors,
                        'cancelled': result.cancelled,
                        'total': result.total,
                        'elapsed': round(result.elapsed, 3),
                    })
                except Exception:
                    pass

            self._q_put({'type': 'undo_done', 'result': result})

    def _on_undo_done(self, result: UndoResult):
        t = TEXTS[self.language]

        if result.cancelled:
            self.status_label.config(text=t['status_cancelled'], font=self._font(12))
        else:
            self.status_label.config(text=t['undo_dialog_title'], font=self._font(12))

        self._set_processing_ui(False)
        self._refresh_undo_state()
        self._progress_mode = 'rename'
        self._refresh_undo_state()

        self._show_undo_result_dialog(result)

    def _show_undo_result_dialog(self, result: UndoResult):
        t = TEXTS[self.language]

        dialog = tk.Toplevel(self)
        dialog.title(t['undo_dialog_title'])
        dialog.configure(bg=COLORS['bg_main'])
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        outer = tk.Frame(dialog, bg=COLORS['bg_main'], padx=26, pady=24)
        outer.pack(fill=tk.BOTH, expand=True)

        icon = '↩'
        icon_color = COLORS['success'] if (not result.cancelled and result.errors == 0) else COLORS['warning']
        tk.Label(outer, text=icon, font=self._font(56, 'bold'), bg=COLORS['bg_main'], fg=icon_color).pack(pady=(0, 6))

        tk.Label(
            outer,
            text=t['undo_dialog_title'] if not result.cancelled else t['status_cancelled'],
            font=self._font(22, 'bold'),
            bg=COLORS['bg_main'],
            fg=COLORS['text_primary'],
        ).pack(pady=(0, 14))

        card = RoundedFrame(outer, radius=16)
        card.pack(fill=tk.X)

        inner = tk.Frame(card.inner_frame, bg=COLORS['bg_card'], padx=18, pady=16)
        inner.pack(fill=tk.X)

        def row(label: str, value: str, color: str = COLORS['text_primary']):
            r = tk.Frame(inner, bg=COLORS['bg_card'])
            r.pack(fill=tk.X, pady=4)
            tk.Label(r, text=label, font=self._font(13), bg=COLORS['bg_card'], fg=COLORS['text_secondary']).pack(side=tk.LEFT)
            tk.Label(r, text=value, font=self._font(13, 'bold'), bg=COLORS['bg_card'], fg=color).pack(side=tk.RIGHT)

        row(t['undo_ok_label'], str(result.restored), COLORS['success'])
        row(t['undo_skip_label'], str(result.skipped), COLORS['warning'])
        row(t['error_label'], str(result.errors), COLORS['error'])
        row(t['time_label'], f"{result.elapsed:.2f}" + t['time_unit'], COLORS['text_secondary'])

        btn = PillButton(
            outer,
            text=t['close'],
            height=44,
            radius=22,
            fill=COLORS['bg_button'],
            fill_hover=COLORS['bg_button_hover'],
            outline=COLORS['bg_button'],
            outline_width=0,
            fg=COLORS['text_button'],
            font=self._font(11, 'bold'),
            command=dialog.destroy,
        )
        btn.pack(pady=(16, 0))

        self._center_dialog(dialog)

    def _set_processing_ui(self, is_processing: bool):
        self.processing = is_processing

        if is_processing:
            self.btn_start.config(state=tk.DISABLED)
            self.btn_cancel.config(state=tk.NORMAL)
            self.btn_lang.config(state=tk.DISABLED)
            self.btn_undo.config(state=tk.DISABLED)

            self.chk_subfolders.config(state=tk.DISABLED)
            self.chk_dryrun.config(state=tk.DISABLED)
            if hasattr(self, 'rb_mtime'):
                self.rb_mtime.config(state=tk.DISABLED)
                self.rb_ctime.config(state=tk.DISABLED)
                self.rb_exif.config(state=tk.DISABLED)
            self.ent_filter_exts.config(state=tk.DISABLED)
            self.ent_filter_include.config(state=tk.DISABLED)
            self.ent_filter_exclude.config(state=tk.DISABLED)

            self.btn_preview_conflict.config(state=tk.DISABLED)
            self.btn_preview_diff.config(state=tk.DISABLED)
            self.drop_area.config(cursor='arrow')
        else:
            self.btn_cancel.config(state=tk.DISABLED)
            self.btn_lang.config(state=tk.NORMAL)

            self.chk_subfolders.config(state=tk.NORMAL)
            self.chk_dryrun.config(state=tk.NORMAL)
            if hasattr(self, 'rb_mtime'):
                self.rb_mtime.config(state=tk.NORMAL)
                self.rb_ctime.config(state=tk.NORMAL)
                self.rb_exif.config(state=tk.NORMAL)
            self.ent_filter_exts.config(state=tk.NORMAL)
            self.ent_filter_include.config(state=tk.NORMAL)
            self.ent_filter_exclude.config(state=tk.NORMAL)

            self.drop_area.config(cursor='hand2')

            if self.target_path:
                self.btn_start.config(state=tk.NORMAL)
                self.btn_preview_diff.config(state=tk.NORMAL)
            else:
                self.btn_start.config(state=tk.DISABLED)
                self.btn_preview_diff.config(state=tk.DISABLED)

            # refresh conflict estimate after processing
            self._schedule_precheck()
            self._refresh_undo_state()

    def _start_processing(self):
        if not self.target_path or self.processing:
            return

        self._progress_mode = 'rename'
        self._clear_log()
        self._cancel_event.clear()
        self.progress['value'] = 0
        self.progress['maximum'] = 100

        self._set_processing_ui(True)

        # options snapshot
        opts = RenameOptions(
            include_subfolders=bool(self.var_include_subfolders.get()),
            dry_run=bool(self.var_dry_run.get()),
            date_source=str(self.var_date_source.get()).strip() or 'mtime',
            filter_exts=str(self.var_filter_exts.get()).strip(),
            filter_include=str(self.var_filter_include.get()).strip(),
            filter_exclude=str(self.var_filter_exclude.get()).strip(),
        )
        # start worker
        self._worker = threading.Thread(
            target=self._worker_run,
            args=(self.target_path, self.is_single_file, opts),
            daemon=True,
        )
        self._worker.start()

        # start draining queue
        self.after(50, self._drain_queue)

    def _cancel_processing(self):
        if self.processing:
            self._cancel_event.set()

    def _q_put(self, event: dict):
        self._q.put(event)

    def _drain_queue(self):
        drained_any = False
        try:
            while True:
                ev = self._q.get_nowait()
                drained_any = True

                et = ev.get('type')
                if et == 'log':
                    self._append_log(ev.get('msg', ''), ev.get('tag', 'info'))
                elif et == 'progress':
                    cur = int(ev.get('current', 0))
                    tot = int(ev.get('total', 0))
                    self.progress['maximum'] = max(tot, 1)
                    self.progress['value'] = cur
                    t = TEXTS[self.language]
                    key = 'status_undoing' if getattr(self, '_progress_mode', 'rename') == 'undo' else 'status_processing'
                    self.status_label.config(text=t[key].format(cur, tot), font=self._font(12))
                elif et == 'precheck':
                    token = int(ev.get('token', 0))
                    if token != self._precheck_token:
                        continue
                    conflicts = ev.get('conflicts', []) or []
                    err = ev.get('error')
                    if err:
                        self._last_conflicts = []
                        self._conflict_count = 0
                        self._set_conflict_display(f"{TEXTS[self.language]['conflict_unknown']} ({err})", conflicts=[])
                        self._precheck_inflight = False
                    else:
                        self._last_conflicts = conflicts
                        self._conflict_count = len(conflicts)
                        self._set_conflict_display(TEXTS[self.language]['conflict_estimate'].format(n=len(conflicts)), conflicts=conflicts)
                        self._precheck_inflight = False

                elif et == 'preview':
                    token = int(ev.get('token', 0))
                    if token != self._preview_token:
                        continue
                    err = ev.get('error')
                    rows = ev.get('rows', []) or []
                    self._preview_rows = rows
                    self._preview_inflight = False
                    if err:
                        try:
                            messagebox.showerror('Error', err)
                        except Exception:
                            pass
                    self._preview_set_data(rows)
                    

                elif et == 'done':
                    result: RenameResult = ev['result']
                    self._on_processing_done(result)

                elif et == 'undo_done':
                    result: UndoResult = ev['result']
                    self._on_undo_done(result)
                else:
                    pass
        except queue.Empty:
            pass

        # continue polling if still processing or queue not empty
        if self.processing or self._precheck_inflight or self._preview_inflight:
            self.after(60 if drained_any else 120, self._drain_queue)

    def _on_processing_done(self, result: RenameResult):
        t = TEXTS[self.language]

        if result.cancelled:
            self.status_label.config(text=t['status_cancelled'], font=self._font(12))
        else:
            self.status_label.config(text=t['processing_complete'], font=self._font(12))

        self._set_processing_ui(False)
        self._refresh_undo_state()
        self._show_result_dialog(result)

    # ---------- worker ----------
    def _worker_run(self, target_path: str, is_single_file: bool, opts: RenameOptions):
        t = TEXTS[self.language]
        start = time.time()
        result = RenameResult()
        ops: list[dict] = []  # for undo history (only real renames)

        try:
            # 1) Build a unified plan (also applies filters + simulates conflicts)
            plan = _build_rename_plan(
                target_path=target_path,
                is_single_file=is_single_file,
                opts=opts,
                language=self.language,
                cancel_event=self._cancel_event,
            )

            if is_single_file:
                self._q_put({'type': 'log', 'tag': 'info', 'msg': t['processing_single'].format(Path(target_path).name)})
            else:
                self._q_put({'type': 'log', 'tag': 'info', 'msg': t['processing_folder'].format(plan.scanned)})

            if plan.cancelled:
                result.cancelled = True
                self._q_put({'type': 'log', 'tag': 'warning', 'msg': t['processing_cancelled']})
                result.total = 0
                return

            if plan.scanned == 0:
                self._q_put({'type': 'log', 'tag': 'warning', 'msg': t['no_files']})
                result.total = 0
                return

            # scan warnings (best-effort)
            if plan.scan_errors:
                # only show a few to avoid spamming logs
                for msg in plan.scan_errors[:3]:
                    self._q_put({'type': 'log', 'tag': 'warning', 'msg': f"{t['warning'] if 'warning' in t else 'Warning'}: {msg}"})

            # filter summary
            result.filtered = plan.filtered_out
            if result.filtered:
                self._q_put({'type': 'log', 'tag': 'info', 'msg': t['filter_summary'].format(before=plan.scanned, after=plan.matched, filtered=plan.filtered_out)})

            if plan.matched == 0:
                self._q_put({'type': 'log', 'tag': 'warning', 'msg': t['no_files_after_filter']})
                result.total = 0
                return

            result.total = len(plan.items)
            self._q_put({'type': 'progress', 'current': 0, 'total': result.total})

            # 2) Execute the plan
            for i, it in enumerate(plan.items, start=1):
                if self._cancel_event.is_set():
                    result.cancelled = True
                    self._q_put({'type': 'log', 'tag': 'warning', 'msg': t['processing_cancelled']})
                    break

                src = it.path
                original_name = it.original_name

                try:
                    if it.status == 'skip_prefix':
                        result.skipped += 1
                        self._q_put({'type': 'log', 'tag': 'skip', 'msg': t['skip'].format(original_name)})
                        self._q_put({'type': 'progress', 'current': i, 'total': result.total})
                        continue

                    if it.status == 'error':
                        result.errors += 1
                        self._q_put({'type': 'log', 'tag': 'error', 'msg': t['error'].format(str(src), it.error or 'unknown error')})
                        self._q_put({'type': 'progress', 'current': i, 'total': result.total})
                        continue

                    # rename item
                    final_name = it.final_name or original_name
                    base_name = it.base_name or final_name

                    if (it.conflict_index or 0) > 0:
                        result.conflicts += 1
                        self._q_put({'type': 'log', 'tag': 'warning', 'msg': t['conflict_resolved'].format(base_name, final_name)})

                    if opts.dry_run:
                        result.renamed += 1
                        self._q_put({'type': 'log', 'tag': 'preview', 'msg': t['preview_rename'].format(original_name, final_name) + (f" ({t['summary_exif_fallback']})" if it.note_code else '')})
                    else:
                        dst = src.with_name(final_name)
                        _safe_rename(src, dst)
                        ops.append({'old': str(src), 'new': str(dst)})
                        result.renamed += 1
                        self._q_put({'type': 'log', 'tag': 'success', 'msg': t['success_rename'].format(original_name, final_name) + (f" ({t['summary_exif_fallback']})" if it.note_code else '')})
                except Exception as e:
                    result.errors += 1
                    self._q_put({'type': 'log', 'tag': 'error', 'msg': t['error'].format(str(src), str(e))})

                self._q_put({'type': 'progress', 'current': i, 'total': result.total})

        finally:
            result.elapsed = time.time() - start

            # persist undo history (only when real renames occurred)
            if (not opts.dry_run) and ops:
                try:
                    entry = {
                        'id': uuid4().hex,
                        'ts': datetime.now().isoformat(timespec='seconds'),
                        'target_path': target_path,
                        'is_single_file': bool(is_single_file),
                        'options': {
                            'include_subfolders': bool(opts.include_subfolders),
                            'dry_run': bool(opts.dry_run),
                            'date_source': str(opts.date_source),
                            'filter_exts': str(opts.filter_exts),
                            'filter_include': str(opts.filter_include),
                            'filter_exclude': str(opts.filter_exclude),
                        },
                        'ops': ops,
                        'status': 'done',
                        'cancelled': bool(result.cancelled),
                    }
                    _append_history_entry(entry)
                except Exception:
                    pass

            self._q_put({'type': 'done', 'result': result})

    # ---------- dialogs ----------
    def _show_result_dialog(self, result: RenameResult):
        t = TEXTS[self.language]

        dialog = tk.Toplevel(self)
        dialog.title(t['dialog_title_cancel'] if result.cancelled else t['dialog_title'])
        dialog.configure(bg=COLORS['bg_main'])
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        outer = tk.Frame(dialog, bg=COLORS['bg_main'], padx=26, pady=24)
        outer.pack(fill=tk.BOTH, expand=True)

        icon = '✓' if (not result.cancelled and result.errors == 0) else '⚠'
        icon_color = COLORS['success'] if (not result.cancelled and result.errors == 0) else COLORS['warning']
        tk.Label(outer, text=icon, font=self._font(56, 'bold'), bg=COLORS['bg_main'], fg=icon_color).pack(pady=(0, 6))

        tk.Label(
            outer,
            text=t['dialog_title_cancel'] if result.cancelled else t['dialog_title'],
            font=self._font(22, 'bold'),
            bg=COLORS['bg_main'],
            fg=COLORS['text_primary'],
        ).pack(pady=(0, 14))

        card = RoundedFrame(outer, radius=16)
        card.pack(fill=tk.X)

        inner = tk.Frame(card.inner_frame, bg=COLORS['bg_card'], padx=22, pady=18)
        inner.pack(fill=tk.BOTH, expand=True)

        rows = [
            (t['success_rename_label'], result.renamed, COLORS['success']),
            (t['skip_label'], result.skipped, COLORS['text_secondary']),
            (t['filtered_label'], result.filtered, COLORS['text_secondary']),
            (t['conflict_label'], result.conflicts, COLORS['warning'] if result.conflicts > 0 else COLORS['text_secondary']),
            (t['error_label'], result.errors, COLORS['warning'] if result.errors > 0 else COLORS['text_secondary']),
        ]

        for label, value, color in rows:
            line = tk.Frame(inner, bg=COLORS['bg_card'])
            line.pack(fill=tk.X, pady=6)
            tk.Label(line, text=label, font=self._font(13), bg=COLORS['bg_card'], fg=COLORS['text_secondary']).pack(side=tk.LEFT)
            tk.Label(line, text=str(value), font=self._font(13, 'bold'), bg=COLORS['bg_card'], fg=color).pack(side=tk.RIGHT)

        line = tk.Frame(inner, bg=COLORS['bg_card'])
        line.pack(fill=tk.X, pady=(12, 0))
        tk.Label(line, text=t['time_label'], font=self._font(13), bg=COLORS['bg_card'], fg=COLORS['text_secondary']).pack(side=tk.LEFT)
        tk.Label(line, text=f"{result.elapsed:.2f}{t['time_unit']}", font=self._font(13, 'bold'), bg=COLORS['bg_card'], fg=COLORS['text_primary']).pack(side=tk.RIGHT)

        btn = PillButton(
            outer,
            text=t['close'],
            height=44,
            radius=22,
            fill=COLORS['bg_button'],
            fill_hover=COLORS['bg_button_hover'],
            outline=COLORS['bg_button'],
            outline_width=0,
            fg=COLORS['text_button'],
            font=self._font(11, 'bold'),
            command=dialog.destroy,
        )
        btn.pack(pady=(16, 0))


def main():
    app = RenameApp()
    app.mainloop()


if __name__ == '__main__':
    main()
