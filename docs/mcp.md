# 共享写字台与 AI MCP 接口

网页、机器共享工作区与 AI 档口分开：

- 同一控制器、同一设备端口共用文字、排版、缓存预览和实时书写进度。所有获准访问服务的网页都能查看、手动编辑、操作机器，不需要占用 AI。
- 同一台机器一次只允许一位使用者占用 AI 档口。占用者通过一次性配对码接入自己的 Codex 或 DeepSeek Harness（DSH）。
- 退出 AI 占用撤销本轮全部 AI 会话，不清空文档、不改变预览、不停止正在执行的任务。下一位的 AI 接着读同一份内容。
- 网页与 AI 修改都使用现有 revision 校验，拒绝旧版本覆盖；运行中页面始终执行已缓存的固定路径。

前端首页提供“如何调用 AI”入口，打开 `/ai-help.html`。包含安装步骤、按当前服务地址生成的 Codex/DSH 配置、复制按钮、配对流程、文本/公式示例、预览调节、共享与交接说明。指南页面不用占用 AI 即可查看。

## 安装

业务后端仍使用 Python 3.10+ 标准库。AI 适配器在每位使用者自己的电脑运行，使用 stdio MCP，经 HTTP 连接业务服务器；无需在使用者电脑启动串口控制端。

```powershell
python -m venv .venv-mcp
.venv-mcp\Scripts\python.exe -m pip install -r requirements-mcp.txt
```

可选依赖为官方 MCP Python SDK 1.x 维护线 `>=1.28,<2` 及 Pillow。Pillow 将后端返回的确切笔画折线转换成 PNG，供支持看图的宿主模型检查布局。未执行通用 SVG 脚本、网络资源或字体渲染。

## Codex / DSH 连接

[Codex 示例](../examples/mcp/codex.toml) 与 [DSH overlay](../examples/mcp/dsh.patch.yml) 中的路径需要改成**各自电脑**的 Python、项目脚本路径；服务器地址改成实际可达的业务 API。也可在前端指南填写路径后复制配置。

配置启动命令的实际形式为：

```powershell
C:/path/to/python.exe C:/path/to/project/backend/mcp_server.py --api-url http://server:8080
```

DSH 使用官方 `@deepseek-ai/dsh-mcp-client` 插件加载 stdio 服务，命令如 `npx @deepseek-ai/dsh web --patch ./writing.patch.yml`。这是可复用的 MCP 适配器及配置，尚未发布独立 DSH/Codex 商店插件。当前也不直接在公网提供 Streamable HTTP MCP 端点。

AI 使用宿主自己的模型。网页中已有导入功能可加载 TXT、Markdown、文档 JSON；AI 可以直接将当前对话中可访问的题目、解答和 LaTeX 内容通过 `create_document` 送入后端。

## 配对与交接

1. 网页已显示本机共享文档与机器状态；需要 AI 时点击“占用 AI 档口”。
2. 点击“连接我的 AI”，复制提示词给宿主。提示词包含业务地址、控制器 ID、设备端口、一次性 AI 配对码。
3. AI 调用 `pair_workbench(controller, code)`。配对码 5 分钟有效，仅能使用一次，新码取代旧码。
4. AI 读取共享文档与 revision，试排、看图、调整，再发布到网页。
5. 点击“退出 AI 占用”或调用 `release_workbench`。可以在机器仍在书写时交接 AI，运行路径与进度保持原样。

也可由 AI 调用 `claim_workbench` 占用空闲 AI 档口，再让网页输入返回的浏览器配对码。`browser_pairing` 可以补发网页管理码。网页“连接另一网页管理 AI”可以给另一浏览器本轮管理权限；共享文字本来就可见，不需要该码。

MCP 默认将本机配对身份和当前会话凭证保存到 `~/.zhijian-plotter/mcp-sessions.json`。`--state-file` 或 `PLOTTER_MCP_STATE` 可以指定私有文件路径。退出后文件中的旧 AI 会话即使尚未清理，也会被服务器拒绝。

## 工具

| 工具 | 作用 |
| --- | --- |
| `workbench_status` / `list_controllers` | 查看 AI 档口占用状态与控制器编号 |
| `claim_workbench` / `pair_workbench` / `browser_pairing` / `release_workbench` | 领取、连接和交接 AI 档口 |
| `describe_capabilities` / `list_fonts` | 获取可调参数、手写变化范围和可用字体 |
| `read_workspace` | 读取共享正文、网页字段、可编辑参数和 revision |
| `create_document` | 备份已有正文，替换为 AI 文档、实际排版并保存共享文档快照 |
| `preview_document` | 独立试排，返回实际输出页数与指标，不替换当前工作区 |
| `update_document` | 实际排版成功后发布内容、参数与缓存预览 |
| `get_preview` / `get_preview_image` | 读取输出页指标、可选 SVG 或真实纸面笔画 PNG |
| `get_machine_state` | 读取当前任务、进度、状态和 ETA，不移动机器 |
| `save_document` / `list_documents` / `load_document` | 保存、列出、恢复本机共享文档快照 |

提示词模板 `optimize_document` 指导宿主按读取、试排、看图、更新的流程工作。文本润色由宿主模型完成，接口本身不调用模型 API，也无需额外模型密钥。

操作必须明确指定 `controller` 和 `device`。设备使用网页选中的实际端口，如 `SIMULATOR`、`COM5`、`/dev/ttyUSB0`；未选端口时用 `default`。不同端口的工作区依旧独立，切换 AI 使用者不会改变端口存档。

读取后使用 `expected_revision`。`settings` 为部分更新；`pages` 为**整份文档的预设页数组**，提供时替换全文，只调排版时应省略。

```json
{
  "controller": "windows",
  "device": "COM5",
  "expected_revision": 3,
  "settings": {
    "line_sizing": "size",
    "size": 4,
    "latin_size": 4,
    "line_looseness": 2,
    "humanization": {"enabled": true, "scale": 3, "rotation": 1, "baseline": 0.2}
  }
}
```

将参数传给 `preview_document` 检查实际页数及范围，可通过 `get_preview_image` 检查公式和整体疏密，再传给 `update_document`。每次生成可能重新随机笔迹，最终以发布到网页的缓存预览为准。复杂公式、缺字、边界溢出均由原排版器校验；没有强行塞入固定页数的保证。

## 接口与权限

- `GET /api/workbench/status`：AI 档口状态。
- `POST /api/workbench/claim`：名称、可选本机身份凭证与客户端类型。
- `POST /api/workbench/pair`：生成 `ai` 或 `browser` 配对码，需要本轮管理凭证。
- `POST /api/workbench/redeem`：兑换一次性配对码并绑定用途。
- `POST /api/workbench/release`：撤销本轮 AI 档口凭证，不操作机器。
- `GET /api/library`、`POST /api/library/save|load|new`：本机共享文档快照，变更需要最新 revision。

AI 适配器发送 `X-Workbench-Client: ai` 和当前 `X-Workbench-Key`。AI 必须持有有效本轮凭证；即使知道共享服务令牌，退出后的旧 AI 凭证也不能退回网页权限继续调用。AI 仅有文档、预览和读取进度的能力，不提供启动、暂停、点动、抬落笔等机器操作。

网页使用原有服务访问令牌，或经明确网页配对获得的浏览器访问凭证 `X-Workbench-Web`。浏览器的服务访问权限与 AI 本轮占用分开，释放 AI 后仍可查看和编辑。服务 Host、Origin、Bearer 和 CORS 检查继续生效。共享面向可信现场使用者，未提供账号密码系统或管理员强制接管；不要把服务无认证暴露到不可信网络。

占用按控制器持久化，关闭浏览器不自动释放。书写任务由控制端独立负责，AI 档口不是机器运行锁。机器仍按现有机制拒绝冲突的执行请求，并要求网页确认纸张与原点。两人共同编辑可能触发版本冲突，此时需合并新内容，不能强行覆盖。

现有 `.workspaces` 和 `.previews` 继续使用，升级不迁移或清空原共享文字。AI 档口元数据与共享快照保存在任务目录 `.workbench/`，已加入忽略规则。内容与预览属于本机共享数据，不按使用者隔离。

## 验证

```powershell
python -m unittest tests.test_workbench tests.test_mcp tests.test_workspaces -v
node tests/test_workbench_ui.cjs
```

Python 测试覆盖共享文档、AI 独占、配对一次性与过期、旧 AI 撤权、浏览器访问连续性、运行中交接保持任务和路径、共享快照、实际预览图像及真实 stdio MCP 调用。浏览器测试使用两个隔离上下文验证无占用共同编辑、AI 发布预览、共享文档、AI 交接和前端指南。所有测试均使用临时目录、模拟器或替身，不连接真实写字机。浏览器测试需安装 Playwright 和本机 Edge。

参考：[Codex MCP](https://developers.openai.com/codex/mcp)、[DSH MCP 客户端](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md)、[官方 Python SDK 1.x](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x)。
