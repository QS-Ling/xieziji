# 部署与多控制端

Python 后端负责文字和路径，C++ 控制端负责 USB 串口执行，默认分别监听本机 8080 和 8090。

## 分机部署

控制端所在电脑：

```powershell
$env:CONTROLLER_TOKEN='replace-with-a-long-random-token'
.\controller\build\plotter-controller.exe --host 0.0.0.0 --allow-host controller.example --jobs-dir .\controller-jobs
```

业务后端所在电脑：

```powershell
$env:CONTROLLER_TOKEN='replace-with-a-long-random-token'
$env:PLOTTER_TOKEN='replace-with-another-long-random-token'
python -m backend.server --host 0.0.0.0 --allow-host writing.example --controller-url http://controller.example:8090 --font-dir 'C:\path\to\gcodeFonts'
```

将示例主机名换成实际地址。非本机监听需要至少 16 位令牌，跨网络使用受保护的隧道或 HTTPS 代理。控制端拒绝浏览器 Origin，只由后端访问。程序不会自动配置防火墙。

## 多控制端

创建私有文件，例如 `deploy/controllers-private.json`：

```json
[
  {"id": "windows", "name": "Windows 写字机", "url": "http://127.0.0.1:8090", "token": "replace-with-controller-one-token"},
  {"id": "linux", "name": "Linux 写字机", "url": "http://controller.example:8090", "token": "replace-with-controller-two-token"}
]
```

使用 `python -m backend.server --controllers-file deploy/controllers-private.json` 启动，按需指定字体、任务目录和网络参数。该文件仅在服务端读取，令牌不下发浏览器。

网页显式选择目标控制端；设备档案、正文、预览、任务与 ETA 按控制端和串口隔离。切换查看不停止另一台设备，每个控制端实例仍只执行一个活动串口任务。

后端接受注册项 `contact_startup`，用于支持相应校准协议的纸面接触启动控制端。本次快照来自 Windows 控制端，不能据此假定包含该特殊控制端实现；使用前需核对目标程序与设备要求。普通 GRBL 使用默认模式并按实物配置 Z 参数。

## 数据与升级

字体由用户自备；共享正文、预设、设备档案、文档快照、预览和 AI 配对记录保存在业务任务目录，控制端任务单独落盘。升级前备份数据目录与私有配置，保持源码和实例数据分离。

停止后端不会停止独立控制端任务；控制端退出后不支持断点续写。更换控制程序前先处理当前任务和设备状态。

本次重新发布不附带原服务器计划任务、域名配置、令牌或运行存档。按自己的环境设置服务，首页“如何调用 AI”会根据当前地址生成接入配置。
