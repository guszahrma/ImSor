from fastapi import FastAPI

from .database import engine, Base
from .routers import auth, setup, users, images, duplicates, annotations, sharing, admin, communities

Base.metadata.create_all(bind=engine)

app = FastAPI(title="ImSor - Image Sorter", version="0.1.0")

app.include_router(auth.router)
app.include_router(setup.router)
app.include_router(users.router)
app.include_router(images.router)
app.include_router(duplicates.router)
app.include_router(annotations.router)
app.include_router(sharing.router)
app.include_router(admin.router)
app.include_router(communities.router)


@app.get("/")
def root():
    return {"service": "ImSor Central Web Service", "version": "0.1.0"}
