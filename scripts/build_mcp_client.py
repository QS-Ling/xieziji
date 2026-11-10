"""Build a source-only MCP client bundle; never include instance data or fonts."""
import argparse
import pathlib
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def build_client(output):
    output = pathlib.Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    files = sorted((ROOT / 'backend').glob('*.py'))
    files += [ROOT / p for p in ('backend/cursive_rules.json', 'requirements-mcp.txt',
              'LICENSE', 'NOTICE', 'docs/mcp.md', 'examples/mcp/codex.toml', 'examples/mcp/dsh.patch.yml')]
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, 'zhijian-mcp-client/' + path.relative_to(ROOT).as_posix())
        archive.writestr('zhijian-mcp-client/README.txt',
            'Writing workbench MCP client / 写字台 MCP 客户端\n\n'
            '在此目录创建 Python 虚拟环境，安装 requirements-mcp.txt。\n'
            '适配器入口：backend/mcp_server.py。请在正式网页的“如何调用 AI”中填写本机路径并复制配置。\n'
            '配对前在网页占用 AI 档口；退出 AI 不会清空共享文档或停止机器。\n'
            '运行命令：python backend/mcp_server.py --api-url http://127.0.0.1:8080\n'
            '详见 docs/mcp.md。本包不含字体、存档、设备配置、服务令牌或模型密钥。\n')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=pathlib.Path, default=ROOT / 'frontend/mcp-client.zip')
    print(build_client(parser.parse_args().output))
