import os
import time
import asyncio
import random
import aiohttp

APP_URL = os.getenv("APP_URL", "http://app:8000")
MAX_WORKERS = 15

async def wait_for_app():
    print("Waiting for app to be ready...")
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(f"{APP_URL}/health", timeout=2) as r:
                    if r.status == 200:
                        break
            except Exception:
                pass
            await asyncio.sleep(2)
    print("App is ready. Starting load test.")

async def worker(worker_id):
    async with aiohttp.ClientSession() as session:
        while True:
            # Распределяем веса для разных типов запросов
            action = random.choices(
                ["get", "post_ok", "post_err", "put_ok", "put_err", "delete_ok", "delete_err"],
                weights=[30, 20, 5, 15, 10, 10, 10],
                k=1
            )[0]
            
            try:
                if action == "get":
                    await session.get(f"{APP_URL}/items/")
                
                elif action == "post_ok":
                    data = {"name": f"item_{random.randint(1, 1000)}", "price": random.uniform(10.0, 100.0)}
                    await session.post(f"{APP_URL}/items/", json=data)
                    
                elif action == "post_err":
                    # Пропущено обязательное поле price -> 422 Unprocessable Entity
                    data = {"name": "invalid_item"}
                    await session.post(f"{APP_URL}/items/", json=data)
                    
                elif action == "put_ok":
                    # Делаем put на малые ID, предполагая, что post_ok их уже создал
                    item_id = random.randint(1, 10) 
                    data = {"name": "updated", "price": 99.99}
                    await session.put(f"{APP_URL}/items/{item_id}", json=data)
                    
                elif action == "put_err":
                    # PUT на несуществующий ID -> 404 Not Found
                    item_id = random.randint(9000, 9999)
                    data = {"name": "updated", "price": 99.99}
                    await session.put(f"{APP_URL}/items/{item_id}", json=data)

                elif action == "delete_ok":
                    item_id = random.randint(1, 10)
                    await session.delete(f"{APP_URL}/items/{item_id}")

                elif action == "delete_err":
                    # DELETE на несуществующий ID -> 404 Not Found
                    item_id = random.randint(9000, 9999)
                    await session.delete(f"{APP_URL}/items/{item_id}")
                    
            except Exception:
                pass 
            
            # Небольшая пауза, чтобы не повесить контейнер на 100% CPU
            await asyncio.sleep(random.uniform(0.05, 0.2))

async def main():
    await wait_for_app()
    
    workers = []
    for i in range(MAX_WORKERS):
        print(f"Spawning worker {i+1}/{MAX_WORKERS}")
        workers.append(asyncio.create_task(worker(i)))
        # Постепенное нарастание нагрузки
        await asyncio.sleep(2)
        
    # Ждем завершения (скрипт работает бесконечно)
    await asyncio.gather(*workers)

if __name__ == "__main__":
    asyncio.run(main())
