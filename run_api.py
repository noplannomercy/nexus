import uvicorn
import config

if __name__ == "__main__":
    uvicorn.run("api.main:app", host="0.0.0.0", port=config.API_PORT, reload=False)
