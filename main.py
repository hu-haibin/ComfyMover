# Import necessary libraries
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import os
import sys
import shutil
import threading
import time
import json
from bs4 import BeautifulSoup # Kept for HTML mode, but lxml is optional if only using HTML mode lightly
import re # Import regex for parsing AI response

# --- 在文件顶部添加新的映射字典 ---
known_missing_key_to_subdir = {
    "instantid": "instantid", # Map the KEY "instantid" to the SUBDIR "instantid"
    # Add more later as needed
    # "ipadapter": "ipadapter",
    # "animatediff_models": "animatediff_models",
    # ...
}

# --- Global Variables ---
CONFIG_FILE = "comfyui_mover_config.txt" # Config filename
folder_paths = None # To store imported ComfyUI folder_paths module
reference_data = None # 新增: 用于存储加载的 JSON 数据
reference_data_path = "extracted_models.json" # 新增:

# --- 新的映射: Output Type 到 folder_paths key ---
# 优先使用这个映射
output_type_to_folder_map = {
    "MODEL": "checkpoints", # 涵盖 CheckpointLoader, UNETLoader 等输出 "MODEL" 的情况
    "VAE": "vae",
    "CLIP": "clip",
    "CONTROL_NET": "controlnet",
    "LORA": "loras",
    "UPSCALE_MODEL": "upscale_models",
    "STYLE_MODEL": "style_models", # T2I Adapters 等
    "GLIGEN": "gligen",
    "CLIP_VISION": "clip_vision",
    "HYPERNETWORK": "hypernetworks",
    "UNET": "unet", # 如果有专门的 UNET 输出类型
    "PHOTOMAKER": "photomaker", # 示例：自定义节点类型
    "SAM_MODEL": "sams",       # 示例：SAM 模型
    "MOTION_MODULE": "animatediff_models", # AnimateDiff 模型
    # !!! 请根据您查看 extracted_models.json 后的实际情况补充或调整这个映射 !!!
    # 例如： "cogvideo_pipe" 应该映射到哪里？ "mochi_model" 呢？这需要您决定或查找对应节点的存放习惯
    "AUTOENCODER": "vae", # DiffusersVaeLoader 输出的是这个
    "SAM2_MODEL": "sams",
    "GROUNDING_DINO_MODEL": "grounding-dino", # ComfyUI Manager 常用的路径名
    # 注意大小写，映射时可以统一转为大写或小写来匹配
}

# --- Mapping: HTML Node Type to folder_paths key ---
# This remains relevant for the HTML mode
nodetype_to_folderkey = {
    "CheckpointLoaderSimple": "checkpoints",
    "CheckpointLoader": "checkpoints", # 可能需要处理 YAML 问题
    "LoraLoaderModelOnly": "loras",
    "LoraLoader": "loras",
    "VAELoader": "vae",
    "ControlNetLoader": "controlnet",
    "UpscaleModelLoader": "upscale_models",
    "CLIPLoader": "clip",
    "DualCLIPLoader": "clip",
    "CLIPLoaderGGUF": "clip",
    "UnetLoaderGGUF": "unet",
    "InstantIDModelLoader": "instantid",
    
}

# --- Helper Function: 添加一个过滤函数 ---
def is_likely_model_file(filename):
    """
    检查文件名是否可能是模型文件 (过滤掉配置、特殊标识符等).
    """
    if not filename or not isinstance(filename, str):
        return False

    name_lower = filename.lower()
    # 常见模型扩展名
    model_extensions = ('.safetensors', '.ckpt', '.pt', '.bin', '.pth', '.onnx', '.gguf')
    # 要忽略的配置文件扩展名
    config_extensions = ('.yaml', '.json', '.toml')
    # 要忽略的特殊字符串或非文件标识符 (转为小写)
    ignore_names = ('none', 'baked vae', 'default', 'taesd', 'taesdxl', 'taef1')

    # 忽略特殊字符串
    if name_lower in ignore_names:
        return False

    # 忽略配置文件 (除非您想移动它们)
    if name_lower.endswith(config_extensions):
        return False

    # 判断是否以模型扩展名结尾
    if name_lower.endswith(model_extensions):
        return True

    # 可选：增加更复杂的检查，比如是否包含路径分隔符，暗示它是一个文件路径
    # if '/' in filename or '\\' in filename:
    #     # 但要小心，这可能误判一些包含斜杠的特殊标识符
    #     # 也许结合扩展名检查更安全
    #     pass

    # 默认认为不是可移动的模型文件
    return False

# --- Helper Functions: Path Configuration ---
# (get_script_dir, load_paths_from_config, save_paths_to_config remain largely the same)
def get_script_dir():
    """Get the directory where the script is located"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

def load_paths_from_config(config_path):
    """Load paths from the configuration file"""
    paths = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
                if len(lines) >= 2:
                    paths['download'] = lines[0]
                    paths['comfyui'] = lines[1]
                    if len(lines) >= 3:
                       paths['html'] = lines[2]
                    # Basic validation added here
                    # Check if paths are directories, print warning if not
                    # Use os.path.exists to allow files if needed, but we need dirs here
                    if paths.get('download') and not os.path.isdir(paths.get('download', '')):
                        # Print only once maybe? Or let GUI handle user feedback
                        print(f"Config Warning: Download path '{paths.get('download', '')}' not valid (should be a folder).")
                    if paths.get('comfyui') and not os.path.isdir(paths.get('comfyui', '')):
                         print(f"Config Warning: ComfyUI path '{paths.get('comfyui', '')}' not valid (should be a folder).")

                    return paths
                else:
                    print("Configuration file format is incorrect.")
                    return None
        except Exception as e:
            print(f"Error reading config file '{config_path}': {e}")
            return None
    return None

def save_paths_to_config(config_path, paths):
    """Save paths to the configuration file"""
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(paths.get('download', '') + '\n')
            f.write(paths.get('comfyui', '') + '\n')
            # Only write HTML path if it's explicitly in the dictionary to be saved
            if 'html' in paths and paths['html'] is not None: # Check for None too
                 f.write(paths['html'] + '\n')
        print(f"Paths saved to config file: {config_path}")
    except Exception as e:
        print(f"Error saving paths to config file '{config_path}': {e}")


# --- Helper Functions: HTML Parsing (Mode 1) ---
# (parse_model_info_from_html remains the same)
def parse_model_info_from_html(html_file_path, status_callback):
    """Parse filename to node type mapping from HTML file"""
    mapping = {}
    status_callback(f"Starting to parse HTML file: {os.path.basename(html_file_path)}...")
    try:
        with open(html_file_path, 'r', encoding='utf-8') as f:
            try:
                import lxml
                soup = BeautifulSoup(f, 'lxml')
            except ImportError:
                status_callback("lxml not found, using html.parser for HTML parsing (might be slower).")
                soup = BeautifulSoup(f, 'html.parser')

        table = soup.find('table', id='modelTable')
        if not table:
            status_callback(f"Error: Could not find table with id 'modelTable' in HTML file.")
            messagebox.showerror("HTML Parse Error", f"Could not find table with id 'modelTable' in HTML file.")
            return None

        rows = table.find_all('tr')
        if len(rows) < 2:
            status_callback("Warning: Not enough data rows found in HTML table.")
            return mapping

        headers_th = rows[0].find_all('th')
        headers_text = [th.get_text(strip=True) for th in headers_th]
        filename_idx, nodetype_idx = -1, -1

        for i, header in enumerate(headers_text):
            if header.startswith('文件名'): filename_idx = i
            elif header.startswith('节点类型'): nodetype_idx = i

        if filename_idx == -1 or nodetype_idx == -1:
            status_callback(f"Error: Could not locate '文件名' or '节点类型' columns in headers {headers_text}.")
            messagebox.showerror("HTML Parse Error", f"Could not locate '文件名' or '节点类型' columns in headers {headers_text}.")
            return None

        for i, row in enumerate(rows[1:], 1):
            cols = row.find_all('td')
            if len(cols) > max(filename_idx, nodetype_idx):
                filename = cols[filename_idx].get_text(strip=True)
                node_type = cols[nodetype_idx].get_text(strip=True)
                if filename and node_type:
                    mapping[filename] = node_type

        status_callback(f"Successfully parsed {len(mapping)} model entries from HTML file.")
        return mapping

    except FileNotFoundError:
        status_callback(f"Error: HTML file '{html_file_path}' not found.")
        messagebox.showerror("File Not Found", f"HTML file '{html_file_path}' not found.")
        return None
    except Exception as e:
        status_callback(f"Critical error parsing HTML file: {e}")
        messagebox.showerror("HTML Parse Error", f"Critical error parsing HTML file:\n{e}")
        return None

# --- Helper Functions: AI Response Parsing (Mode 2) ---
# (parse_ai_response remains the same)
def parse_ai_response(ai_text, status_callback):
    """
    Parses the text pasted from the AI assistant.
    EXPECTS format like: filename1.safetensors -> loras
    Returns a dictionary: {filename: destination_key}
    """
    mapping = {}
    status_callback("Parsing AI response text...")
    lines = ai_text.strip().split('\n')
    pattern = re.compile(r"^\s*(.+?)\s*->\s*(\w+)\s*$")
    parsed_count = 0
    error_lines = 0
    for i, line in enumerate(lines):
        line = line.strip()
        if not line: continue
        match = pattern.match(line)
        if match:
            filename = match.group(1).strip()
            dest_key = match.group(2).strip().lower()
            mapping[filename] = dest_key
            parsed_count += 1
        else:
            status_callback(f"  Warning: Could not parse line {i+1}: '{line}'. Expected format: 'filename -> key'. Skipping.")
            error_lines += 1

    if parsed_count > 0:
         status_callback(f"Successfully parsed {parsed_count} entries from AI response.")
    if error_lines > 0:
         status_callback(f"Could not parse {error_lines} lines from AI response.")
    if not mapping and len(lines) > 0 and all(not l for l in lines):
        status_callback("AI response text was empty or contained only whitespace.")
    elif not mapping and parsed_count == 0 and error_lines > 0:
        status_callback(f"Warning: AI response text provided, but no entries were parsed due to format errors.")
        messagebox.showwarning("Parsing Warning", f"Could not parse any valid entries from the AI response text ({error_lines} lines failed). Please check the format (e.g., 'filename -> key' per line).")
        return None
    elif not mapping:
         status_callback("Warning: No valid mapping entries found in AI response.")

    return mapping

# --- Helper Functions: ComfyUI Interaction ---
# (initialize_folder_paths, get_destination_folder remain the same)
def initialize_folder_paths(comfyui_base_path, status_callback):
    """Dynamically load ComfyUI's folder_paths module"""
    global folder_paths
    status_callback(f"Attempting to load ComfyUI modules from {comfyui_base_path}...")
    if not os.path.isdir(comfyui_base_path):
         status_callback(f"Error: ComfyUI path '{comfyui_base_path}' is not a valid directory.")
         messagebox.showerror("Path Error", f"ComfyUI path '{comfyui_base_path}' is not a valid directory.")
         return False

    original_sys_path = list(sys.path)
    folder_paths = None
    try:
        if comfyui_base_path not in sys.path:
            sys.path.insert(0, comfyui_base_path)

        import importlib
        try:
            if 'folder_paths' in sys.modules:
                folder_paths = importlib.reload(sys.modules['folder_paths'])
            else:
                folder_paths = importlib.import_module('folder_paths')
        except ImportError as e:
             status_callback(f"Error: Failed to import ComfyUI's folder_paths module from '{comfyui_base_path}'. Error: {e}")
             messagebox.showerror("Import Error", f"Failed to import ComfyUI's folder_paths module from '{comfyui_base_path}'.\nCheck path and ensure folder_paths.py exists.\nError: {e}")
             return False
        except Exception as e:
             status_callback(f"Error during folder_paths import: {e}")
             messagebox.showerror("Import Error", f"An unexpected error occurred during folder_paths import:\n{e}")
             return False

        if hasattr(folder_paths, 'init'):
            try:
                folder_paths.init()
            except Exception as init_e:
                 status_callback(f"Warning during folder_paths.init(): {init_e}")

        try:
            test_paths = folder_paths.get_folder_paths("checkpoints")
            if not test_paths:
                 status_callback("Warning: folder_paths loaded but get_folder_paths('checkpoints') returned empty.")
        except Exception as check_e:
             status_callback(f"Warning: Error testing get_folder_paths after load: {check_e}")

        status_callback("Successfully initialized ComfyUI's folder_paths.")
        return True

    except Exception as e:
        status_callback(f"Error loading ComfyUI folder_paths: {e}")
        messagebox.showerror("Loading Error", f"Error loading ComfyUI folder_paths:\n{e}")
        return False
    finally:
        sys.path = original_sys_path

# --- 修改后的 get_destination_folder 函数 ---
def get_destination_folder(model_type_key, comfyui_base_path, status_callback):
    """Get the preferred destination folder path, falling back to known defaults."""
    global folder_paths
    if not folder_paths:
        status_callback("错误: folder_paths 模块未成功加载。")
        return None

    # 统一使用小写关键字进行查找，增加兼容性
    model_type_key_lower = model_type_key.lower()

    target_folder = None # 初始化目标文件夹

    try:
        # 1. 优先尝试从 ComfyUI 配置获取路径
        paths = folder_paths.get_folder_paths(model_type_key_lower)
        if paths:
            target_folder = paths[0] # 使用 ComfyUI 官方/用户配置的路径
            status_callback(f"信息: 使用 ComfyUI 配置路径 '{target_folder}' (关键字: '{model_type_key_lower}')")

    except KeyError:
        # 2. 如果 ComfyUI 不认识这个关键字 (KeyError)，尝试从我们的备选默认路径查找
        status_callback(f"信息: ComfyUI 配置中未找到关键字 '{model_type_key_lower}'。尝试 Mover 默认路径...")
        # *** 使用新的备选字典 ***
        default_subdir = known_missing_key_to_subdir.get(model_type_key_lower)

        if default_subdir:
            # 构建默认路径: ComfyUI根目录/models/子目录名
            target_folder = os.path.join(comfyui_base_path, "models", default_subdir)
            status_callback(f"信息: 使用 Mover 默认路径 '{target_folder}' (关键字: '{model_type_key_lower}')")
        else:
            # 在 ComfyUI 配置和我们的备选默认路径中都找不到
            status_callback(f"错误: 无法为关键字 '{model_type_key_lower}' 确定目标文件夹。请检查 ComfyUI 配置或 Mover 的内置映射。")
            return None # 确实无法处理

    except Exception as e:
        # 其他访问 folder_paths 的错误
        status_callback(f"错误: 获取 ComfyUI 路径时出错 (关键字 '{model_type_key_lower}'): {e}")
        return None

    # 3. 如果找到了路径 (无论是来自 ComfyUI 配置还是 Mover 默认)，则创建目录并返回
    if target_folder:
        try:
            os.makedirs(target_folder, exist_ok=True) # 确保目录存在
            return target_folder
        except OSError as e:
             status_callback(f"错误: 创建目标目录 '{target_folder}' 失败: {e}")
             return None
    else:
        # 如果 get_folder_paths 返回空列表 (理论上不常见，但处理一下)
        status_callback(f"警告: 未能为关键字 '{model_type_key_lower}' 获取有效路径。")
        return None


# --- GUI Application Class (Sidebar Layout) ---
class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("ComfyUI Model Mover")
        self.geometry("900x700")
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.config_path = os.path.join(get_script_dir(), CONFIG_FILE)
        self.processing_thread = None
        self.current_mode = "html" # Default mode

        # --- Main Window Grid Configuration ---
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Top Frame for Common Paths ---
        self.common_path_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.common_path_frame.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 5), sticky="ew")
        self.common_path_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.common_path_frame, text="Download Folder:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.download_path_entry = ctk.CTkEntry(self.common_path_frame, width=400)
        self.download_path_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkButton(self.common_path_frame, text="Browse...", width=60, command=self.browse_download_folder).grid(row=0, column=2, padx=5, pady=5)
        ctk.CTkLabel(self.common_path_frame, text="ComfyUI Root:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.comfyui_path_entry = ctk.CTkEntry(self.common_path_frame, width=400)
        self.comfyui_path_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkButton(self.common_path_frame, text="Browse...", width=60, command=self.browse_comfyui_folder).grid(row=1, column=2, padx=5, pady=5)

        # --- Left Sidebar Frame ---
        self.sidebar_frame = ctk.CTkFrame(self, width=150, corner_radius=0)
        self.sidebar_frame.grid(row=1, column=0, rowspan=2, padx=(10, 0), pady=(5, 10), sticky="nsw")
        self.sidebar_frame.grid_rowconfigure(4, weight=1)
        self.sidebar_label = ctk.CTkLabel(self.sidebar_frame, text="Modes", font=ctk.CTkFont(size=16, weight="bold"))
        self.sidebar_label.grid(row=0, column=0, padx=20, pady=(20, 10))
        self.html_mode_button = ctk.CTkButton(self.sidebar_frame, text="HTML Mode", command=lambda: self.show_content_frame("html"))
        self.html_mode_button.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        self.ai_mode_button = ctk.CTkButton(self.sidebar_frame, text="AI Mode", command=lambda: self.show_content_frame("ai"))
        self.ai_mode_button.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        self.appearance_mode_label = ctk.CTkLabel(self.sidebar_frame, text="Appearance:", anchor="w")
        self.appearance_mode_label.grid(row=5, column=0, padx=20, pady=(10, 0), sticky="s")
        self.appearance_mode_optionemenu = ctk.CTkOptionMenu(self.sidebar_frame, values=["Light", "Dark", "System"],
                                                               command=self.change_appearance_mode_event)
        self.appearance_mode_optionemenu.grid(row=6, column=0, padx=20, pady=(0, 20), sticky="s")

        # --- Right Main Content Frame ---
        self.content_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.content_frame.grid(row=1, column=1, padx=(5, 10), pady=(5, 0), sticky="nsew")

        # --- Bottom Status Log Frame ---
        self.status_frame = ctk.CTkFrame(self)
        self.status_frame.grid(row=2, column=1, padx=(5, 10), pady=(0, 10), sticky="nsew")
        self.status_frame.grid_columnconfigure(0, weight=1)
        self.status_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(self.status_frame, text="Processing Log:").grid(row=0, column=0, padx=5, sticky="w")
        self.status_textbox = ctk.CTkTextbox(self.status_frame, state="disabled", wrap="word", height=150)
        self.status_textbox.grid(row=1, column=0, padx=5, pady=5, sticky="nsew")

        # --- Initialize ---
        self.load_initial_paths()
        self.show_content_frame(self.current_mode)
        self.appearance_mode_optionemenu.set("System")

    def build_html_mode_ui(self, parent_frame):
        """Creates widgets for the HTML mode in the parent_frame"""
        parent_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(parent_frame, text="HTML Metadata File:").grid(row=0, column=0, padx=5, pady=10, sticky="w")
        self.html_path_entry = ctk.CTkEntry(parent_frame, width=350) # Define instance variable
        self.html_path_entry.grid(row=0, column=1, padx=5, pady=10, sticky="ew")
        ctk.CTkButton(parent_frame, text="Browse...", width=60, command=self.browse_html_file).grid(row=0, column=2, padx=5, pady=10)
        loaded_paths = load_paths_from_config(self.config_path)
        if loaded_paths and 'html' in loaded_paths:
            self.html_path_entry.insert(0, loaded_paths.get('html', ''))
        self.process_button_html = ctk.CTkButton(parent_frame, text="Start Moving (HTML Mode - Overwrites)", command=lambda: self.start_processing(mode="html")) # Define instance variable
        self.process_button_html.grid(row=1, column=0, columnspan=3, pady=20)

    def build_ai_mode_ui(self, parent_frame):
        """Creates widgets for the AI mode in the parent_frame"""
        parent_frame.grid_rowconfigure(2, weight=1)
        parent_frame.grid_rowconfigure(5, weight=1)
        parent_frame.grid_columnconfigure(0, weight=1)
        self.list_files_button = ctk.CTkButton(parent_frame, text="List Files in Download Folder (for Copying)", command=self.list_download_files) # Define instance variable
        self.list_files_button.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        ctk.CTkLabel(parent_frame, text="Paste AI Response Here (Format: filename -> key):").grid(row=1, column=0, padx=10, pady=(10, 0), sticky="w")
        self.ai_response_textbox = ctk.CTkTextbox(parent_frame, wrap="word", height=150) # Define instance variable
        self.ai_response_textbox.grid(row=2, column=0, padx=10, pady=5, sticky="nsew")
        self.process_button_ai = ctk.CTkButton(parent_frame, text="Start Moving (AI Mode - Overwrites)", command=lambda: self.start_processing(mode="ai")) # Define instance variable
        self.process_button_ai.grid(row=3, column=0, padx=10, pady=10)
        ctk.CTkLabel(parent_frame, text="Download Folder Files (Output):").grid(row=4, column=0, padx=10, pady=(10,0), sticky="w")
        self.filename_list_textbox = ctk.CTkTextbox(parent_frame, state="disabled", wrap="none", height=100) # Define instance variable
        self.filename_list_textbox.grid(row=5, column=0, padx=10, pady=5, sticky="nsew")

    def show_content_frame(self, mode):
        """Clears the content frame and builds the UI for the selected mode"""
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        self.current_mode = mode
        self.html_mode_button.configure(fg_color=self.html_mode_button.cget("hover_color") if mode == "html" else "transparent")
        self.ai_mode_button.configure(fg_color=self.ai_mode_button.cget("hover_color") if mode == "ai" else "transparent")
        if mode == "html":
            self.build_html_mode_ui(self.content_frame)
        elif mode == "ai":
            self.build_ai_mode_ui(self.content_frame)
        else:
             ctk.CTkLabel(self.content_frame, text=f"Unknown mode: {mode}").pack()
        # Buttons are implicitly reset by being recreated

    def change_appearance_mode_event(self, new_appearance_mode: str):
        """Callback for changing appearance mode"""
        ctk.set_appearance_mode(new_appearance_mode)

    # --- GUI Methods ---
    def update_status(self, message):
        self.after(0, self._append_status_message, message)

    def _append_status_message(self, message):
        try:
            self.status_textbox.configure(state="normal")
            self.status_textbox.insert("end", f"{message}\n")
            self.status_textbox.configure(state="disabled")
            self.status_textbox.see("end")
        except tk.TclError as e: print(f"Error updating status textbox (maybe closed?): {e}")

    def load_initial_paths(self):
        self.update_status("Loading configuration...")
        loaded_paths = load_paths_from_config(self.config_path)
        if loaded_paths:
            if hasattr(self, 'download_path_entry'):
                 self.download_path_entry.delete(0, tk.END)
                 self.download_path_entry.insert(0, loaded_paths.get('download', ''))
            if hasattr(self, 'comfyui_path_entry'):
                  self.comfyui_path_entry.delete(0, tk.END)
                  self.comfyui_path_entry.insert(0, loaded_paths.get('comfyui', ''))
            self.update_status("Loaded saved paths.")
        else:
            self.update_status("No valid config found or paths invalid. Please set paths manually.")

    def browse_html_file(self):
        initial_dir = None
        if hasattr(self, 'html_path_entry') and self.html_path_entry.winfo_exists() and self.html_path_entry.get():
             initial_dir = os.path.dirname(self.html_path_entry.get())
        filepath = filedialog.askopenfilename(
            title="Select HTML Metadata File",
            filetypes=(("HTML files", "*.html;*.htm"), ("All files", "*.*")),
            initialdir=initial_dir
        )
        if filepath and hasattr(self, 'html_path_entry') and self.html_path_entry.winfo_exists():
            self.html_path_entry.delete(0, tk.END)
            self.html_path_entry.insert(0, filepath)

    def browse_download_folder(self):
        initial_dir = self.download_path_entry.get() if self.download_path_entry.get() else None
        dirpath = filedialog.askdirectory(title="Select Download Folder", initialdir=initial_dir)
        if dirpath:
            self.download_path_entry.delete(0, tk.END)
            self.download_path_entry.insert(0, dirpath)
            # Clear filename listbox only if it currently exists
            if self.current_mode == "ai" and hasattr(self, 'filename_list_textbox') and self.filename_list_textbox.winfo_exists():
                 self.filename_list_textbox.configure(state="normal")
                 self.filename_list_textbox.delete("1.0", tk.END)
                 self.filename_list_textbox.configure(state="disabled")

    def browse_comfyui_folder(self):
        initial_dir = self.comfyui_path_entry.get() if self.comfyui_path_entry.get() else None
        dirpath = filedialog.askdirectory(title="Select ComfyUI Root Folder", initialdir=initial_dir)
        if dirpath:
            self.comfyui_path_entry.delete(0, tk.END)
            self.comfyui_path_entry.insert(0, dirpath)

    def list_download_files(self):
        if not hasattr(self, 'filename_list_textbox') or not self.filename_list_textbox.winfo_exists():
             self.update_status("Error: Filename listbox not available in current view.")
             return
        download_path = self.download_path_entry.get().strip()
        if not download_path or not os.path.isdir(download_path):
             messagebox.showerror("Path Error", "Please select a valid Download Folder first.")
             return
        self.update_status(f"Listing files in {download_path}...")
        self.filename_list_textbox.configure(state="normal")
        self.filename_list_textbox.delete("1.0", tk.END)
        try:
            filenames = [f for f in os.listdir(download_path) if os.path.isfile(os.path.join(download_path, f))]
            filenames.sort()
            if filenames:
                 self.filename_list_textbox.insert("1.0", "\n".join(filenames))
                 self.update_status(f"Found {len(filenames)} files. List displayed below for copying.")
                 self.after(10, lambda: messagebox.showinfo("Files Listed", f"Found {len(filenames)} files... You can copy the list..."))
            else:
                 self.filename_list_textbox.insert("1.0", "(No files found)")
                 self.update_status("No files found in the download folder.")
        except Exception as e:
            self.filename_list_textbox.insert("1.0", f"Error listing files: {e}")
            self.update_status(f"Error listing files: {e}")
            self.after(10, lambda e=e: messagebox.showerror("Listing Error", f"Could not list files:\n{e}"))
        finally:
            self.filename_list_textbox.configure(state="disabled")

    # --- Processing Logic ---
    def start_processing(self, mode):
        if self.processing_thread and self.processing_thread.is_alive():
            messagebox.showwarning("Processing", "Already processing files. Please wait.")
            return
        if mode != self.current_mode:
             messagebox.showerror("Mode Error", f"Attempting to start process for '{mode}' mode, but '{self.current_mode}' mode is active.")
             return
        download_path = self.download_path_entry.get().strip()
        comfyui_path = self.comfyui_path_entry.get().strip()
        if not download_path or not os.path.isdir(download_path): messagebox.showerror("Path Error", "Please provide a valid Download Folder path."); return
        if not comfyui_path or not os.path.isdir(comfyui_path): messagebox.showerror("Path Error", "Please provide a valid ComfyUI Root Folder path."); return
        html_path = None
        ai_response_text = None
        if mode == "html":
            # Check widget exists before accessing .get()
            if not hasattr(self, 'html_path_entry') or not self.html_path_entry.winfo_exists():
                 messagebox.showerror("Internal Error", "HTML path entry widget not found."); return
            html_path = self.html_path_entry.get().strip()
            if not html_path or not os.path.isfile(html_path): messagebox.showerror("Path Error", "Mode 1 requires a valid HTML Metadata File path."); return
        elif mode == "ai":
             if not hasattr(self, 'ai_response_textbox') or not self.ai_response_textbox.winfo_exists():
                 messagebox.showerror("Internal Error", "AI response textbox widget not found."); return
             ai_response_text = self.ai_response_textbox.get("1.0", tk.END).strip()
             if not ai_response_text: messagebox.showerror("Input Error", "Mode 2 requires you to paste the AI response text."); return
        else: messagebox.showerror("Error", "Invalid processing mode specified."); return

        confirm = messagebox.askyesno(
            title="Confirm Action",
            message=f"Start moving files using Mode: '{mode.upper()}'?\n\n"
                    f"Files from:\n{download_path}\n\n"
                    f"Will be moved to corresponding ComfyUI folders inside:\n{comfyui_path}\n\n"
                    f"Based on {'HTML metadata' if mode == 'html' else 'AI response text'}.\n\n"
                    "WARNING: Existing files with the same name WILL BE OVERWRITTEN!\n\n"
                    "Continue?",
            icon=messagebox.WARNING )
        if not confirm: self.update_status("Operation cancelled by user."); return

        # --- Save Paths (Simplified Logic) ---
        current_paths = {'download': download_path, 'comfyui': comfyui_path}
        # Only save HTML path if we are currently in HTML mode and it's valid
        if mode == 'html' and html_path:
             current_paths['html'] = html_path
        else:
            # If not in HTML mode, try to preserve existing HTML path from config if it exists
            # This avoids erasing it when running AI mode.
            existing_paths = load_paths_from_config(self.config_path)
            if existing_paths and 'html' in existing_paths:
                 current_paths['html'] = existing_paths['html']

        save_paths_to_config(self.config_path, current_paths)

        # --- Disable Buttons and Start Thread ---
        self.status_textbox.configure(state="normal"); self.status_textbox.delete("1.0", tk.END); self.status_textbox.configure(state="disabled")
        self.update_status(f"User confirmed. Starting processing (Mode: {mode.upper()}, Overwrite: On)...")
        self._set_buttons_processing_state(True) # Disable relevant buttons

        self.processing_thread = threading.Thread(
            target=self.run_processing_thread,
            args=(mode, download_path, comfyui_path, html_path, ai_response_text),
            daemon=True )
        self.processing_thread.start()

    def run_processing_thread(self, mode, download_path, comfyui_path, html_path, ai_response_text):
        # (This function remains identical to the previous version - no changes needed here)
        global folder_paths, reference_data
        # --- 加载 JSON 参考数据 (如果尚未加载) ---
        if reference_data is None:
            ref_path = os.path.join(get_script_dir(), reference_data_path)
            if not os.path.exists(ref_path):
                self.update_status(f"错误: 参考 JSON 文件 '{reference_data_path}' 未在脚本目录中找到。")
                self.after(0, lambda: messagebox.showerror("错误", f"参考文件 '{reference_data_path}' 未找到。请将其放在脚本同目录下。"))
                self.after(0, self._set_buttons_processing_state, False)
                return
            try:
                self.update_status(f"正在加载参考数据: {reference_data_path}...")
                with open(ref_path, 'r', encoding='utf-8') as f_ref:
                    reference_data = json.load(f_ref)
                self.update_status("参考数据加载成功。")
            except Exception as e_ref:
                self.update_status(f"错误: 加载参考 JSON '{ref_path}' 失败: {e_ref}")
                self.after(0, lambda e=e_ref: messagebox.showerror("JSON 加载错误", f"加载参考 JSON 失败:\n{e}"))
                self.after(0, self._set_buttons_processing_state, False)
                return
        # --- JSON 数据加载结束 ---
        
        moved_count = 0; skipped_count = 0; error_count = 0; overwritten_count = 0
        filename_to_process_map = {} # 存储: {源文件名: (目标关键字, 原始映射文件名)}
        try:
            self.update_status(f"--- 开始处理模式: {mode.upper()} ---")

            # --- HTML 模式逻辑 (主要修改区域) ---
            if mode == "html":
                filename_nodetype_map = parse_model_info_from_html(html_path, self.update_status)
                if filename_nodetype_map is None: raise Exception("HTML 解析失败。")
                if not filename_nodetype_map:
                    self.update_status("警告: HTML 解析未产生任何条目。")
                else:
                    self.update_status(f"从 HTML 解析到 {len(filename_nodetype_map)} 个条目，开始映射目标文件夹...")
                    mapped_count = 0
                    skipped_mapping_count = 0

                    for fname_from_html, ntype_from_html in filename_nodetype_map.items():
                        target_key = None # 目标 ComfyUI 文件夹关键字 (如 'vae', 'checkpoints')

                        # 步骤 1: 尝试使用 JSON reference_data 和 output_types 进行映射
                        if ntype_from_html in reference_data:
                            loader_info = reference_data[ntype_from_html]
                            output_types = loader_info.get('output_types', [])
                            for out_type in output_types:
                                # 尝试在 output_type_to_folder_map 中查找 (统一转大写匹配)
                                potential_key = output_type_to_folder_map.get(out_type.upper())
                                if potential_key:
                                    target_key = potential_key
                                    # print(f"Debug: Found map via output_type: '{ntype_from_html}' -> '{out_type}' -> '{target_key}'") # 调试信息
                                    break # 找到第一个匹配就用它

                        # 步骤 2: 如果基于 output_types 没找到，尝试使用旧的 fallback 映射
                        if target_key is None:
                            # *** 使用正确的备选映射字典 (nodetype_to_folderkey) ***
                            target_key = nodetype_to_folderkey.get(ntype_from_html)
                            if target_key:
                                self.update_status(f"  信息: 节点类型 '{ntype_from_html}' 使用备选映射 -> '{target_key}'.")
                        # 步骤 3: 如果仍然没有找到映射
                        if target_key is None:
                            self.update_status(f"  警告: 无法为节点类型 '{ntype_from_html}' 确定目标文件夹关键字。跳过文件 '{fname_from_html}'.")
                            skipped_mapping_count += 1
                            continue # 跳过这个HTML条目

                        # 映射成功，记录下来准备处理
                        # 使用 HTML 中的 fname_from_html 作为要查找和移动的文件名
                        filename_to_process_map[fname_from_html] = (target_key, fname_from_html)
                        mapped_count += 1

                    self.update_status(f"完成映射: {mapped_count} 个条目成功映射, {skipped_mapping_count} 个条目因无法映射而被跳过。")
                    if not filename_to_process_map:
                        self.update_status("没有可处理的文件映射。")
                        # 提前结束，避免后续扫描文件夹
                        self.after(0, self._set_buttons_processing_state, False)
                        return

            # --- AI 模式逻辑 (按计划移除或保留旧逻辑) ---
            elif mode == "ai":
                 self.update_status("错误: AI 模式已计划移除，当前不可用。")
                 raise NotImplementedError("AI Mode is planned for removal.")
                 # ... (或者保留旧的 parse_ai_response 调用逻辑，但建议移除)

            else:
                raise Exception("内部错误: 无效的处理模式。")

            # --- 通用文件移动逻辑 ---
            if not initialize_folder_paths(comfyui_path, self.update_status):
                raise Exception("ComfyUI folder_paths 初始化失败。")

            if not filename_to_process_map:
                 # 如果经过映射后没有文件需要处理（例如HTML为空或所有条目都无法映射）
                 self.update_status("没有需要处理的文件。")
            else:
                self.update_status(f"开始扫描下载文件夹并移动 {len(filename_to_process_map)} 个已映射文件...")
                self.update_status(f"下载文件夹: {download_path}")

                try:
                    all_items_in_download = os.listdir(download_path)
                except FileNotFoundError: raise Exception(f"下载文件夹未找到: {download_path}")
                except OSError as e: raise Exception(f"读取下载文件夹错误 {download_path}: {e}")

                files_actually_found_in_download = set(f for f in all_items_in_download if os.path.isfile(os.path.join(download_path, f)))
                processed_files_counter = 0

                for filename_to_move, (target_key, original_mapped_filename) in filename_to_process_map.items():
                     processed_files_counter += 1
                     self.update_status(f"[{processed_files_counter}/{len(filename_to_process_map)}] 检查: {filename_to_move}")

                     # --- 过滤非模型文件 ---
                     if not is_likely_model_file(filename_to_move):
                         self.update_status(f"  -> 跳过: '{filename_to_move}' 根据名称/扩展名判断不是标准模型文件。")
                         skipped_count += 1
                         continue
                     # --- 过滤器结束 ---

                     # 在下载文件夹中查找文件
                     source_path = os.path.join(download_path, filename_to_move)
                     if not os.path.exists(source_path):
                         # 尝试匹配 basename (如果原始映射包含路径)
                         basename_to_match = os.path.basename(filename_to_move)
                         found_by_basename = False
                         if basename_to_match != filename_to_move: # 仅当原始名称包含路径时才尝试
                             potential_source_path = os.path.join(download_path, basename_to_match)
                             if os.path.exists(potential_source_path):
                                 source_path = potential_source_path
                                 self.update_status(f"  信息: 在下载目录中通过 basename '{basename_to_match}' 找到文件。")
                                 found_by_basename = True
                         
                         if not found_by_basename:
                             self.update_status(f"  -> 跳过: 文件 '{filename_to_move}' 在下载文件夹中未找到。")
                             skipped_count += 1
                             continue # 跳到下一个文件

                     # 获取目标文件夹
                     target_folder = get_destination_folder(target_key, comfyui_path, self.update_status)

                     if target_folder:
                         # 构建目标路径，保留原始映射文件名中的子目录结构
                         dest_filename = os.path.basename(original_mapped_filename) # 用映射源的文件名部分
                         sub_dirs = os.path.dirname(original_mapped_filename)     # 用映射源的子目录部分
                         final_target_folder = os.path.join(target_folder, sub_dirs) if sub_dirs else target_folder
                         destination_path = os.path.join(final_target_folder, dest_filename)

                         self.update_status(f"  -> 目标类型 '{target_key}'")
                         try:
                             # 确保目标目录存在
                             os.makedirs(final_target_folder, exist_ok=True)

                             target_exists = os.path.exists(destination_path)
                             # 构建相对路径用于日志显示
                             log_dest_path = os.path.join(os.path.basename(target_folder), sub_dirs, dest_filename) if sub_dirs else os.path.join(os.path.basename(target_folder), dest_filename)

                             if target_exists:
                                 self.update_status(f"  -> 移动 (覆盖!) 到: ...{os.sep}{log_dest_path}")
                             else:
                                 self.update_status(f"  -> 移动到: ...{os.sep}{log_dest_path}")

                             shutil.move(source_path, destination_path)

                             if target_exists:
                                 self.update_status(f"  -> 覆盖成功!")
                                 overwritten_count += 1
                             else:
                                  self.update_status(f"  -> 移动成功!")
                             moved_count += 1

                         except Exception as move_e:
                             self.update_status(f"  -> 错误: 移动文件 {filename_to_move} 时出错: {move_e}")
                             error_count += 1
                     else:
                         self.update_status(f"  -> 跳过: 无法为关键字 '{target_key}' 确定或创建目标文件夹。")
                         skipped_count += 1

                # 统计在 map 中但从未在下载文件夹中找到的文件 (可选，可能意义不大，因为上面已经处理了)
                # map_files_processed_or_skipped = set(filename_to_process_map.keys())
                # files_in_map_never_found = map_files_processed_or_skipped - files_actually_found_in_download
                # if files_in_map_never_found:
                #    self.update_status(f"Info: {len(files_in_map_never_found)} files from map were never found in download folder.")

            # --- 最终总结 ---
            self.update_status("-" * 30)
            self.update_status("处理完成!")
            self.update_status(f"已移动: {moved_count} 文件")
            if overwritten_count > 0:
                self.update_status(f"(其中 {overwritten_count} 个文件被覆盖)")
            self.update_status(f"已跳过 (映射/目标路径/非模型/未找到): {skipped_count} 文件")
            self.update_status(f"移动时出错: {error_count} 文件")

        except Exception as e:
            self.update_status(f"严重错误: 处理过程中发生意外: {e}")
            import traceback
            self.update_status(traceback.format_exc()) # 打印更详细的错误堆栈
            self.after(0, lambda e=e: messagebox.showerror("处理错误", f"发生错误:\n{e}"))
        finally:
            self.after(0, self._set_buttons_processing_state, False) # 重新启用按钮

    def _set_buttons_processing_state(self, is_processing):
        """Enable/disable buttons based on processing state, checking existence and validity"""
        new_state = "disabled" if is_processing else "normal"
        html_text = "Processing..." if is_processing else "Start Moving (HTML Mode - Overwrites)"
        ai_text = "Processing..." if is_processing else "Start Moving (AI Mode - Overwrites)"
        try:
            # Check if the attribute exists AND if the widget still exists before trying to configure
            if hasattr(self, 'process_button_html') and self.process_button_html.winfo_exists():
                 self.process_button_html.configure(state=new_state, text=html_text)
            if hasattr(self, 'process_button_ai') and self.process_button_ai.winfo_exists():
                 self.process_button_ai.configure(state=new_state, text=ai_text)
            if hasattr(self, 'list_files_button') and self.list_files_button.winfo_exists():
                 self.list_files_button.configure(state=new_state)
        except Exception as e: # Catch broader exceptions during configure
             # Log error instead of crashing if configure fails for unexpected reason
             print(f"Error configuring button state: {e}")


# --- Program Entry Point ---
if __name__ == "__main__":
    # Dependency check
    try:
        import customtkinter
    except ImportError as missing_dep:
        dep_name = str(missing_dep).split("'")[-2]
        print(f"Error: Missing dependency: {dep_name}")
        print("Please install required libraries:")
        print("pip install customtkinter")
        print("(For HTML Mode: pip install beautifulsoup4)")
        print("(Optional but recommended for HTML Mode: pip install lxml)")
        input("Press Enter to exit...")
        sys.exit(1)
    # 考虑到JSON可能也比较大，放在线程里按需加载更好。

    app = App()
    app.protocol("WM_DELETE_WINDOW", app.destroy) # Graceful exit
    app.mainloop()