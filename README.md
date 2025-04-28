ComfyMover - ComfyUI 模型自动移动工具
这是一个简单的图形界面 (GUI) 工具，旨在帮助 ComfyUI 用户自动将下载的模型文件根据元数据移动到正确的 ComfyUI 模型子文件夹中。

✨ 功能特性
图形用户界面 (GUI): 使用 CustomTkinter 构建，界面简洁直观。

路径记忆: 自动保存上次使用的路径（HTML 元数据文件、下载文件夹、ComfyUI 根目录），方便下次使用。

基于元数据分类: 通过解析指定的 HTML 文件（包含模型文件名和对应的 ComfyUI 节点类型）来准确识别模型类型，避免了基于文件名的猜测。

集成 ComfyUI 路径: 调用 ComfyUI 自身的 folder_paths 逻辑来确定目标文件夹，支持用户自定义的模型路径 (extra_model_paths.yaml)。

覆盖确认: 在移动文件并可能覆盖目标文件夹中同名文件前，会弹出确认对话框，防止误操作。

跨平台兼容: 基于 Python 和 CustomTkinter，理论上可在 Windows, macOS, Linux 上运行（需安装相应依赖）。

安装助手: 提供 .bat 脚本简化 Python 环境检查和依赖安装 (Windows)。

📁 文件结构

ComfyMover/

├── main.py                   # 主程序 GUI 脚本

├── requirements.txt          # Python 依赖列表

├── run_ComfyMover.bat        # (Windows) 启动主程序的脚本

├── install_requirements.bat  # (Windows) 安装依赖的脚本

├── comfyui_mover_config.txt  # (自动生成) 保存用户路径配置的文件

└── README.md                 # 项目说明文件 (就是这个文件)

🚀 开始使用
1. 环境准备
安装 Python: 确保你的系统安装了 Python 3.8 或更高版本。可以从 python.org 下载。重要： 在 Windows 安装时，请务必勾选 "Add Python to PATH" 选项。

准备元数据文件: 你需要一个 HTML 文件，其中包含一个 ID 为 modelTable 的表格。这个表格需要至少包含两列，列标题需要以 "文件名" 和 "节点类型" 开头（忽略标题中的其他符号如 '▼'）。"节点类型" 列应包含 ComfyUI 加载器节点的名称（如 CheckpointLoaderSimple, VAELoader, ControlNetLoader 等）。你可以使用其他工具（如你的 ModelFinder）生成这个 HTML 文件。

2. 安装依赖
Windows: 直接双击运行 install_requirements.bat 文件。它会自动检查 Python 和 pip，并安装所需的库。

其他系统 (或手动安装): 打开终端或命令行，导航到项目文件夹，然后运行：

pip install -r requirements.txt

3. 运行工具
Windows: 双击运行 run_ComfyMover.bat 文件。

其他系统 (或手动运行): 打开终端或命令行，导航到项目文件夹，然后运行：

python main.py

4. 使用界面
程序启动后，会显示主窗口。

设置路径:

HTML 元数据文件: 点击“浏览...”选择你准备好的包含模型信息的 HTML 文件。

下载文件夹: 点击“浏览...”选择你下载模型文件存放的文件夹。

ComfyUI 根目录: 点击“浏览...”选择你的 ComfyUI 安装根目录（包含 models 文件夹和 folder_paths.py 的那个目录）。

程序会自动保存你设置的路径，下次启动时会自动加载。

开始移动: 点击 "开始移动文件 (覆盖模式)" 按钮。

确认操作: 程序会弹出一个确认框，提示你此操作会覆盖同名文件。仔细阅读后，如果确认无误，请点击“是”。

查看日志: 处理过程和结果会显示在下方的“处理日志”区域。

📝 注意事项
覆盖模式: 当前版本在移动文件时，如果目标文件夹已存在同名文件，将会覆盖。请务必确认这是你想要的行为。

HTML 文件准确性: 文件移动的准确性完全依赖于你提供的 HTML 元数据文件中“文件名”和“节点类型”的准确性。请确保 HTML 文件内容正确。

节点类型映射: 程序内部有一个从 HTML 中的“节点类型”到 ComfyUI 文件夹关键字的映射 (nodetype_to_folderkey 字典在 main.py 中)。如果你的 ComfyUI 使用了特殊的自定义节点或你的 HTML 文件中的节点类型名称与默认不同，你可能需要手动修改 main.py 中的这个字典。

📜 开源许可 (License)

本软件根据 MIT 许可证 授权。

🤝 贡献 (Contributing)
欢迎提交问题 (Issues) 和拉取请求 (Pull Requests)！如果你有任何改进建议或发现了 Bug，请在项目的仓库中提出。

📞 联系方式 (Contact)
微信号 wangdefa4567。
