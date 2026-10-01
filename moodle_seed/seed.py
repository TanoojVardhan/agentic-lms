"""
Seeds a local Moodle instance with fake data for development/testing.

What this DOES automate (via Moodle's standard REST web services):
  1. Create one course
  2. Create 10 fake student accounts (from fake_students.csv)
  3. Enrol those students into the course

What this does NOT automate (Moodle's default web services don't support
writing these reliably — see CLAUDE.md's "write-back gap" note):
  - Adding page/content resources to the course
  - Creating a quiz with questions
  - Generating fake quiz attempts / grades
  These need to be done once, manually, in the Moodle UI (steps printed
  at the end of this script).

Requirements before running:
  1. Moodle running (docker compose up -d) at MOODLE_BASE_URL
  2. Web services + REST protocol enabled in Moodle admin
  3. A web service token with these functions enabled:
     - core_course_create_courses
     - core_user_create_users
     - enrol_manual_enrol_users
     - core_course_get_courses (used to fetch the new course's id reliably)
  4. MOODLE_WS_TOKEN set in your .env

Run with:  python moodle_seed/seed.py
"""
import csv
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MOODLE_BASE_URL = os.getenv("MOODLE_BASE_URL", "http://localhost:8080")
MOODLE_WS_TOKEN = os.getenv("MOODLE_WS_TOKEN", "")
REST_ENDPOINT = f"{MOODLE_BASE_URL.rstrip('/')}/webservice/rest/server.php"

COURSE_FULLNAME = "Intro to Data Structures (Seed Course)"
COURSE_SHORTNAME = "DS101-SEED"
COURSE_CATEGORY_ID = 1  # default "Miscellaneous" category

STUDENT_ROLE_ID = 5  # Moodle's standard "Student" role id


def call(wsfunction: str, **params) -> dict | list:
    if not MOODLE_WS_TOKEN or MOODLE_WS_TOKEN == "replace_with_generated_token":
        sys.exit(
            "MOODLE_WS_TOKEN is not set in .env. Generate one in Moodle admin "
            "(Site administration > Server > Web services > Manage tokens) "
            "and put it in .env first."
        )
    query = {
        "wstoken": MOODLE_WS_TOKEN,
        "wsfunction": wsfunction,
        "moodlewsrestformat": "json",
        **params,
    }
    resp = httpx.post(REST_ENDPOINT, data=query, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get("exception"):
        sys.exit(f"Moodle API error on {wsfunction}: {data.get('message')}")
    return data


def create_course() -> int:
    print(f"Creating course '{COURSE_FULLNAME}'...")
    result = call(
        "core_course_create_courses",
        **{
            "courses[0][fullname]": COURSE_FULLNAME,
            "courses[0][shortname]": COURSE_SHORTNAME,
            "courses[0][categoryid]": COURSE_CATEGORY_ID,
        },
    )
    course_id = result[0]["id"]
    print(f"  -> course id {course_id}")
    return course_id


def load_students_csv() -> list[dict]:
    csv_path = Path(__file__).resolve().parent / "fake_students.csv"
    with open(csv_path, newline="") as f:
        return list(csv.DictReader(f))


def create_students(students: list[dict]) -> list[int]:
    print(f"Creating {len(students)} fake student accounts...")
    params = {}
    for i, s in enumerate(students):
        params[f"users[{i}][username]"] = s["username"]
        params[f"users[{i}][password]"] = s["password"]
        params[f"users[{i}][firstname]"] = s["firstname"]
        params[f"users[{i}][lastname]"] = s["lastname"]
        params[f"users[{i}][email]"] = s["email"]
    result = call("core_user_create_users", **params)
    user_ids = [u["id"] for u in result]
    print(f"  -> created user ids: {user_ids}")
    return user_ids


def enrol_students(course_id: int, user_ids: list[int]):
    print(f"Enrolling {len(user_ids)} students into course {course_id}...")
    params = {}
    for i, uid in enumerate(user_ids):
        params[f"enrolments[{i}][roleid]"] = STUDENT_ROLE_ID
        params[f"enrolments[{i}][userid]"] = uid
        params[f"enrolments[{i}][courseid]"] = course_id
    call("enrol_manual_enrol_users", **params)
    print("  -> enrolled")


def main():
    students = load_students_csv()
    course_id = create_course()
    user_ids = create_students(students)
    enrol_students(course_id, user_ids)

    print("\nDone with the automated part. Two manual steps remain in the Moodle UI:")
    print(f"  1. Open course '{COURSE_FULLNAME}' (id {course_id}) and add a couple of")
    print("     Page resources with syllabus-style text, for the Tutor Agent's RAG.")
    print("  2. Add a Quiz with a few questions, then log in as a couple of the fake")
    print("     students (passwords in fake_students.csv) and submit varied answers")
    print("     — some good, some poor — so the Mentor Agent has real gaps to detect.")


if __name__ == "__main__":
    main()
