# Formula OCR

![Windows](https://img.shields.io/badge/Windows-10%20%2F%2011-283027) ![Python](https://img.shields.io/badge/Python-3.12-283027) [![License: MIT](https://img.shields.io/badge/License-MIT-fff500)](LICENSE)

**截图识别数学公式，直接粘贴到 Word 继续编辑。** Formula OCR 是一款 Windows 桌面工具，也能识别论文截图里的正文、行内公式、独立公式和原始编号。识别使用你配置的视觉模型 API，预览和格式转换在本地完成。

![Formula OCR 日间界面：上方是原始截图，中间是排版预览，下方是可编辑源码](docs/images/ui-light.png)

<details>
<summary>查看夜间模式</summary>

![石墨灰等高线底面的夜间界面](docs/images/ui-dark.png)

</details>

## 安装与启动

**当前版本为 1.3**，提供两个 Windows 10/11 x64 单文件版本，任选一个即可。两个版本均可双击运行，使用同一套识别和导出功能，无需安装 Python。[查看 1.3 发布说明](https://github.com/sakiii3321/MathFormulas_OCR/releases/tag/v1.3)

| 版本与下载 | EXE 大小（约） | 运行依赖与选择建议 |
| --- | ---: | --- |
| [WebView2 轻量版](https://github.com/sakiii3321/MathFormulas_OCR/releases/download/v1.3/FormulaOCR-1.3-WebView2-Windows-x64.exe) | 58.3 MiB | 适合已安装 Microsoft WebView2 Runtime 的电脑，使用系统共享运行库 |
| [完整运行库版](https://github.com/sakiii3321/MathFormulas_OCR/releases/download/v1.3/FormulaOCR-1.3-Full-Windows-x64.exe) | 210.0 MiB | 内置 Python、Qt 和 Qt WebEngine 预览引擎，适合希望下载后直接使用的用户 |

轻量版需要 [Microsoft WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/#download-section)。缺少时程序会显示安装/修复入口；安装后重新启动即可。表中大小仅为应用下载包，不含共享运行时和使用时产生的缓存。

下载 EXE 后双击启动。首次使用在「API 设置」中配置视觉模型，也可先点击「查看示例」体验预览和导出。单文件版启动时会展开内置组件，请稍候。**两个版本的 OCR 都使用你配置的模型 API，完整运行库版不包含离线识别模型。**

升级前请先右键托盘图标选择「退出程序」，再启动新版。两版共用已有 API、快捷键和外观设置；同时运行会争用截图快捷键。[查看版本更新说明](CHANGELOG.md)，[历史版本](https://github.com/sakiii3321/MathFormulas_OCR/releases)。Release 附有 `SHA256SUMS.txt`，可用于校验下载文件。

### 从源码运行

需要 Windows 10 或 11 和 64 位 Python。建议使用 Python 3.12，确保 PowerShell 中可以运行 `python --version`。

```powershell
git clone https://github.com/sakiii3321/MathFormulas_OCR.git
cd MathFormulas_OCR
.\setup.cmd
.\run.cmd
```

也可以在 GitHub 下载源码 ZIP 并解压，首次双击 `setup.cmd` 安装依赖，之后双击 `run.cmd` 启动。想先看效果，可以在「混合模式」点击「查看示例」，直接体验编辑、预览和 Word 导出。

## 识别一张截图

1. 打开左栏「API 设置」，选择服务商并填写 API Key，以及账户可用的**视觉模型 ID**。
2. 只截一个公式时选「公式模式」，截取含正文、编号或插图的一段论文时选「混合模式」。
3. 按 **Ctrl+Shift+A**，拖动框选并松开，程序会把选区发送到配置的 API 识别。按 Esc 或右键可取消。也可以导入、拖入或粘贴图片，再点击识别。
4. 对照原图检查文字、上下标和公式编号。直接修改编辑区内容即可更新预览。点击「复制到 Word」，在桌面 Word 中保留源格式粘贴。

| 模式 | 适用内容 | 输出 |
| --- | --- | --- |
| 公式模式 | 单个公式、矩阵、多行公式 | 裸 LaTeX、行内或块级 LaTeX、`equation` 环境、MathML、Word 公式 |
| 混合模式 | 自然段、行内公式、独立公式、编号和裁剪插图 | Markdown、LaTeX、HTML、Word 富文本、含可编辑公式的 DOCX |

原图会按比例完整显示在上方展示框内，识别使用原始分辨率。在公式模式下，拖动分隔条或调整窗口大小时，预览会按实际宽高调整字号。常规字号为 27 px，最小字号默认 16 px，可在「使用设置 → 公式预览最小字号」中调整。达到下限后可滚动查看其余部分。

### 后台截图

点击主窗口右上角的 ×，可选择「转到后台」或「退出程序」。默认每次询问。勾选「记住我的选择」后会直接执行所选操作，也可以到「使用设置 → 关闭主窗口时」改回「每次询问」。

转到后台后，进行中的识别会继续，截图快捷键仍然有效。后台框选成功会唤出主窗口并自动识别，按 Esc 或右键取消则保持隐藏。点击托盘图标可恢复窗口，右键菜单也可直接退出。选择「退出程序」时，程序会等待进行中的识别结束后退出。

### 开机自启

在「使用设置」中勾选「开机自启（登录 Windows 后启动）」并保存。默认在下次登录时进入托盘，此时可直接使用截图快捷键。将关闭方式设为「退出程序」后，自启会显示主窗口。手动双击启动始终显示主窗口。

开机自启默认关闭，使用当前用户的 Windows 启动项，无需管理员权限。取消勾选并保存即可移除。完整运行库版、WebView2 轻量版和源码启动均支持，两版共用一个启动项，保存时使用当前运行版本的路径。移动 EXE 或源码目录后，请重新勾选并保存以更新启动路径。系统托盘不可用时会显示主窗口。

## API 配置

所有来源都使用支持 Base64 图片输入的 Chat Completions 接口。填写服务商控制台提供的完整模型 ID，普通文本模型无法读取截图。

| 来源 | 预设 Base URL | 模型填写方式 |
| --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | 账户可用的视觉模型 ID |
| 硅基流动 | `https://api.siliconflow.cn/v1` | 完整视觉模型 ID，包含组织前缀 |
| DeepSeek | `https://api.deepseek.com` | 程序预填 `deepseek-flash`，可按账户可用的视觉模型修改 |
| 自定义兼容接口 | 自行填写 | 支持图片输入的兼容模型，本机免鉴权服务可留空 Key |

**密钥和图片。** 默认仅在当前进程中使用密钥。勾选记住密钥后，程序通过 keyring 保存到 Windows 凭据管理器。识别会把当前图片发送给所选服务商，计费和数据处理规则以该服务商为准。

## 编辑与导出

混合模式用空行分段，行内公式用 `$…$`，独立公式前后的 `$$` 各占一行。例如：

```text
设 $S_n$ 为前 $n$ 个正整数之和。

$$
S_n = \frac{n(n+1)}{2}
\tag{1}
$$
```

- `\tag{1}` 保存原编号。输出到 Word 时，带编号的公式在段落中居中，编号使用右对齐制表位。
- 「导出 DOCX」将正文和原生 Word 公式写入文件，导出本身无需安装 Word。不同 Office 版本的粘贴效果可能不同，也可直接使用 DOCX。
- 插图按模型给出的区域从原图裁剪。导出含插图的 Markdown 或 LaTeX 时，请同时保留生成的 `_assets` 文件夹。
- 「使用设置」可修改截图快捷键，并为两种识别模式分别指定自动复制格式。切换左栏的夜间模式开关时，新主题从左下向右上展开。下次启动会沿用上次的主题。

**在 Word 中编辑公式。** 在公式模式下点击「复制到 Word」后粘贴。安装桌面 MathType 并启用其粘贴提示时，可在弹窗中选择 Word 原生公式（OMML）或 MathType 公式。对于用 `&=` 对齐的多行等式，两种格式都按等号对齐。Word 原生公式会将求和项放入对应的求和号中，避免出现多余的虚线占位框。

如需直接粘贴到 MathType 编辑器，可在输出格式中选择「MathML」并点击「复制代码」。

## 支持范围

支持常见图片格式，每张上限 10 MB，转换为 PNG 后也会检查大小。截图选区限于一个显示器内。混合模式适合单栏截图，低清符号、阅读顺序和插图边界需要核对。程序按内容结构重新排版，复杂表格以裁剪图片保留。

## 测试与打包

### WebView2 轻量版

轻量版的预览使用共享 **WebView2 Runtime**，打包时排除 Qt WebEngine。运行时缺失时，识别、源码编辑和导出仍可使用。版本选择和下载链接见上方「安装与启动」。

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-webview2.txt
.\.venv\Scripts\python.exe main_webview2.py
.\build-webview2.cmd
```

生成的单文件程序为 `dist\webview2\FormulaOCR-WebView2.exe`。预览桥接使用固定版本的 [SideView](https://github.com/AlexsanderMe/SideView)。浏览器数据保存在 `%LOCALAPPDATA%\FormulaOCR\WebView2`，不写入 EXE 所在目录。

Windows 桌面集成测试使用模拟 OCR，并在结束后恢复剪贴板：

```powershell
.\.venv\Scripts\python.exe tests\webview2_smoke.py
.\.venv\Scripts\python.exe tests\webview2_alignment_smoke.py
.\.venv\Scripts\python.exe tests\windows_capture_smoke.py --webview2
```

### 完整运行库版与自动测试

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest -q
.\build.cmd
```

自动测试使用模拟 API 响应，无需真实密钥。默认目录版从 `dist\FormulaOCR\FormulaOCR.exe` 启动，分发时请提供整个 `dist\FormulaOCR` 目录。运行 `build.cmd onefile` 可生成可单独分发的 `dist\FormulaOCR.exe`。

## 许可证

本项目采用 [MIT 许可证](LICENSE)。
