import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from store_module import get_artifact_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with get_artifact_store() as active_store:
        app.state.store = active_store
        yield


app = FastAPI(lifespan = lifespan)

@app.get("/view/{user_id}/{artifact_id}", response_class=HTMLResponse)
async def view_artifact(user_id:str, artifact_id: str, request: Request):
    
    st = getattr(request.app.state, 'store', None)
    
    if st:
        record = await st.aget(('artifact', user_id), artifact_id)
    else:
        raise HTTPException(status_code=500, detail="Database store is unavailable.")
 
    return HTMLResponse(content=record.value)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8010)