export const metadata = {
    title: 'Workspace Explorer',
    description: 'Workspace file explorer',
  };
  
  export default function RootLayout({ children }) {
    return (
      <html lang="zh-CN">
        <body>{children}</body>
      </html>
    );
  }