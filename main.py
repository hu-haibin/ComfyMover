import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import sys
import shutil
import threading
import time
from bs4 import BeautifulSoup

# --- 全局变量 ---
CONFIG_FILE = "comfyui_mover_config.txt" # 配置文件名
folder_paths = None # 用于存储导入的 ComfyUI folder_paths 模块

# --- 映射：将 HTML 中的节点类型转换为 folder_paths 使用的 key ---
# 你可能需要根据你的 ComfyUI 版本和使用的自定义节点来调整这个映射
nodetype_to_folderkey = {
    "CheckpointLoaderSimple": "checkpoints",
    "CheckpointLoader": "checkpoints",
    "LoraLoaderModelOnly": "loras",
    "LoraLoader": "loras",
    "VAELoader": "vae",
    "ControlNetLoader": "controlnet",
    "UpscaleModelLoader": "upscale_models",
    "CLIPLoader": "clip",
    "DualCLIPLoader": "clip",
    "CLIPLoaderGGUF": "clip", # GGUF CLIP 也放入 clip
    "UnetLoaderGGUF": "unet", # GGUF UNet 放入 unet
    "CLIPTextEncode": "embeddings", # 假设 Textual Inversion/Embeddings 使用此 key
    # 添加更多你可能遇到的节点类型到文件夹关键字的映射...
}

# --- 辅助函数：路径配置 ---
def get_script_dir():
    """获取脚本所在的目录"""
    if getattr(sys, 'frozen', False):
        # 如果是打包后的 .exe 文件
        return os.path.dirname(sys.executable)
    else:
        # 如果是直接运行 .py 文件
        return os.path.dirname(os.path.abspath(__file__))

def load_paths_from_config(config_path):
    """从配置文件加载路径"""
    paths = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
                if len(lines) >= 3:
                    paths['html'] = lines[0]
                    paths['download'] = lines[1]
                    paths['comfyui'] = lines[2]
                    # 简单验证路径是否存在
                    if os.path.isfile(paths['html']) and \
                       os.path.isdir(paths['download']) and \
                       os.path.isdir(paths['comfyui']):
                        return paths
                    else:
                        print("配置文件中的部分路径已失效。")
                        return None
                else:
                    print("配置文件格式不正确。")
                    return None
        except Exception as e:
            print(f"读取配置文件 '{config_path}' 时出错: {e}")
            return None
    return None

def save_paths_to_config(config_path, paths):
    """保存路径到配置文件"""
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(paths['html'] + '\n')
            f.write(paths['download'] + '\n')
            f.write(paths['comfyui'] + '\n')
        print(f"路径已保存到配置文件: {config_path}")
    except Exception as e:
        print(f"保存路径到配置文件 '{config_path}' 时出错: {e}")

# --- 辅助函数：HTML 解析 ---
def parse_model_info_from_html(html_file_path, status_callback):
    """从 HTML 文件解析文件名到节点类型的映射"""
    mapping = {}
    status_callback(f"开始解析 HTML 文件: {os.path.basename(html_file_path)}...")
    try:
        with open(html_file_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'lxml')

        table = soup.find('table', id='modelTable')
        if not table:
            status_callback(f"错误：在 HTML 文件中未找到 ID 为 'modelTable' 的表格。")
            messagebox.showerror("HTML 解析错误", f"在 HTML 文件中未找到 ID 为 'modelTable' 的表格。")
            return None

        rows = table.find_all('tr')
        if len(rows) < 2:
            status_callback("警告：HTML 表格中未找到足够的数据行。")
            return mapping # 返回空字典也算成功，只是没有数据

        headers_th = rows[0].find_all('th')
        headers_text = [th.get_text(strip=True) for th in headers_th]
        filename_idx, nodetype_idx = -1, -1

        for i, header in enumerate(headers_text):
            if header.startswith('文件名'): filename_idx = i
            elif header.startswith('节点类型'): nodetype_idx = i

        if filename_idx == -1 or nodetype_idx == -1:
            status_callback(f"错误：未能从表头 {headers_text} 中定位 '文件名' 或 '节点类型' 列。")
            messagebox.showerror("HTML 解析错误", f"未能从表头 {headers_text} 中定位 '文件名' 或 '节点类型' 列。")
            return None

        for i, row in enumerate(rows[1:], 1): # 从 1 开始计数数据行
            cols = row.find_all('td')
            if len(cols) > max(filename_idx, nodetype_idx):
                filename = cols[filename_idx].get_text(strip=True)
                node_type = cols[nodetype_idx].get_text(strip=True)
                if filename and node_type:
                    mapping[filename] = node_type
            # else: # 可选：记录缺少列的行
            #     status_callback(f"警告：HTML 第 {i+1} 行数据列数不足。")


        status_callback(f"成功从 HTML 文件解析了 {len(mapping)} 条模型信息。")
        return mapping

    except FileNotFoundError:
        status_callback(f"错误：HTML 文件 '{html_file_path}' 未找到。")
        messagebox.showerror("文件未找到", f"HTML 文件 '{html_file_path}' 未找到。")
        return None
    except Exception as e:
        status_callback(f"解析 HTML 文件时发生严重错误: {e}")
        messagebox.showerror("HTML 解析错误", f"解析 HTML 文件时发生严重错误:\n{e}")
        return None

# --- 辅助函数：ComfyUI 交互 ---
def initialize_folder_paths(comfyui_base_path, status_callback):
    """动态加载 ComfyUI 的 folder_paths 模块"""
    global folder_paths
    if folder_paths: # 如果已经加载过，直接返回 True
        return True

    status_callback(f"尝试从 {comfyui_base_path} 加载 ComfyUI 模块...")
    if not os.path.isdir(comfyui_base_path):
         status_callback(f"错误：ComfyUI 路径 '{comfyui_base_path}' 不是有效目录。")
         messagebox.showerror("路径错误", f"ComfyUI 路径 '{comfyui_base_path}' 不是有效目录。")
         return False

    original_sys_path = list(sys.path) # 备份原始 sys.path
    try:
        # 将 ComfyUI 根目录添加到 Python 搜索路径的开头
        sys.path.insert(0, comfyui_base_path)

        # 尝试导入 folder_paths
        import importlib
        try:
            # 尝试重新加载，以防之前有缓存
            if 'folder_paths' in sys.modules:
                folder_paths = importlib.reload(sys.modules['folder_paths'])
            else:
                folder_paths = importlib.import_module('folder_paths')
        except ImportError:
             status_callback(f"错误：无法从 '{comfyui_base_path}' 导入 ComfyUI 的 folder_paths 模块。")
             messagebox.showerror("导入错误", f"无法从 '{comfyui_base_path}' 导入 ComfyUI 的 folder_paths 模块。\n请确认路径正确且包含 folder_paths.py。")
             return False

        # 尝试执行初始化（如果存在）
        if hasattr(folder_paths, 'init'):
            try:
                folder_paths.init()
                status_callback("执行了 folder_paths.init()")
            except Exception as init_e:
                 status_callback(f"执行 folder_paths.init() 时出错: {init_e}")
                 # 不一定是致命错误，继续尝试
        else:
            status_callback("未找到 folder_paths.init()。")

        status_callback("成功导入 ComfyUI 的 folder_paths 模块。")
        return True

    except Exception as e:
        status_callback(f"加载 ComfyUI folder_paths 时发生错误: {e}")
        messagebox.showerror("加载错误", f"加载 ComfyUI folder_paths 时发生错误:\n{e}")
        return False
    finally:
        # 恢复原始 sys.path，避免潜在冲突
        sys.path = original_sys_path


def get_destination_folder(model_type_key, comfyui_base_path, status_callback):
    """获取 ComfyUI 模型类型的首选目标文件夹路径"""
    global folder_paths
    if not folder_paths:
        status_callback("错误：folder_paths 模块未成功加载。")
        return None

    try:
        # get_folder_paths 返回一个列表，包含默认路径和自定义路径
        paths = folder_paths.get_folder_paths(model_type_key)
        if paths:
            target_folder = paths[0] # 通常使用列表中的第一个路径作为主要目标
            # 确保目标文件夹存在，如果不存在则创建
            os.makedirs(target_folder, exist_ok=True)
            return target_folder
        else:
            status_callback(f"警告：在 ComfyUI 配置中未找到 '{model_type_key}' 类型的路径。尝试默认。")
            # 尝试回退到基于约定的默认路径
            fallback_path = os.path.join(comfyui_base_path, "models", model_type_key)
            models_dir = os.path.join(comfyui_base_path, "models")
            if os.path.exists(models_dir): # 检查 models 目录是否存在
                 status_callback(f"使用默认回退路径: {fallback_path}")
                 os.makedirs(fallback_path, exist_ok=True)
                 return fallback_path
            else:
                 status_callback(f"错误：无法确定 '{model_type_key}' 的目标文件夹，且 models 目录不存在。")
                 return None
    except KeyError:
         status_callback(f"错误：ComfyUI 的 folder_paths 不支持关键字 '{model_type_key}'。")
         return None
    except Exception as e:
        status_callback(f"错误：获取 '{model_type_key}' 的 ComfyUI 路径时出错: {e}")
        return None


# --- GUI 应用类 (添加覆盖确认) ---
class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("ComfyUI 模型移动工具")
        self.geometry("700x550") # 调整窗口大小
        ctk.set_appearance_mode("System") # 或 "Light", "Dark"
        ctk.set_default_color_theme("blue") # 或 "green", "dark-blue"

        self.config_path = os.path.join(get_script_dir(), CONFIG_FILE)
        self.processing_thread = None # 用于跟踪处理线程

        # --- 创建主框架 ---
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(pady=10, padx=10, fill="both", expand=True)

        # --- 路径设置部分 ---
        path_frame = ctk.CTkFrame(self.main_frame)
        path_frame.pack(pady=10, padx=10, fill="x")
        path_frame.grid_columnconfigure(1, weight=1) # 让输入框可以扩展

        # HTML 文件路径
        ctk.CTkLabel(path_frame, text="HTML 元数据文件:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.html_path_entry = ctk.CTkEntry(path_frame, width=350)
        self.html_path_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkButton(path_frame, text="浏览...", width=60, command=self.browse_html_file).grid(row=0, column=2, padx=5, pady=5)

        # 下载文件夹路径
        ctk.CTkLabel(path_frame, text="下载文件夹:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.download_path_entry = ctk.CTkEntry(path_frame, width=350)
        self.download_path_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkButton(path_frame, text="浏览...", width=60, command=self.browse_download_folder).grid(row=1, column=2, padx=5, pady=5)

        # ComfyUI 根目录路径
        ctk.CTkLabel(path_frame, text="ComfyUI 根目录:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.comfyui_path_entry = ctk.CTkEntry(path_frame, width=350)
        self.comfyui_path_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkButton(path_frame, text="浏览...", width=60, command=self.browse_comfyui_folder).grid(row=2, column=2, padx=5, pady=5)

        # --- 操作按钮 ---
        self.process_button = ctk.CTkButton(self.main_frame, text="开始移动文件 (覆盖模式)", command=self.start_processing) # 更新按钮文本
        self.process_button.pack(pady=10)

        # --- 状态日志 ---
        status_frame = ctk.CTkFrame(self.main_frame)
        status_frame.pack(pady=10, padx=10, fill="both", expand=True)
        ctk.CTkLabel(status_frame, text="处理日志:").pack(anchor="w", padx=5)
        self.status_textbox = ctk.CTkTextbox(status_frame, state="disabled", wrap="word") # wrap="word" 自动换行
        self.status_textbox.pack(fill="both", expand=True, padx=5, pady=5)

        # --- 加载保存的路径 ---
        self.load_initial_paths()

    def update_status(self, message):
        """安全地更新状态文本框 (可在任何线程调用)"""
        # 使用 self.after 确保 GUI 更新在主线程执行
        self.after(0, self._append_status_message, message)

    def _append_status_message(self, message):
        """实际在主线程中追加消息"""
        self.status_textbox.configure(state="normal") # 允许编辑
        self.status_textbox.insert("end", f"{message}\n")
        self.status_textbox.configure(state="disabled") # 禁止编辑
        self.status_textbox.see("end") # 滚动到底部

    def load_initial_paths(self):
        """加载初始路径"""
        self.update_status("正在加载配置...")
        loaded_paths = load_paths_from_config(self.config_path)
        if loaded_paths:
            self.html_path_entry.insert(0, loaded_paths['html'])
            self.download_path_entry.insert(0, loaded_paths['download'])
            self.comfyui_path_entry.insert(0, loaded_paths['comfyui'])
            self.update_status("已加载保存的路径。")
        else:
            self.update_status("未找到有效配置或配置已失效，请手动设置路径。")

    def browse_html_file(self):
        """浏览 HTML 文件"""
        filepath = filedialog.askopenfilename(
            title="选择 HTML 元数据文件",
            filetypes=(("HTML files", "*.html;*.htm"), ("All files", "*.*"))
        )
        if filepath:
            self.html_path_entry.delete(0, tk.END)
            self.html_path_entry.insert(0, filepath)

    def browse_download_folder(self):
        """浏览下载文件夹"""
        dirpath = filedialog.askdirectory(title="选择下载文件夹")
        if dirpath:
            self.download_path_entry.delete(0, tk.END)
            self.download_path_entry.insert(0, dirpath)

    def browse_comfyui_folder(self):
        """浏览 ComfyUI 根目录"""
        dirpath = filedialog.askdirectory(title="选择 ComfyUI 根目录")
        if dirpath:
            self.comfyui_path_entry.delete(0, tk.END)
            self.comfyui_path_entry.insert(0, dirpath)

    def start_processing(self):
        """开始处理文件移动（按钮回调）"""
        # 检查是否已经在处理
        if self.processing_thread and self.processing_thread.is_alive():
            messagebox.showwarning("处理中", "当前正在处理文件，请稍候。")
            return

        # 获取并验证路径
        html_path = self.html_path_entry.get().strip()
        download_path = self.download_path_entry.get().strip()
        comfyui_path = self.comfyui_path_entry.get().strip()

        if not html_path or not os.path.isfile(html_path):
            messagebox.showerror("路径错误", "请提供有效的 HTML 元数据文件路径。")
            return
        if not download_path or not os.path.isdir(download_path):
            messagebox.showerror("路径错误", "请提供有效的下载文件夹路径。")
            return
        if not comfyui_path or not os.path.isdir(comfyui_path):
            messagebox.showerror("路径错误", "请提供有效的 ComfyUI 根目录路径。")
            return

        # --- 添加确认步骤 ---
        confirm = messagebox.askyesno(
            title="确认操作",
            message="即将开始移动文件。\n\n"
                    "此操作将根据 HTML 文件信息将下载文件夹中的模型文件移动到对应的 ComfyUI 文件夹。\n\n"
                    "注意：如果目标文件夹已存在同名文件，将会被覆盖！\n\n"
                    "是否继续？",
            icon=messagebox.WARNING # 添加警告图标
        )

        if not confirm:
            self.update_status("用户取消了操作。")
            return # 用户点击 "否"，则不继续
        # --- 确认步骤结束 ---


        # 保存当前有效路径 (用户确认后才保存)
        current_paths = {'html': html_path, 'download': download_path, 'comfyui': comfyui_path}
        save_paths_to_config(self.config_path, current_paths)

        # 清空状态栏并禁用按钮
        self.status_textbox.configure(state="normal")
        self.status_textbox.delete("1.0", tk.END)
        self.status_textbox.configure(state="disabled")
        self.process_button.configure(state="disabled", text="正在处理 (覆盖)...") # 更新按钮文本
        self.update_status("用户已确认，开始处理 (覆盖模式)...") # 更新状态

        # 在新线程中运行处理逻辑
        self.processing_thread = threading.Thread(
            target=self.run_processing_thread,
            args=(html_path, download_path, comfyui_path),
            daemon=True # 设置为守护线程，主程序退出时线程也退出
        )
        self.processing_thread.start()

    def run_processing_thread(self, html_path, download_path, comfyui_path):
        """实际的文件处理逻辑（在单独线程中运行）"""
        # ... (run_processing_thread 函数内部的代码保持不变) ...
        global folder_paths # 确保能访问全局变量
        folder_paths = None # 重置 folder_paths 状态，强制重新加载

        moved_count = 0
        skipped_count = 0 # 这个计数器现在主要记录非文件、未在HTML中找到或路径错误的文件
        error_count = 0
        overwritten_count = 0 # 新增计数器：记录覆盖了多少文件

        try:
            # 1. 解析 HTML
            filename_nodetype_map = parse_model_info_from_html(html_path, self.update_status)
            if filename_nodetype_map is None: # 解析失败
                raise Exception("HTML 解析失败，请检查日志。") # 抛出异常以便 finally 处理按钮状态

            # 2. 加载 ComfyUI 模块
            if not initialize_folder_paths(comfyui_path, self.update_status):
                 raise Exception("ComfyUI folder_paths 加载失败，请检查日志。")

            # 3. 遍历下载文件夹
            self.update_status(f"开始扫描下载文件夹: {download_path}")
            all_items = os.listdir(download_path)
            total_files_in_dir = sum(1 for item in all_items if os.path.isfile(os.path.join(download_path, item)))
            self.update_status(f"找到 {total_files_in_dir} 个文件进行检查...")
            processed_files = 0

            for filename in all_items:
                source_path = os.path.join(download_path, filename)

                if os.path.isfile(source_path):
                    processed_files += 1
                    self.update_status(f"[{processed_files}/{total_files_in_dir}] 检查: {filename}")
                    target_folder, model_type_key, display_type = None, None, "未知 (HTML中未找到)"

                    if filename in filename_nodetype_map:
                        node_type = filename_nodetype_map[filename]
                        display_type = node_type

                        if node_type in nodetype_to_folderkey:
                            model_type_key = nodetype_to_folderkey[node_type]
                            target_folder = get_destination_folder(model_type_key, comfyui_path, self.update_status)
                            if target_folder is None:
                                self.update_status(f"  -> 跳过 {filename}，无法获取类型 '{model_type_key}' 的有效目标路径。")
                                skipped_count += 1
                                continue # 处理下一个文件
                        else:
                            self.update_status(f"  -> 跳过 {filename}，节点类型 '{node_type}' 未在映射中定义。")
                            skipped_count += 1
                            continue
                    else:
                        # 文件不在 HTML 映射中
                        self.update_status(f"  -> 跳过 {filename} (未在 HTML 元数据中找到)。")
                        skipped_count += 1
                        continue

                    # --- 执行移动 (覆盖模式) ---
                    if target_folder and model_type_key:
                        destination_path = os.path.join(target_folder, filename)
                        self.update_status(f"  识别为 {display_type} ({model_type_key})")
                        try:
                            # 检查目标是否存在，用于统计覆盖数量
                            target_exists = os.path.exists(destination_path)
                            if target_exists:
                                self.update_status(f"  -> 正在移动 (将覆盖已存在文件) 到: ...{os.path.basename(target_folder)}{os.sep}{filename}")
                            else:
                                self.update_status(f"  -> 正在移动到: ...{os.path.basename(target_folder)}{os.sep}{filename}")

                            # 直接移动，shutil.move 会覆盖
                            shutil.move(source_path, destination_path)

                            if target_exists:
                                self.update_status(f"  -> 覆盖成功!")
                                overwritten_count += 1
                            else:
                                self.update_status(f"  -> 移动成功!")
                            moved_count += 1 # 无论覆盖还是新建都算移动成功

                        except Exception as move_e:
                            self.update_status(f"  -> 移动文件 {filename} 时发生错误: {move_e}")
                            error_count += 1
                    else:
                        # 理论上不会到这里
                        skipped_count += 1

                # else: # 跳过子文件夹
                #     self.update_status(f"跳过子文件夹: {filename}")
                #     skipped_count += 1

            # 处理完成
            self.update_status("-" * 30)
            self.update_status("处理完成！")
            self.update_status(f"成功移动 (含覆盖): {moved_count} 文件")
            self.update_status(f"其中覆盖了: {overwritten_count} 个已存在文件")
            self.update_status(f"跳过/未识别/路径错误: {skipped_count} 文件")
            self.update_status(f"移动出错: {error_count} 文件")

        except Exception as e:
            self.update_status(f"处理过程中发生严重错误: {e}")
            messagebox.showerror("处理错误", f"处理过程中发生错误:\n{e}")
        finally:
            # 确保按钮在处理结束后（无论成功或失败）恢复可用
            # 使用 self.after 确保在主线程中执行
            self.after(0, self._reset_button_state)


    def _reset_button_state(self):
        """在主线程中恢复按钮状态"""
        self.process_button.configure(state="normal", text="开始移动文件 (覆盖模式)") # 恢复按钮文本



# --- 程序入口 ---
if __name__ == "__main__":
    # 检查是否需要安装依赖
    try:
        import customtkinter
        import bs4
        import lxml
    except ImportError:
        print("错误：缺少必要的库。请先安装：pip install customtkinter beautifulsoup4 lxml")
        input("按 Enter 退出...")
        sys.exit(1)

    app = App()
    app.mainloop()
