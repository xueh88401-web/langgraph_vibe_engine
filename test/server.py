"""
Flask 服务器 — 提供目录树 API
从 test.py 中提取 workspace 逻辑，提供 HTTP API
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import json
from typing import Optional
from pathlib import Path
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _load_workspace():
    """从文件加载 workspace"""
    workspace_file = Path(__file__).parent.parent / ".workspace.json"
    if workspace_file.exists():
        try:
            with open(workspace_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}


app = Flask(__name__)
CORS(app)  # 允许跨域请求

# ── Workspace（从文件加载）────────────────────────────
# 结构: { "/path/to/canvas": { "title": str, "content": [line1, line2, ...] } }
# 每次 API 请求时重新加载，确保获取最新数据
_WORKSPACE: dict[str, dict] = {}


def _normalize_path(path: str) -> str:
    """统一路径格式: 确保 / 开头，去掉尾部 /"""
    path = path.strip()
    if not path.startswith("/"):
        path = "/" + path
    path = path.rstrip("/")
    return path or "/"


def _list_children(parent: str) -> list[str]:
    """列出某个路径下的直接子画布"""
    parent = _normalize_path(parent)
    prefix = parent if parent == "/" else parent + "/"
    children = []
    for p in _WORKSPACE:
        if p == parent:
            continue
        if p.startswith(prefix):
            # 只取直接子级 (prefix 之后不再有 /)
            remainder = p[len(prefix):]
            if "/" not in remainder:
                children.append(p)
    return sorted(children)

def _get_canvas(path: str) -> Optional[dict]:
    return _WORKSPACE.get(_normalize_path(path))

def get_directory_tree(path: str = "/") -> list:
    """返回结构化的 JSON 树用于前端文件浏览器"""
    path = _normalize_path(path)

    def build(parent: str):
        nodes = []
        children = _list_children(parent)
        for child in children:
            canvas = _WORKSPACE[child]
            grandchildren = _list_children(child)

            nodes.append({
                "name": canvas["title"],
                "path": child,
                "type": "folder" if grandchildren else "file",
                "line_count": len(canvas["content"]),
                "children": build(child) if grandchildren else []
            })
        return nodes

    tree = build(path)
    return tree


# ── API 路由 ────────────────────────────────────────────────

@app.route('/api/get_directory_tree', methods=['GET'])
def api_get_directory_tree():
    """获取目录树"""
    global _WORKSPACE
    _WORKSPACE = _load_workspace()  # 重新加载
    path = request.args.get('path', '/')
    try:
        tree = get_directory_tree(path)
        return jsonify(tree)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/read_document', methods=['GET'])
def api_read_document():
    """读取文档内容"""
    global _WORKSPACE
    _WORKSPACE = _load_workspace()  # 重新加载
    path = request.args.get('path', '/')
    try:
        canvas = _get_canvas(path)
        if not canvas:
            return jsonify({"error": f"Canvas not found at '{path}'"}), 404
        
        return jsonify({
            "path": path,
            "title": canvas["title"],
            "content": canvas["content"],
            "line_count": len(canvas["content"])
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """健康检查"""
    return jsonify({"status": "ok"})


if __name__ == '__main__':
    print("启动 Flask 服务器...")
    print("API 地址: http://localhost:5001/api/get_directory_tree")
    app.run(host='0.0.0.0', port=5001, debug=True)
