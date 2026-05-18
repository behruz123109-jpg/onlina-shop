import asyncio
from pathlib import Path
from aiohttp import web

ROOT = Path(__file__).resolve().parent

async def products(request):
    sample_products = [
        {"id": 1, "name": "Olma", "price": 5000},
        {"id": 2, "name": "Banan", "price": 7000},
        {"id": 3, "name": "Sut", "price": 12000},
        {"id": 4, "name": "Non", "price": 2000}
    ]
    return web.json_response(sample_products)

async def serve_file(request):
    path = request.match_info.get('path', '')
    if path == '' or path == '/':
        path = 'index.html'
    file_path = ROOT / path
    if not file_path.exists() or not file_path.is_file():
        return web.Response(status=404, text='404 Not Found')
    return web.FileResponse(path=file_path)

app = web.Application()
app.router.add_get('/api/products', products)
app.router.add_get('/', serve_file)
app.router.add_get('/{path:.*}', serve_file)

if __name__ == '__main__':
    web.run_app(app, host='127.0.0.1', port=8080)
