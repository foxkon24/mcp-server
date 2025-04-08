import os
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
import httpx
import uvicorn
from dotenv import load_dotenv

# .envファイルを読み込む
load_dotenv()

app = FastAPI(title="Brave Search MCP Server")

# 環境変数から設定を読み込む
MCP_HOST = os.getenv("MCP_HOST", "localhost")
MCP_PORT = int(os.getenv("MCP_PORT", "8001"))
MCP_LOG_LEVEL = os.getenv("MCP_LOG_LEVEL", "info")
MCP_API_KEY = os.getenv("MCP_API_KEY")  # このサーバーのAPIキー認証用（オプション）
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")  # Brave Search APIキー

# Brave Search API の設定
BRAVE_SEARCH_API_URL = os.getenv("BRAVE_SEARCH_API_URL", "https://api.search.brave.com/res/v1/web/search")

# このサーバーのAPIキー認証（オプション）
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

# Brave Search APIキーの確認
def get_brave_api_key():
    if not BRAVE_API_KEY:
        raise HTTPException(
            status_code=500, 
            detail="Brave Search API key not configured. Please set BRAVE_API_KEY in .env file."
        )
    return BRAVE_API_KEY

# モデル定義
class SearchRequest(BaseModel):
    query: str
    count: Optional[int] = 10
    offset: Optional[int] = 0
    country: Optional[str] = "US"
    search_lang: Optional[str] = "en"

class SearchResult(BaseModel):
    title: str
    url: str
    description: str
    published_date: Optional[str] = None

class SearchResponse(BaseModel):
    results: List[SearchResult]
    total_count: int
    next_offset: Optional[int] = None

# ルート
@app.get("/")
def read_root(api_key: Optional[str] = Depends(get_api_key)):
    return {"status": "Brave Search MCP server is running"}

# 検索エンドポイント
@app.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest, 
    api_key: Optional[str] = Depends(get_api_key)
):
    try:
        brave_api_key = get_brave_api_key()
        
        params = {
            "q": request.query,
            "count": request.count,
            "offset": request.offset,
            "country": request.country,
            "search_lang": request.search_lang
        }
        
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": brave_api_key
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                BRAVE_SEARCH_API_URL,
                params=params,
                headers=headers
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Brave Search API error: {response.text}"
                )
            
            data = response.json()
            
            # 結果の加工
            results = []
            for item in data.get("web", {}).get("results", []):
                result = SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    description=item.get("description", ""),
                    published_date=item.get("published_date")
                )
                results.append(result)
            
            total_count = data.get("web", {}).get("total_results", 0)
            next_offset = request.offset + request.count if request.offset + request.count < total_count else None
            
            return SearchResponse(
                results=results,
                total_count=total_count,
                next_offset=next_offset
            )
            
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(
        "brave_search_mcp:app",  # ファイル名に合わせて変更してください
        host=MCP_HOST, 
        port=MCP_PORT,
        log_level=MCP_LOG_LEVEL,
        reload=True
    )
