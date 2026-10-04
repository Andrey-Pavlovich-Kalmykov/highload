from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any

app = FastAPI(title="HW1 Simple CRUD API")

# In-memory хранилище
items_db: Dict[int, Dict[str, Any]] = {}
current_id = 1

class ItemCreate(BaseModel):
    name: str
    description: str | None = None
    price: float

class ItemResponse(ItemCreate):
    id: int

@app.post("/items/", response_model=ItemResponse, status_code=201)
async def create_item(item: ItemCreate):
    global current_id
    new_item = item.model_dump()
    new_item["id"] = current_id
    items_db[current_id] = new_item
    current_id += 1
    return new_item

@app.get("/items/", response_model=List[ItemResponse])
async def get_items():
    return list(items_db.values())

@app.put("/items/{item_id}", response_model=ItemResponse)
async def update_item(item_id: int, item: ItemCreate):
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")
    
    updated_item = item.model_dump()
    updated_item["id"] = item_id
    items_db[item_id] = updated_item
    return updated_item

@app.delete("/items/{item_id}", status_code=204)
async def delete_item(item_id: int):
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")
    del items_db[item_id]
    return None

@app.get("/endpoints", response_model=List[str])
async def get_endpoints():
    """
    Возвращает список всех зарегистрированных API ручек (путей).
    Понадобится генератору дашбордов для автоматического получения списка.
    """
    endpoints = set()
    for route in app.routes:
        if hasattr(route, "path") and route.path not in [
            "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc",
            "/metrics", "/health", "/endpoints"
        ]:
            endpoints.add(route.path)
    return list(endpoints)

@app.get("/health")
async def health_check():
    """
    Проверка жизнеспособности сервиса для docker-compose.
    """
    return {"status": "ok"}
