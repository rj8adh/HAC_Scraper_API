import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_URL = "https://accesscenter.roundrockisd.org/"
LOGIN_URL = BASE_URL + "HomeAccess/Account/LogOn?ReturnUrl=%2fhomeaccess"

class LoginRequest(BaseModel):
    username: str
    password: str

def login(session, username, password):
    res = session.get(LOGIN_URL)
    soup = BeautifulSoup(res.content, "html.parser")
    token_tag = soup.find("input", {"name": "__RequestVerificationToken"})
    if not token_tag:
        return False
    
    csrf_token = token_tag.get("value", "")

    payload = {
        "__RequestVerificationToken": csrf_token,
        "Type": "Normal",
        "LocalLogin": "False",
        "SiteCode": "",
        "SCKTY00328510CustomEnabled": "False",
        "SCKTY00436568CustomEnabled": "False",
        "Database": "10",
        "VerificationOption": "UsernamePassword",
        "LogOnDetails.UserName": username,
        "tempUN": "",
        "tempPW": "",
        "LogOnDetails.Password": password,
    }
    
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://accesscenter.roundrockisd.org",
        "Referer": LOGIN_URL,
    })
    
    session.post(LOGIN_URL, data=payload)
    
    check = session.get(BASE_URL + "HomeAccess/Home/Home")
    return "Home View" in check.text or "Summary" in check.text

def parse_courses(session):
    res = session.get(BASE_URL + "HomeAccess/Home/WeekView")
    soup = BeautifulSoup(res.content, "html.parser")
    courses = []
    
    tbody = soup.find("tbody")
    if not tbody:
        return courses

    for row in tbody.find_all("tr"):
        name_tag = row.find("a", attrs={"id": lambda x: x and x.startswith("courseName-")})
        grade_tag = row.find("a", attrs={"id": "average"})
        if name_tag and grade_tag:
            courses.append({
                "name": name_tag.get_text(strip=True),
                "grade": grade_tag.get_text(strip=True)
            })
    return courses

def parse_gpa(session):
    res = session.get(BASE_URL + "HomeAccess/Content/Student/Transcript.aspx")
    soup = BeautifulSoup(res.content, "html.parser")
    table = soup.find("table", attrs={"id": "plnMain_rpTranscriptGroup_tblCumGPAInfo"})
    if not table:
        return {"gpa": "N/A", "rank": "N/A"}

    row = table.find("tr", attrs={"class": "sg-asp-table-data-row"})
    if not row:
        return {"gpa": "N/A", "rank": "N/A"}

    cols = row.find_all("td")
    return {
        "gpa": cols[1].get_text(strip=True) if len(cols) > 1 else "N/A",
        "rank": cols[2].get_text(strip=True) if len(cols) > 2 else "N/A"
    }

def parse_assignments(session):
    res = session.get(BASE_URL + "HomeAccess/Content/Student/Assignments.aspx")
    soup = BeautifulSoup(res.content, "html.parser")
    assignments = []

    tables = soup.select('table[id^="plnMain_rptAssigmnetsByCourse_dgCourseAssignments_"]')
    for table in tables:
        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")
            if len(cols) >= 8:
                assignments.append({
                    "name": cols[2].get_text(strip=True).replace("\r", "").replace("\n", "").replace("*", ""),
                    "score": cols[4].get_text(strip=True),
                    "total": cols[7].get_text(strip=True),
                })
    return assignments

@app.post("/api/hac")
def get_hac_data(creds: LoginRequest):
    session = requests.Session()
    
    if not login(session, creds.username, creds.password):
        return {"error": "Invalid credentials or login failed"}

    return {
        "courses": parse_courses(session),
        "gpa_info": parse_gpa(session),
        "assignments": parse_assignments(session)
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
