"""
Generates fake_students.csv: 1000 students across 20 sections of 50 each.

Roll number scheme (as specified):
  25<section><position>  where section = 1,2,3...20 and position = 01..50
  e.g. Section 1:  25101 - 25150
       Section 2:  25201 - 25250
       ...
       Section 20: 252001 - 252050   (section becomes 2 digits once >= 10)

This is a generator script, not hand-maintained data — rerun it if you need
to change student count, section size, or the name pools below.
"""
import csv
import random
from pathlib import Path

SECTIONS = 20
STUDENTS_PER_SECTION = 50
PASSWORD = "Student@123"

FIRST_NAMES = [
    "Aarav", "Diya", "Vihaan", "Ananya", "Kabir", "Myra", "Aryan", "Saanvi",
    "Reyansh", "Ira", "Vivaan", "Aadhya", "Arjun", "Kiara", "Sai", "Riya",
    "Ishaan", "Avni", "Rohan", "Prisha", "Dhruv", "Anika", "Kian", "Navya",
    "Yash", "Siya", "Atharv", "Pari", "Krish", "Zara", "Advik", "Mishka",
    "Shaurya", "Aarohi", "Vedant", "Kyra", "Aditya", "Sara", "Rudra", "Tara",
]
LAST_NAMES = [
    "Sharma", "Patel", "Reddy", "Nair", "Iyer", "Joshi", "Menon", "Gupta",
    "Rao", "Kulkarni", "Singh", "Verma", "Mehta", "Desai", "Agarwal",
    "Kapoor", "Malhotra", "Chawla", "Bhatt", "Pillai", "Shetty", "Naidu",
    "Chatterjee", "Banerjee", "Mukherjee", "Das", "Ghosh", "Pandey", "Mishra",
    "Trivedi",
]


def gen_rows():
    rng = random.Random(42)  # fixed seed so the roster is reproducible
    rows = []
    for section in range(1, SECTIONS + 1):
        for pos in range(1, STUDENTS_PER_SECTION + 1):
            roll = f"25{section}{pos:02d}"
            first = rng.choice(FIRST_NAMES)
            last = rng.choice(LAST_NAMES)
            rows.append(
                {
                    "username": roll,
                    "password": PASSWORD,
                    "firstname": first,
                    "lastname": f"{last}",
                    "email": f"{roll}@test.local",
                    "section": f"Section {chr(64 + section)}" if section <= 26 else f"Section {section}",
                }
            )
    return rows


def main():
    rows = gen_rows()
    out_path = Path(__file__).resolve().parent / "fake_students.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["username", "password", "firstname", "lastname", "email", "section"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} students to {out_path}")


if __name__ == "__main__":
    main()
