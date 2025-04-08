import os
import base64
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv

# .envファイルを読み込む
load_dotenv()

app = FastAPI(title="Filesystem MCP Server")

# 環境変数から設定を読み込む
MCP_HOST = os.getenv("MCP_HOST", "localhost")
MCP_PORT = int(os.getenv("MCP_PORT", "8000"))
MCP_LOG_LEVEL = os.getenv("MCP_LOG_LEVEL", "info")
MCP_API_KEY = os.getenv("MCP_API_KEY")  # APIキー認証用（オプション）
MCP_BASE_PATH = os.getenv("MCP_BASE_PATH")  # ファイルシステムのルートパス制限（オプション）

# APIキー認証（オプション）
API_KEY_NAME = "X-MCP-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def get_api_key(api_key: str = Header(None, alias=API_KEY_NAME)):
    # APIキーが設定されていない場合は認証をスキップ
    if not MCP_API_KEY:
        return None
    
    if api_key and api_key == MCP_API_KEY:
        return api_key
    
    raise HTTPException(
        status_code=403, 
        detail="Invalid API key"
    )

# モデル定義
class FileRequest(BaseModel):
    path: str
    encoding: Optional[str] = None

class FileListRequest(BaseModel):
    path: str
    recursive: Optional[bool] = False

class FileInfo(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: Optional[int] = None
    modified: Optional[str] = None

class FileListResponse(BaseModel):
    files: List[FileInfo]

class FileContentResponse(BaseModel):
    content: str
    encoding: str

# パスの安全性を確認する関数
def safe_path(path: str) -> str:
    """
    パスが指定された基本パス内にあることを確認
    """
    abs_path = os.path.abspath(path)
    
    # 基本パスが設定されている場合、その範囲内かチェック
    if MCP_BASE_PATH:
        base_path = os.path.abspath(MCP_BASE_PATH)
        if not abs_path.startswith(base_path):
            raise HTTPException(
                status_code=403, 
                detail=f"Access to paths outside of {MCP_BASE_PATH} is not allowed"
            )
    
    return abs_path

# ルート
@app.get("/")
def read_root(api_key: Optional[str] = Depends(get_api_key)):
    return {"status": "Filesystem MCP server is running"}

# ファイル一覧取得
@app.post("/list", response_model=FileListResponse)
def list_files(request: FileListRequest, api_key: Optional[str] = Depends(get_api_key)):
    try:
        path = safe_path(request.path)
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Path not found")
        
        files = []
        
        if request.recursive:
            for root, dirs, filenames in os.walk(path):
                for dir_name in dirs:
                    dir_path = os.path.join(root, dir_name)
                    stat = os.stat(dir_path)
                    files.append(FileInfo(
                        name=dir_name,
                        path=dir_path,
                        is_dir=True,
                        size=None,
                        modified=stat.st_mtime
                    ))
                
                for file_name in filenames:
                    file_path = os.path.join(root, file_name)
                    stat = os.stat(file_path)
                    files.append(FileInfo(
                        name=file_name,
                        path=file_path,
                        is_dir=False,
                        size=stat.st_size,
                        modified=stat.st_mtime
                    ))
        else:
            items = os.listdir(path)
            for item in items:
                item_path = os.path.join(path, item)
                is_dir = os.path.isdir(item_path)
                stat = os.stat(item_path)
                
                files.append(FileInfo(
                    name=item,
                    path=item_path,
                    is_dir=is_dir,
                    size=None if is_dir else stat.st_size,
                    modified=stat.st_mtime
                ))
        
        return FileListResponse(files=files)
    
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

# ファイル読み込み
@app.post("/read", response_model=FileContentResponse)
def read_file(request: FileRequest, api_key: Optional[str] = Depends(get_api_key)):
    try:
        path = safe_path(request.path)
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="File not found")
        
        if os.path.isdir(path):
            raise HTTPException(status_code=400, detail="Cannot read directory")
        
        encoding = request.encoding or "utf-8"
        
        try:
            # テキストモードで読み込み
            with open(path, "r", encoding=encoding) as file:
                content = file.read()
                return FileContentResponse(content=content, encoding=encoding)
        except UnicodeDecodeError:
            # バイナリファイルの場合、base64エンコードして返す
            with open(path, "rb") as file:
                binary_content = file.read()
                base64_content = base64.b64encode(binary_content).decode("ascii")
                return FileContentResponse(content=base64_content, encoding="base64")
        
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(
        "filesystem_mcp:app",  # ファイル名に合わせて変更してください
        host=MCP_HOST, 
        port=MCP_PORT,
        log_level=MCP_LOG_LEVEL,
        reload=True
    )
