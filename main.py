from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import shutil
import os
import json


from reports.ball_sorting_report import generate_clinical_pdf




app = FastAPI()

PASSWORD = "RehabXR-ENP@2026!Clinical"
app.mount("/assets", StaticFiles(directory="assets"), name="assets")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploaded_json"
OUTPUT_DIR = "generated_reports"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)



@app.get("/", response_class=HTMLResponse)
def login_page():
    with open("frontend/login.html", "r", encoding="utf-8") as f:
        return f.read()


@app.post("/login")
async def check_login(request: Request):
    data = await request.json()
    if data.get("password") == PASSWORD:
        return {"status": "ok"}
    return {"status": "error"}, 401


@app.get("/app", response_class=HTMLResponse)
def app_page():
    with open("frontend/index.html", "r", encoding="utf-8") as f:
        return f.read()
    


@app.post("/generate/ball")
async def generate_ball_report(
    file: UploadFile = File(...),
    patient_lastname: str = Form(""),
    patient_firstname: str = Form(""),
    patient_birthdate: str = Form(""),
    therapist_name: str = Form("")
):
    file_path = os.path.join(UPLOAD_DIR, file.filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    patient_info = {
        "lastname": patient_lastname,
        "firstname": patient_firstname,
        "birthdate": patient_birthdate,
        "therapist": therapist_name
    }

    pdf_path = generate_clinical_pdf(open(file_path, "rb"), patient_info)

    return FileResponse(pdf_path, filename=os.path.basename(pdf_path))