#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
自动重命名脚本 - 图形界面版本
支持拖放文件夹，实时显示处理过程，完成后显示统计信息
"""

import os
import sys
import time
import threading
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from tkinterdnd2 import DND_FILES, TkinterDnD

# 颜色方案（苹果风格）
COLORS = {
    'bg_main': '#F5F5F7',  # 浅灰背景
    'bg_card': '#FFFFFF',  # 白色卡片
    'bg_drop': '#E8E8ED',  # 拖放区域背景
    'bg_button': '#007AFF',  # 系统蓝
    'bg_button_hover': '#0051D5',
    'bg_button_active': '#007AFF',
    'text_primary': '#1D1D1F',  # 深色文字
    'text_secondary': '#86868B',  # 次要文字
    'text_button': '#FFFFFF',  # 按钮文字
    'border': '#D2D2D7',  # 边框
    'success': '#34C759',  # 成功绿
    'warning': '#FF9500',  # 警告橙
}

# 中英文文本映射
TEXTS = {
    'zh': {
        'title': '文件自动重命名',
        'subtitle': '根据文件修改时间添加日期前缀',
        'drop_area': '拖放文件夹或单个文件到这里\n或点击选择',
        'selected_folder': '已选择文件夹：{}',
        'selected_file': '已选择文件：{}',
        'start_process': '开始处理',
        'log_title': '处理日志',
        'processing_single': '处理单个文件：{}\n',
        'processing_folder': '找到 {} 个文件，开始处理...\n',
        'no_files': '文件夹中没有文件。',
        'skip': '跳过：{} （已有日期前缀）',
        'warning_exists': '警告：{} 已存在，跳过：{}',
        'success_rename': '✓ {} → {}',
        'error': "错误：处理 '{}' 时出错: {}",
        'processing_complete': '处理完成！\n',
        'dialog_title': '处理完成',
        'success_rename_label': '成功重命名',
        'skip_label': '跳过',
        'error_label': '错误',
        'time_label': '处理用时',
        'time_unit': ' 秒',
        'close': '关闭',
        'language_switch': 'English',
        'select_type_title': '选择类型',
        'select_type_message': '选择文件还是文件夹？\n\n点击\'是\'选择文件夹\n点击\'否\'选择单个文件',
        'select_folder_title': '选择要处理的文件夹',
        'select_file_title': '选择要处理的文件',
        'error_path_not_exist': '路径不存在：\n{}',
        'error_invalid_path': '无效的路径：\n{}',
    },
    'en': {
        'title': 'File Auto Rename',
        'subtitle': 'Add date prefix based on file modification time',
        'drop_area': 'Drag and drop folder or file here\nor click to select',
        'selected_folder': 'Selected folder: {}',
        'selected_file': 'Selected file: {}',
        'start_process': 'Start Processing',
        'log_title': 'Processing Log',
        'processing_single': 'Processing single file: {}\n',
        'processing_folder': 'Found {} files, starting processing...\n',
        'no_files': 'No files in folder.',
        'skip': 'Skip: {} (already has date prefix)',
        'warning_exists': 'Warning: {} already exists, skipping: {}',
        'success_rename': '✓ {} → {}',
        'error': "Error processing '{}': {}",
        'processing_complete': 'Processing complete!\n',
        'dialog_title': 'Processing Complete',
        'success_rename_label': 'Renamed',
        'skip_label': 'Skipped',
        'error_label': 'Errors',
        'time_label': 'Processing Time',
        'time_unit': ' seconds',
        'close': 'Close',
        'language_switch': '中文',
        'select_type_title': 'Select Type',
        'select_type_message': 'Select file or folder?\n\nClick \'Yes\' for folder\nClick \'No\' for single file',
        'select_folder_title': 'Select folder to process',
        'select_file_title': 'Select file to process',
        'error_path_not_exist': 'Path does not exist:\n{}',
        'error_invalid_path': 'Invalid path:\n{}',
    }
}

# 字体设置
CHINESE_FONT = '等线'  # 中文等线字体
ENGLISH_FONT = 'Arial'  # 英文无衬线字体


def get_font(size, weight='normal', lang='zh'):
    """获取字体"""
    if lang == 'zh':
        return (CHINESE_FONT, size, weight)
    else:
        return (ENGLISH_FONT, size, weight)


class RoundedFrame(tk.Frame):
    """圆角框架容器"""
    
    def __init__(self, parent, radius=12, bg_color='#FFFFFF', border_color='#D2D2D7', **kwargs):
        self.radius = radius
        self.bg_color = bg_color
        self.border_color = border_color
        
        # 创建画布
        parent_bg = parent.cget('bg') if 'bg' in parent.keys() else '#F5F5F7'
        self.canvas = tk.Canvas(
            parent,
            bg=parent_bg,
            highlightthickness=0
        )
        
        # 创建内部框架
        self.inner_frame = tk.Frame(self.canvas, bg=bg_color)
        
        # 绑定大小变化
        self.canvas.bind('<Configure>', self._on_canvas_configure)
        
        # 存储原来的pack/grid方法
        super().__init__(parent, **kwargs)
        self._place_canvas()
    
    def _place_canvas(self):
        """放置画布"""
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.create_window(0, 0, window=self.inner_frame, anchor='nw', 
                                 tags='inner_frame')
    
    def _on_canvas_configure(self, event):
        """画布大小改变时调整内部框架"""
        canvas_width = event.width
        canvas_height = event.height
        margin = self.radius // 2
        self.canvas.coords('inner_frame', margin, margin, 
                          canvas_width - margin, canvas_height - margin)
        self.inner_frame.configure(width=canvas_width - margin * 2,
                                  height=canvas_height - margin * 2)
        self._draw_border()
    
    def _draw_border(self):
        """绘制圆角边框"""
        self.canvas.delete('border')
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w <= 1 or h <= 1:
            return
        
        r = self.radius
        # 绘制圆角边框
        self.canvas.create_arc(r, r, r*2, r*2, start=90, extent=90,
                               outline=self.border_color, width=1, tags='border', style='arc')
        self.canvas.create_arc(w-r*2, r, w-r, r*2, start=0, extent=90,
                               outline=self.border_color, width=1, tags='border', style='arc')
        self.canvas.create_arc(w-r*2, h-r*2, w-r, h-r, start=270, extent=90,
                               outline=self.border_color, width=1, tags='border', style='arc')
        self.canvas.create_arc(r, h-r*2, r*2, h-r, start=180, extent=90,
                               outline=self.border_color, width=1, tags='border', style='arc')
        
        # 绘制直线边框
        self.canvas.create_line(r, 0, w-r, 0, fill=self.border_color, width=1, tags='border')
        self.canvas.create_line(w, r, w, h-r, fill=self.border_color, width=1, tags='border')
        self.canvas.create_line(w-r, h, r, h, fill=self.border_color, width=1, tags='border')
        self.canvas.create_line(0, h-r, 0, r, fill=self.border_color, width=1, tags='border')
    
    def pack(self, **kwargs):
        """重写pack方法"""
        return self.canvas.pack(**kwargs)
    
    def grid(self, **kwargs):
        """重写grid方法"""
        return self.canvas.grid(**kwargs)
    
    def place(self, **kwargs):
        """重写place方法"""
        return self.canvas.place(**kwargs)


class RenameApp(TkinterDnD.Tk):
    """主应用窗口"""
    
    def __init__(self):
        super().__init__()
        self.target_path = None  # 可以是文件夹或单个文件
        self.is_single_file = False  # 标记是否为单个文件
        self.processing = False
        self.language = 'zh'  # 默认中文
        
        self.setup_window()
        self.create_widgets()
        self.center_window()
    
    def setup_window(self):
        """设置窗口属性"""
        self.title("文件自动重命名工具")
        self.geometry("1000x750")
        self.configure(bg=COLORS['bg_main'])
        self.minsize(800, 600)
        
        # 设置窗口图标（可选）
        try:
            self.iconbitmap(default="")
        except:
            pass
    
    def center_window(self):
        """居中显示窗口"""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')
    
    def switch_language(self):
        """切换语言"""
        self.language = 'en' if self.language == 'zh' else 'zh'
        self.update_texts()
    
    def update_texts(self):
        """更新界面文本"""
        texts = TEXTS[self.language]
        
        # 更新标题
        self.title_label.config(text=texts['title'])
        self.subtitle_label.config(text=texts['subtitle'])
        
        # 更新拖放区域
        self.drop_area.config(text=texts['drop_area'])
        
        # 更新按钮
        self.process_button.config(text=texts['start_process'])
        
        # 更新日志标题
        self.log_title.config(text=texts['log_title'])
        
        # 更新语言切换按钮
        self.lang_button.config(text=texts['language_switch'])
        
        # 如果有选择的路径，更新显示
        if self.target_path:
            path = Path(self.target_path)
            if self.is_single_file:
                self.folder_label.config(text=texts['selected_file'].format(path.name))
            else:
                self.folder_label.config(text=texts['selected_folder'].format(self.target_path))
    
    def create_widgets(self):
        """创建界面组件"""
        # 外层容器 - 用于居中显示
        outer_container = tk.Frame(self, bg=COLORS['bg_main'])
        outer_container.pack(fill=tk.BOTH, expand=True)
        
        # 主容器 - 居中显示，最大宽度限制
        main_container = tk.Frame(outer_container, bg=COLORS['bg_main'])
        main_container.pack(expand=True, fill=tk.BOTH, padx=40, pady=30)
        
        # 内容容器 - 居中显示，限制最大宽度
        content_container = tk.Frame(main_container, bg=COLORS['bg_main'])
        content_container.pack(expand=True)
        
        # 顶部栏（标题和语言切换）
        top_bar = tk.Frame(content_container, bg=COLORS['bg_main'])
        top_bar.pack(fill=tk.X, pady=(0, 10))
        
        # 语言切换按钮（右上角）
        self.lang_button = tk.Button(
            top_bar,
            text=TEXTS[self.language]['language_switch'],
            font=get_font(12, 'normal', self.language),
            bg=COLORS['bg_main'],
            fg=COLORS['text_secondary'],
            activebackground=COLORS['bg_main'],
            activeforeground=COLORS['text_primary'],
            relief=tk.FLAT,
            borderwidth=0,
            cursor="hand2",
            command=self.switch_language
        )
        self.lang_button.pack(side=tk.RIGHT)
        
        # 标题
        self.title_label = tk.Label(
            top_bar,
            text=TEXTS[self.language]['title'],
            font=get_font(32, 'bold', self.language),
            bg=COLORS['bg_main'],
            fg=COLORS['text_primary']
        )
        self.title_label.pack(side=tk.LEFT)
        
        # 副标题
        self.subtitle_label = tk.Label(
            content_container,
            text=TEXTS[self.language]['subtitle'],
            font=get_font(14, 'normal', self.language),
            bg=COLORS['bg_main'],
            fg=COLORS['text_secondary']
        )
        self.subtitle_label.pack(pady=(0, 30))
        
        # 拖放区域卡片（使用圆角框架）- 居中显示，固定宽度
        drop_card_frame = tk.Frame(content_container, bg=COLORS['bg_main'])
        drop_card_frame.pack(pady=(0, 20))
        
        drop_card = RoundedFrame(
            drop_card_frame,
            radius=16,
            bg_color=COLORS['bg_card'],
            border_color=COLORS['border']
        )
        drop_card.pack()
        
        # 设置固定宽度和高度，使卡片居中
        drop_card.canvas.config(width=700, height=200)
        
        # 拖放区域
        self.drop_area = tk.Label(
            drop_card.inner_frame,
            text=TEXTS[self.language]['drop_area'],
            font=get_font(16, 'normal', self.language),
            bg=COLORS['bg_drop'],
            fg=COLORS['text_secondary'],
            cursor="hand2",
            relief=tk.FLAT,
            padx=50,
            pady=70
        )
        self.drop_area.pack(fill=tk.BOTH, expand=True, padx=25, pady=25)
        
        # 启用拖放
        self.drop_area.drop_target_register(DND_FILES)
        self.drop_area.dnd_bind('<<Drop>>', self.on_drop)
        
        # 点击选择文件夹
        self.drop_area.bind("<Button-1>", self.on_click_select)
        self.drop_area.bind("<Enter>", lambda e: self.drop_area.config(
            bg='#DEDEE3',
            fg=COLORS['text_primary']
        ))
        self.drop_area.bind("<Leave>", lambda e: self.drop_area.config(
            bg=COLORS['bg_drop'],
            fg=COLORS['text_secondary']
        ))
        
        # 当前选择的文件夹/文件显示
        self.folder_label = tk.Label(
            drop_card.inner_frame,
            text="",
            font=get_font(12, 'normal', self.language),
            bg=COLORS['bg_card'],
            fg=COLORS['text_secondary'],
            wraplength=900,
            justify=tk.LEFT
        )
        self.folder_label.pack(pady=(0, 15), padx=25, fill=tk.X)
        
        # 处理按钮（使用标准按钮）- 居中显示
        self.process_button = tk.Button(
            content_container,
            text=TEXTS[self.language]['start_process'],
            font=get_font(16, 'bold', self.language),
            bg=COLORS['bg_button'],
            fg=COLORS['text_button'],
            activebackground=COLORS['bg_button_active'],
            activeforeground=COLORS['text_button'],
            relief=tk.FLAT,
            borderwidth=0,
            padx=50,
            pady=15,
            cursor="hand2",
            state=tk.DISABLED,
            command=self.start_processing
        )
        self.process_button.pack(pady=(0, 20))
        
        # 处理日志区域（使用圆角框架）- 居中显示，固定宽度
        log_card_frame = tk.Frame(content_container, bg=COLORS['bg_main'])
        log_card_frame.pack(fill=tk.BOTH, expand=True)
        
        log_frame = RoundedFrame(
            log_card_frame,
            radius=16,
            bg_color=COLORS['bg_card'],
            border_color=COLORS['border']
        )
        log_frame.pack(expand=True)
        
        # 设置固定宽度和高度，使卡片居中
        log_frame.canvas.config(width=700, height=250)
        
        # 日志标题
        self.log_title = tk.Label(
            log_frame.inner_frame,
            text=TEXTS[self.language]['log_title'],
            font=get_font(14, 'bold', self.language),
            bg=COLORS['bg_card'],
            fg=COLORS['text_primary']
        )
        self.log_title.pack(anchor=tk.W, padx=20, pady=(20, 10))
        
        # 日志文本框
        self.log_text = scrolledtext.ScrolledText(
            log_frame.inner_frame,
            font=get_font(10, 'normal', self.language),
            bg='#FAFAFA',
            fg=COLORS['text_primary'],
            relief=tk.FLAT,
            borderwidth=0,
            wrap=tk.WORD,
            padx=20,
            pady=15,
            state=tk.DISABLED
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
        
        # 配置日志文本标签样式
        self.log_text.tag_config("success", foreground=COLORS['success'])
        self.log_text.tag_config("error", foreground="#FF3B30")
        self.log_text.tag_config("warning", foreground=COLORS['warning'])
        self.log_text.tag_config("skip", foreground=COLORS['text_secondary'])
        self.log_text.tag_config("info", foreground=COLORS['text_primary'])
    
    def on_drop(self, event):
        """处理拖放事件"""
        if self.processing:
            return
        
        paths = self.tk.splitlist(event.data)
        if paths:
            path = paths[0].strip('{}')
            self.select_path(path)
    
    def on_click_select(self, event):
        """点击选择文件夹或文件"""
        if self.processing:
            return
        
        from tkinter import filedialog
        texts = TEXTS[self.language]
        
        # 提供选择文件夹或文件的选项
        choice = messagebox.askyesnocancel(
            texts['select_type_title'],
            texts['select_type_message']
        )
        
        if choice is True:
            # 选择文件夹
            path = filedialog.askdirectory(title=texts['select_folder_title'])
        elif choice is False:
            # 选择文件
            path = filedialog.askopenfilename(title=texts['select_file_title'])
        else:
            # 取消
            return
        
        if path:
            self.select_path(path)
    
    def select_path(self, path_str):
        """选择路径（文件夹或单个文件）"""
        path = Path(path_str)
        texts = TEXTS[self.language]
        
        if not path.exists():
            messagebox.showerror("错误", texts['error_path_not_exist'].format(path_str))
            return
        
        # 判断是文件夹还是文件
        if path.is_dir():
            self.target_path = str(path)
            self.is_single_file = False
            self.folder_label.config(
                text=texts['selected_folder'].format(self.target_path),
                fg=COLORS['success']
            )
        elif path.is_file():
            self.target_path = str(path)
            self.is_single_file = True
            self.folder_label.config(
                text=texts['selected_file'].format(path.name),
                fg=COLORS['success']
            )
        else:
            messagebox.showerror("错误", texts['error_invalid_path'].format(path_str))
            return
        
        self.process_button.config(state=tk.NORMAL)
        
        # 清空日志
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def log_message(self, message, tag=None):
        """添加日志消息"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n", tag)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.update()
    
    def start_processing(self):
        """开始处理文件"""
        if not self.target_path or self.processing:
            return
        
        self.processing = True
        self.process_button.config(state=tk.DISABLED)
        self.drop_area.unbind("<Button-1>")
        
        # 在单独线程中处理，避免界面卡顿
        thread = threading.Thread(target=self.process_files)
        thread.daemon = True
        thread.start()
    
    def process_files(self):
        """处理文件（在后台线程中运行）"""
        start_time = time.time()
        texts = TEXTS[self.language]
        
        # 判断是单个文件还是文件夹
        if self.is_single_file:
            # 处理单个文件
            file_path = Path(self.target_path)
            files = [file_path]
            self.after(0, lambda: self.log_message(texts['processing_single'].format(file_path.name), "info"))
        else:
            # 处理文件夹中的所有文件
            folder = Path(self.target_path)
            files = [f for f in folder.iterdir() if f.is_file()]
            
            if not files:
                self.after(0, lambda: self.log_message(texts['no_files'], "warning"))
                self.after(0, self.processing_complete, 0, 0, 0)
                return
            
            self.after(0, lambda: self.log_message(texts['processing_folder'].format(len(files)), "info"))
        
        renamed_count = 0
        skipped_count = 0
        error_count = 0
        
        for idx, file_path in enumerate(files, 1):
            try:
                # 获取文件的最后修改时间
                mod_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                date_prefix = mod_time.strftime("%Y%m%d")
                original_name = file_path.name
                
                # 检查是否已有日期前缀
                if original_name.startswith(date_prefix + "_"):
                    self.after(0, lambda n=original_name: self.log_message(
                        texts['skip'].format(n), "skip"
                    ))
                    skipped_count += 1
                    continue
                
                # 构建新文件名
                new_name = f"{date_prefix}_{original_name}"
                new_path = file_path.parent / new_name
                
                # 检查新文件名是否已存在
                if new_path.exists():
                    self.after(0, lambda n=new_name, o=original_name: self.log_message(
                        texts['warning_exists'].format(n, o), "warning"
                    ))
                    skipped_count += 1
                    continue
                
                # 重命名文件
                file_path.rename(new_path)
                self.after(0, lambda n=new_name, o=original_name: self.log_message(
                    texts['success_rename'].format(o, n), "success"
                ))
                renamed_count += 1
                
            except Exception as e:
                self.after(0, lambda n=file_path.name, err=str(e): self.log_message(
                    texts['error'].format(n, err), "error"
                ))
                error_count += 1
        
        elapsed_time = time.time() - start_time
        
        # 完成处理
        self.after(0, self.processing_complete, renamed_count, skipped_count, error_count, elapsed_time)
    
    def processing_complete(self, renamed, skipped, errors, elapsed_time=0):
        """处理完成"""
        self.processing = False
        self.process_button.config(state=tk.NORMAL)
        self.drop_area.bind("<Button-1>", self.on_click_select)
        
        texts = TEXTS[self.language]
        self.after(0, lambda: self.log_message("\n" + "="*50, "info"))
        self.after(0, lambda: self.log_message(texts['processing_complete'], "success"))
        
        # 显示完成对话框
        self.show_completion_dialog(renamed, skipped, errors, elapsed_time)
    
    def show_completion_dialog(self, renamed, skipped, errors, elapsed_time):
        """显示完成对话框"""
        texts = TEXTS[self.language]
        
        # 创建对话框窗口
        dialog = tk.Toplevel(self)
        dialog.title(texts['dialog_title'])
        dialog.geometry("550x480")
        dialog.configure(bg=COLORS['bg_main'])
        dialog.resizable(False, False)
        
        # 居中显示（相对于主窗口）
        dialog.update_idletasks()
        main_x = self.winfo_x()
        main_y = self.winfo_y()
        main_width = self.winfo_width()
        main_height = self.winfo_height()
        dialog_width = 550
        dialog_height = 480
        x = main_x + (main_width // 2) - (dialog_width // 2)
        y = main_y + (main_height // 2) - (dialog_height // 2)
        dialog.geometry(f'{dialog_width}x{dialog_height}+{x}+{y}')
        
        # 禁用主窗口
        dialog.transient(self)
        dialog.grab_set()
        
        # 主容器 - 居中显示
        outer_frame = tk.Frame(dialog, bg=COLORS['bg_main'])
        outer_frame.pack(fill=tk.BOTH, expand=True)
        
        container = tk.Frame(outer_frame, bg=COLORS['bg_main'])
        container.pack(expand=True, padx=50, pady=50)
        
        # 成功图标
        success_label = tk.Label(
            container,
            text="✓",
            font=get_font(72, 'bold', self.language),
            bg=COLORS['bg_main'],
            fg=COLORS['success']
        )
        success_label.pack(pady=(0, 20))
        
        # 标题
        title_label = tk.Label(
            container,
            text=texts['dialog_title'],
            font=get_font(26, 'bold', self.language),
            bg=COLORS['bg_main'],
            fg=COLORS['text_primary']
        )
        title_label.pack(pady=(0, 30))
        
        # 统计信息卡片（使用圆角框架）- 居中显示
        stats_frame = RoundedFrame(
            container,
            radius=16,
            bg_color=COLORS['bg_card'],
            border_color=COLORS['border']
        )
        stats_frame.pack(expand=True, pady=(0, 25))
        
        # 设置固定宽度和高度，使卡片居中
        stats_frame.canvas.config(width=450, height=200)
        
        stats_inner = tk.Frame(stats_frame.inner_frame, bg=COLORS['bg_card'], padx=25, pady=25)
        stats_inner.pack(fill=tk.BOTH, expand=True)
        
        # 统计信息
        stats = [
            (texts['success_rename_label'], renamed, COLORS['success']),
            (texts['skip_label'], skipped, COLORS['text_secondary']),
            (texts['error_label'], errors, COLORS['warning'] if errors > 0 else COLORS['text_secondary']),
        ]
        
        for label, value, color in stats:
            stat_frame = tk.Frame(stats_inner, bg=COLORS['bg_card'])
            stat_frame.pack(fill=tk.X, pady=10)
            
            tk.Label(
                stat_frame,
                text=label,
                font=get_font(14, 'normal', self.language),
                bg=COLORS['bg_card'],
                fg=COLORS['text_secondary']
            ).pack(side=tk.LEFT)
            
            tk.Label(
                stat_frame,
                text=str(value),
                font=get_font(14, 'bold', self.language),
                bg=COLORS['bg_card'],
                fg=color
            ).pack(side=tk.RIGHT)
        
        # 用时
        time_frame = tk.Frame(stats_inner, bg=COLORS['bg_card'])
        time_frame.pack(fill=tk.X, pady=(15, 0))
        
        tk.Label(
            time_frame,
            text=texts['time_label'],
            font=get_font(14, 'normal', self.language),
            bg=COLORS['bg_card'],
            fg=COLORS['text_secondary']
        ).pack(side=tk.LEFT)
        
        time_str = f"{elapsed_time:.2f}{texts['time_unit']}"
        tk.Label(
            time_frame,
            text=time_str,
            font=get_font(14, 'bold', self.language),
            bg=COLORS['bg_card'],
            fg=COLORS['text_primary']
        ).pack(side=tk.RIGHT)
        
        # 关闭按钮（使用标准按钮）
        close_button = tk.Button(
            container,
            text=texts['close'],
            font=get_font(14, 'bold', self.language),
            bg=COLORS['bg_button'],
            fg=COLORS['text_button'],
            activebackground=COLORS['bg_button_active'],
            activeforeground=COLORS['text_button'],
            relief=tk.FLAT,
            borderwidth=0,
            padx=50,
            pady=12,
            cursor="hand2",
            command=dialog.destroy
        )
        close_button.pack()


def main():
    """主函数"""
    app = RenameApp()
    app.mainloop()


if __name__ == "__main__":
    main()
