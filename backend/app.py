# main.py
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from diff_match_patch import diff_match_patch
from typing import List
import io
import PyPDF2
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

app = FastAPI()

# Configure FastMail
mail_config = ConnectionConfig(
    MAIL_USERNAME=os.getenv('EMAIL_USER'),
    MAIL_PASSWORD=os.getenv('EMAIL_PASSWORD'),
    MAIL_FROM=os.getenv('EMAIL_USER'),
    MAIL_PORT=587,
    MAIL_STARTTLS = True,
    MAIL_SERVER="smtp.gmail.com",
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=False
)

# Define request model
class ReminderRequest(BaseModel):
    email: EmailStr
    contractName: str
    daysUntilExpiry: int

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Adjust this to match your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RedlinedPart(BaseModel):
    id: int
    text: str
    type: str

class RedlinedResponse(BaseModel):
    redlinedText: List[RedlinedPart]

def extract_text_from_pdf(file: UploadFile) -> str:
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(file.file.read()))
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text()
    return text

@app.post("/api/compare-contracts", response_model=RedlinedResponse)
async def compare_contracts(
    original_contract: UploadFile = File(...),
    new_contract: UploadFile = File(...)
):
    if not original_contract or not new_contract:
        raise HTTPException(status_code=400, detail="Both contracts are required")

    # Extract text from PDFs
    original_text = extract_text_from_pdf(original_contract)
    new_text = extract_text_from_pdf(new_contract)

    # Perform diff
    dmp = diff_match_patch()
    diffs = dmp.diff_main(original_text, new_text)
    dmp.diff_cleanupSemantic(diffs)

    # Convert diff results to redlined text
    redlined_text = []
    for i, (diff_type, text) in enumerate(diffs):
        part_type = 'unchanged'
        if diff_type == -1:
            part_type = 'removed'
        elif diff_type == 1:
            part_type = 'added'

        redlined_text.append(RedlinedPart(id=i, text=text, type=part_type))

    return RedlinedResponse(redlinedText=redlined_text)


@app.post("/api/set-reminder")
async def set_reminder(reminder: ReminderRequest):
    try:
        message = MessageSchema(
            subject="Contract Expiry Reminder",
            recipients=[reminder.email],
            body=f"Reminder: Your contract '{reminder.contractName}' will expire in {reminder.daysUntilExpiry} days.",
            subtype="plain"
        )
        
        fm = FastMail(mail_config)
        await fm.send_message(message)
        return {"message": "Reminder set successfully"}
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to send reminder: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)