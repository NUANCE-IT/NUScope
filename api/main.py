from fastapi import FastAPI, Depends, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from auth.azure_ad import validate_token
import numpy as np
from io import BytesIO
from PIL import Image
import h5py

app = FastAPI(title="NUScope Web API")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "NUScope Web API"}

from fastapi import Security

@app.post("/process-image")
async def process_image(
    file: UploadFile = File(...),
    token_data: dict = Security(validate_token, scopes=["openid", "profile", "User.Read"])
):
    """Protected endpoint that requires Northwestern Azure AD auth"""
    try:
        # Verify user is from Northwestern
        if not token_data.get("preferred_username", "").endswith("@northwestern.edu"):
            raise HTTPException(status_code=403, detail="Northwestern affiliation required")
            
        # Process image (placeholder - will add actual microscopy processing)
        contents = await file.read()
        return {"status": "success", "user": token_data.get("preferred_username")}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
