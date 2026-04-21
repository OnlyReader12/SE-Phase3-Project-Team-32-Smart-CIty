import uvicorn
from fastapi import FastAPI
from database import db_core, models
from api import routes

# Boot the local SQLite DB structure
models.Base.metadata.create_all(bind=db_core.engine)

app = FastAPI(title="Persistent Semantic Middleware")

# Include all the sub-routes
app.include_router(routes.router)

print("=================================================")
print(" Middleware Booted and Persistent Storage Active")
print(" Access Dashboard: http://localhost:8001/view")
print("=================================================")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
