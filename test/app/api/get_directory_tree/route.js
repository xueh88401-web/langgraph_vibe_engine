import { NextResponse } from 'next/server';

const PYTHON_SERVER_URL = process.env.PYTHON_SERVER_URL || 'http://localhost:5001';

export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const path = searchParams.get('path') || '/';
    
    // 调用 Python Flask 服务器
    const response = await fetch(`${PYTHON_SERVER_URL}/api/get_directory_tree?path=${encodeURIComponent(path)}`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error(`Python server error: ${response.status}`);
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('API 错误:', error);
    return NextResponse.json(
      { error: error.message || 'Failed to fetch directory tree' },
      { status: 500 }
    );
  }
}
