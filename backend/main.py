from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.use_web.image_storage import ensure_image_dir
from src.API import router as v2_router
from src.lifecycle import register_lifecycle
from src.web_static import mount_spa, register_health

WEB_DRIVE_FORCE_HEADED_DEBUG = False  

app = FastAPI(title="mercari V2 订单管理", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/imges", StaticFiles(directory=ensure_image_dir()), name="imges")

# 注册 V2 根路由 → /mercariV2/src/...
app.include_router(v2_router, prefix="/mercariV2")

# 生命周期事件、兼容健康检查、前端 SPA 静态托管
register_lifecycle(app, force_headed_debug=WEB_DRIVE_FORCE_HEADED_DEBUG)
register_health(app)
mount_spa(app)  # 须最后挂载：根路径 "/" 会兜底其余未匹配路由


if __name__ == "__main__":
    from src.server import run

    run(app)
