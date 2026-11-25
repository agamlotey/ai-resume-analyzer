from __future__ import annotations

import io
import math
import re
from collections import Counter
from datetime import date

from skills import SKILLS, skill_category

STOPWORDS = set("""
a about above after again against all am an and any are as at be because been before being below between both but by
can could did do does doing down during each few for from further had has have having he her here hers herself him
himself his how i if in into is it its itself just me more most my myself no nor not now of off on once only or other
our ours ourselves out over own same she should so some such than that the their theirs them themselves then there
these they this those through to too under until up very was we were what when where which while who whom why will
with would you your yours yourself yourselves also etc using use used work working experience team role job candidate
candidates looking strong good ability able must required preferred plus years year knowledge skills skill including
responsibilities requirements will join company we're you'll
""".split())

SECTION_HEADERS = {
    "summary": ["summary", "profile", "objective", "about me", "professional summary", "career objective"],
    "experience": ["experience", "work experience", "professional experience", "employment", "employment history",
                   "internships", "internship", "work history"],
    "education": ["education", "academic background", "academics", "qualifications", "education details"],
    "skills": ["skills", "technical skills", "key skills", "core competencies", "technologies", "tech stack"],
    "projects": ["projects", "academic projects", "personal projects", "key projects"],
    "certifications": ["certifications", "certificates", "courses", "licenses & certifications"],
    "achievements": ["achievements", "awards", "honors", "accomplishments", "extracurricular", "positions of responsibility"],
}

DEGREES = [
    (4, "PhD", r"\bph\.?\s?d\b|\bdoctorate\b"),
    (3, "Master's", r"\bmaster'?s?\b|\bm\.?\s?tech\b|\bm\.?\s?sc\b|\bmba\b|\bm\.?\s?e\b\.|\bmca\b|\bm\.s\.\b"),
    (2, "Bachelor's", r"\bbachelor'?s?\b|\bb\.?\s?tech\b|\bb\.?\s?e\b\.|\bb\.?\s?sc\b|\bbca\b|\bb\.s\.\b|\bundergraduate\b|\bbe\s+in\b"),
    (1, "Diploma", r"\bdiploma\b"),
]

ACTION_VERBS = ["built", "developed", "designed", "led", "implemented", "created", "improved", "optimized", "deployed",
                "automated", "reduced", "increased", "launched", "managed", "analyzed", "engineered", "architected"]

_SKILL_PATTERNS = []
for _category, _skills in SKILLS.items():
    for _name, _aliases in _skills.items():
        for _alias in _aliases:
            pattern = r"(?<![a-z0-9+#])" + re.escape(_alias) + r"(?![a-z0-9+#])"
            _SKILL_PATTERNS.append((_name, re.compile(pattern)))


def extract_text(filename, data):
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if name.endswith(".docx"):
        import docx
        document = docx.Document(io.BytesIO(data))
        lines = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                lines.append(" | ".join(cell.text for cell in row.cells))
        return "\n".join(lines)
    if name.endswith(".txt"):
        return data.decode("utf-8", errors="ignore")
    raise ValueError("Unsupported file type. Please upload a PDF, DOCX or TXT file.")


def normalize(text):
    text = text.lower().replace("–", "-").replace("—", "-").replace("’", "'")
    return re.sub(r"[ \t\r\f\v]+", " ", text)


def find_skills(text):
    text = normalize(text)
    counts = Counter()
    for name, pattern in _SKILL_PATTERNS:
        hits = len(pattern.findall(text))
        if hits:
            counts[name] += hits
    return counts


def split_sections(text):
    sections = {"header": []}
    current = "header"
    for raw in text.splitlines():
        line = raw.strip()
        key = re.sub(r"[^a-z& ]", "", line.lower()).strip()
        found = None
        if 0 < len(key) <= 40:
            for section, names in SECTION_HEADERS.items():
                if key in names:
                    found = section
                    break
        if found:
            current = found
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


def explicit_years(text):
    values = re.findall(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years?|yrs?)", normalize(text))
    return [float(v) for v in values if float(v) <= 40]


MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_MONTH = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_RANGE = re.compile(r"(?:" + _MONTH + r"\s+)?((?:19|20)\d{2})\s*(?:-|to)\s*(?:" + _MONTH
                    + r"\s+)?((?:19|20)\d{2}|present|current|now|till date|ongoing)")


def years_from_ranges(text):
    today = date.today()
    total_months = 0
    for m1, y1, m2, y2 in _RANGE.findall(normalize(text)):
        start = int(y1) * 12 + (MONTHS[m1[:3]] if m1 else 1)
        if y2[0].isdigit():
            end = int(y2) * 12 + (MONTHS[m2[:3]] if m2 else 1)
        else:
            end = today.year * 12 + today.month
        months = end - start + (1 if m1 and m2 else 0)
        if 0 < months <= 480:
            total_months += months
    return total_months / 12


def resume_years(text, sections):
    mentioned = explicit_years(sections.get("summary", "") + "\n" + sections.get("header", ""))
    from_ranges = years_from_ranges(sections.get("experience", ""))
    return round(max(max(mentioned) if mentioned else 0, from_ranges), 1)


def jd_years(text):
    values = explicit_years(text)
    return min(values) if values else 0


def education_level(text):
    low = normalize(text)
    for level, label, pattern in DEGREES:
        if re.search(pattern, low):
            return level, label
    return 0, None


def contact_info(text):
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    phone = re.search(r"(?:\+?\d{1,3}[\s-]?)?\d{5}[\s-]?\d{5}|\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}", text)
    links = re.findall(r"(?:https?://)?(?:www\.)?(?:linkedin\.com|github\.com)/[\w\-/]+", text, re.I)
    name = None
    for line in text.splitlines():
        line = line.strip()
        if line and "@" not in line and len(line.split()) <= 4 and not re.search(r"\d", line):
            name = line.title() if line.isupper() else line
            break
    return {
        "name": name,
        "email": email.group(0) if email else None,
        "phone": phone.group(0).strip() if phone else None,
        "links": sorted(set(links)),
    }


def tokens(text):
    words = re.findall(r"[a-z][a-z0-9+#.]*[a-z0-9+#]|[a-z]", normalize(text))
    result = []
    for w in words:
        if w in STOPWORDS or len(w) < 2:
            continue
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        result.append(w)
    return result


def cosine_similarity(a, b):
    va, vb = Counter(tokens(a)), Counter(tokens(b))
    common = set(va) & set(vb)
    dot = sum(va[t] * vb[t] for t in common)
    norm = math.sqrt(sum(v * v for v in va.values())) * math.sqrt(sum(v * v for v in vb.values()))
    return dot / norm if norm else 0.0


def top_keywords(text, n=12):
    skill_words = set()
    for skills in SKILLS.values():
        for aliases in skills.values():
            for alias in aliases:
                skill_words.update(alias.split())
    counts = Counter(t for t in tokens(text) if t not in skill_words and len(t) > 3)
    return [w for w, _ in counts.most_common(n)]


def parse_resume(text):
    sections = split_sections(text)
    skills = find_skills(text)
    level, degree = education_level(sections.get("education") or text)
    return {
        "contact": contact_info(text),
        "skills": sorted(skills),
        "skill_counts": dict(skills),
        "years_experience": resume_years(text, sections),
        "education_level": level,
        "degree": degree,
        "sections_found": sorted(k for k, v in sections.items() if k != "header" and v),
        "word_count": len(text.split()),
    }


def parse_jd(text):
    skills = find_skills(text)
    level, degree = education_level(text)
    return {
        "skills": sorted(skills),
        "skill_counts": dict(skills),
        "years_required": jd_years(text),
        "education_level": level,
        "degree": degree,
    }


def grade(score):
    if score >= 80:
        return "Strong match"
    if score >= 60:
        return "Good match"
    if score >= 40:
        return "Partial match"
    return "Weak match"


def build_suggestions(resume, jd, missing, weak, text, keyword_gaps):
    tips = []
    if missing:
        top = ", ".join(missing[:6])
        tips.append(f"Add the missing skills the job asks for, if you have them: {top}. Mention each one inside a project or experience bullet, not only in the skills list.")
    if weak:
        tips.append(f"These skills appear only once in your resume but the job stresses them: {', '.join(weak[:5])}. Show them in more depth with a concrete project or result.")
    if jd["years_required"] and resume["years_experience"] < jd["years_required"]:
        tips.append(f"The job asks for about {jd['years_required']:g} years of experience and your resume shows about {resume['years_experience']:g}. Highlight internships, freelance work and long projects with clear dates.")
    if jd["education_level"] and resume["education_level"] < jd["education_level"]:
        tips.append(f"The job mentions a {jd['degree']} degree. Make your education section clear, with the degree name, institute and year.")
    if not re.search(r"\d+\s*%|\d+x\b|\b\d{2,}\b", normalize(text)):
        tips.append("Add numbers to your achievements (for example: reduced load time by 40%, served 2,000 users).")
    verbs = sum(1 for v in ACTION_VERBS if re.search(r"\b" + v + r"\b", normalize(text)))
    if verbs < 3:
        tips.append("Start bullet points with strong action verbs such as built, designed, deployed or optimized.")
    for needed in ("projects", "skills", "experience", "education"):
        if needed not in resume["sections_found"]:
            tips.append(f"Add a clearly titled '{needed.title()}' section so recruiters and ATS software can find it.")
    if resume["word_count"] < 150:
        tips.append("Your resume is quite short. Add more detail about what you built and the impact it had.")
    elif resume["word_count"] > 1100:
        tips.append("Your resume is long. Try to keep it to one or two pages with the most relevant work first.")
    if keyword_gaps:
        tips.append(f"Use some of the job's own wording where it is true for you: {', '.join(keyword_gaps[:6])}.")
    if not tips:
        tips.append("Your resume already covers this job well. Tailor the summary line to the role title before applying.")
    return tips


def match(resume_text, jd_text):
    resume = parse_resume(resume_text)
    jd = parse_jd(jd_text)

    jd_skills = set(jd["skills"])
    resume_skills = set(resume["skills"])
    matched = sorted(jd_skills & resume_skills)
    missing = sorted(jd_skills - resume_skills, key=lambda s: (-jd["skill_counts"][s], s))
    weak = sorted(s for s in matched if resume["skill_counts"][s] == 1 and jd["skill_counts"][s] >= 2)
    extra = sorted(resume_skills - jd_skills)

    similarity = cosine_similarity(resume_text, jd_text)
    text_score = min(1.0, similarity / 0.6)
    skill_score = len(matched) / len(jd_skills) if jd_skills else text_score

    if not jd["years_required"]:
        exp_score = 1.0
    else:
        exp_score = min(1.0, resume["years_experience"] / jd["years_required"])

    if not jd["education_level"] or resume["education_level"] >= jd["education_level"]:
        edu_score = 1.0
    elif resume["education_level"] == jd["education_level"] - 1:
        edu_score = 0.5
    else:
        edu_score = 0.0

    weights = {"skills": 0.55, "text": 0.25, "experience": 0.10, "education": 0.10}
    total = (weights["skills"] * skill_score + weights["text"] * text_score
             + weights["experience"] * exp_score + weights["education"] * edu_score)
    score = round(total * 100, 1)

    resume_stems = {t[:5] for t in tokens(resume_text)}
    keyword_gaps = [k for k in top_keywords(jd_text) if k[:5] not in resume_stems]

    by_category = {}
    for skill in sorted(jd_skills):
        cat = skill_category(skill)
        entry = by_category.setdefault(cat, {"matched": [], "missing": []})
        entry["matched" if skill in resume_skills else "missing"].append(skill)

    return {
        "score": score,
        "verdict": grade(score),
        "breakdown": {
            "skills": round(skill_score * 100, 1),
            "text_similarity": round(text_score * 100, 1),
            "experience": round(exp_score * 100, 1),
            "education": round(edu_score * 100, 1),
        },
        "weights": weights,
        "matched_skills": matched,
        "missing_skills": missing,
        "weak_skills": weak,
        "extra_skills": extra,
        "skills_by_category": by_category,
        "keyword_gaps": keyword_gaps[:10],
        "suggestions": build_suggestions(resume, jd, missing, weak, resume_text, keyword_gaps),
        "resume": resume,
        "job": jd,
    }
