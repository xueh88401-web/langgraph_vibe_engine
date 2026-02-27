"use client";
import { useEffect, useState } from "react";

export default function FileTree({ onFileSelect }) {
  const [tree, setTree] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch("/api/get_directory_tree")
      .then(res => {
        if (!res.ok) {
          throw new Error(`HTTP error! status: ${res.status}`);
        }
        return res.json();
      })
      .then(data => {
        setTree(data);
        setLoading(false);
      })
      .catch(err => {
        console.error("API 请求失败:", err);
        setError(err.message);
        setLoading(false);
      });
  }, []);

  const renderTree = (nodes, level = 0) => {
    if (!nodes || nodes.length === 0) return null;
    
    return nodes.map((node) => (
      <div key={node.path} style={{ paddingLeft: `${level * 16}px` }}>
        <div 
          style={{ 
            padding: '4px 0', 
            display: 'flex', 
            alignItems: 'center',
            cursor: node.type === 'file' ? 'pointer' : 'default',
            color: node.type === 'file' ? '#0066cc' : 'inherit',
            borderRadius: '4px',
            transition: 'background-color 0.2s'
          }}
          onClick={() => node.type === 'file' && onFileSelect?.(node.path)}
          onMouseEnter={(e) => {
            if (node.type === 'file') {
              e.currentTarget.style.backgroundColor = '#e8f4f8';
            }
          }}
          onMouseLeave={(e) => {
            if (node.type === 'file') {
              e.currentTarget.style.backgroundColor = 'transparent';
            }
          }}
        >
          <span style={{ marginRight: '4px' }}>
            {node.type === "folder" ? "📁" : "📄"}
          </span>
          <span>{node.name}</span>
          {node.line_count !== undefined && (
            <span style={{ marginLeft: '8px', fontSize: '12px', color: '#666' }}>
              ({node.line_count} 行)
            </span>
          )}
        </div>
        {node.children && node.children.length > 0 && (
          <div>
            {renderTree(node.children, level + 1)}
          </div>
        )}
      </div>
    ));
  };

  return (
    <div style={{ 
      width: '256px', 
      borderRight: '1px solid #ccc', 
      height: '100vh', 
      overflow: 'auto', 
      padding: '8px',
      backgroundColor: '#f9f9f9'
    }}>
      <div style={{ fontWeight: 'bold', marginBottom: '10px', paddingBottom: '8px', borderBottom: '1px solid #ddd' }}>
        文件树
      </div>
      {loading ? (
        <div style={{ padding: '8px', color: '#666' }}>加载中...</div>
      ) : error ? (
        <div style={{ padding: '8px', color: 'red' }}>
          错误: {error}
          <div style={{ fontSize: '12px', marginTop: '4px', color: '#666' }}>
            请确保 Python 服务器正在运行 (python server.py)
          </div>
        </div>
      ) : tree.length === 0 ? (
        <div style={{ padding: '8px', color: '#666' }}>空目录</div>
      ) : (
        renderTree(tree)
      )}
    </div>
  );
}