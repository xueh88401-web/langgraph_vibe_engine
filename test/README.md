# Workspace Explorer

前端文件浏览器，使用 Next.js + Flask 架构。

## 启动步骤

### 1. 安装 Python 依赖

```bash
cd /Users/kker/project/langgraph_vibe_engine
pip install -r requirements.txt
```

### 2. 启动 Flask 服务器（Python 后端）

在一个终端窗口中：

```bash
cd /Users/kker/project/langgraph_vibe_engine/test
python server.py
```

服务器将在 `http://localhost:5000` 启动。

### 3. 启动 Next.js 前端

在另一个终端窗口中：

```bash
cd /Users/kker/project/langgraph_vibe_engine/test
npm run dev
```

前端将在 `http://localhost:3000` 启动。

## 架构说明

- **Flask 服务器** (`server.py`): 提供目录树 API (`/api/get_directory_tree`)
- **Next.js API 路由** (`app/api/get_directory_tree/route.js`): 作为代理，调用 Flask 服务器
- **前端组件** (`app/FileTree.jsx`): 显示文件树界面

## 环境变量

如果需要修改 Flask 服务器地址，可以在 `.env.local` 中设置：

```
PYTHON_SERVER_URL=http://localhost:5000
```
