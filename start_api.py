"""
启动 Maximo RPA API 服务
"""
import uvicorn

if __name__ == "__main__":
    print("启动 Maximo RPA API 服务...")
    print("访问 http://localhost:8000/docs 查看 API 文档")
    print()
    
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
