"use client";
import { useState } from "react";
import FileTree from './FileTree';

export default function Home() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileContent, setFileContent] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleFileSelect = async (filePath) => {
    if (!filePath || filePath === '/') return;
    
    setSelectedFile(filePath);
    setLoading(true);
    
    try {
      const response = await fetch(`/api/read_document?path=${encodeURIComponent(filePath)}`);
      if (response.ok) {
        const data = await response.json();
        setFileContent(data);
      } else {
        setFileContent({ error: '无法加载文件内容' });
      }
    } catch (error) {
      setFileContent({ error: error.message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', height: '100vh' }}>
      <FileTree onFileSelect={handleFileSelect} />
      <div style={{ 
        flex: 1, 
        padding: 20, 
        overflow: 'auto',
        backgroundColor: '#fff'
      }}>
        {loading ? (
          <div>加载中...</div>
        ) : fileContent ? (
          <div>
            <h2 style={{ marginBottom: '16px', borderBottom: '2px solid #eee', paddingBottom: '8px' }}>
              {fileContent.title || selectedFile}
            </h2>
            {fileContent.error ? (
              <div style={{ color: 'red' }}>{fileContent.error}</div>
            ) : (
              <div>
                <div style={{ marginBottom: '8px', color: '#666', fontSize: '14px' }}>
                  路径: {fileContent.path} | {fileContent.line_count} 行
                </div>
                <pre style={{ 
                  backgroundColor: '#f5f5f5', 
                  padding: '16px', 
                  borderRadius: '4px',
                  overflow: 'auto',
                  whiteSpace: 'pre-wrap',
                  fontFamily: 'monospace',
                  fontSize: '14px',
                  lineHeight: '1.6'
                }}>
                  {fileContent.content && fileContent.content.length > 0 
                    ? fileContent.content.map((line, i) => `${i + 1}: ${line}`).join('\n')
                    : '(文件为空)'
                  }
                </pre>
              </div>
            )}
          </div>
        ) : (
          <div style={{ color: '#999' }}>请从左侧文件树中选择一个文件</div>
        )}
      </div>
    </div>
  );
}