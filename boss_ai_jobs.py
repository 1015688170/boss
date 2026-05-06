#!/usr/bin/env python3
"""
Fetch and analyze AI-related Boss Zhipin job listings.

This script does not bypass login, CAPTCHA, rate limits, or anti-bot checks.
Use your own authenticated browser Cookie/headers and keep requests slow.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests


DEFAULT_SEARCH_URL = "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"
DEFAULT_KEYWORDS = [
    "AI",
    "\u4eba\u5de5\u667a\u80fd",
    "\u5927\u6a21\u578b",
    "LLM",
    "AIGC",
    "\u673a\u5668\u5b66\u4e60",
    "\u6df1\u5ea6\u5b66\u4e60",
    "NLP",
    "\u7b97\u6cd5\u5de5\u7a0b\u5e08",
]

SKILL_PATTERNS: dict[str, list[str]] = {
    "Python": [r"\bpython\b"],
    "Shell": [r"\bshell\b"],
    "Java": [r"\bjava\b"],
    "Go": [r"\bgo\b", r"\bgolang\b"],
    "C++": [r"c\+\+"],
    "SQL": [r"\bsql\b"],
    "Linux": [r"\blinux\b"],
    "Docker": [r"\bdocker\b"],
    "Kubernetes/K8s": [r"\bk8s\b", r"\bkubernetes\b"],
    "PyTorch": [r"\bpytorch\b"],
    "TensorFlow": [r"\btensorflow\b"],
    "Transformers": [r"\btransformers\b"],
    "LangChain": [r"\blangchain\b"],
    "LlamaIndex": [r"\bllamaindex\b"],
    "RAG": [r"\brag\b", r"\u68c0\u7d22\u589e\u5f3a"],
    "LLM": [r"\bllm\b", r"\u5927\u8bed\u8a00\u6a21\u578b"],
    "\u5927\u6a21\u578b": [r"\u5927\u6a21\u578b"],
    "AIGC": [r"\baigc\b"],
    "Agent": [r"\bagent\b", r"\u667a\u80fd\u4f53"],
    "NLP": [r"\bnlp\b", r"\u81ea\u7136\u8bed\u8a00"],
    "CV": [r"\bcv\b", r"\u8ba1\u7b97\u673a\u89c6\u89c9"],
    "OCR": [r"\bocr\b"],
    "\u673a\u5668\u5b66\u4e60": [r"\u673a\u5668\u5b66\u4e60"],
    "\u6df1\u5ea6\u5b66\u4e60": [r"\u6df1\u5ea6\u5b66\u4e60"],
    "\u591a\u6a21\u6001": [r"\u591a\u6a21\u6001"],
    "\u63a8\u8350": [r"\u63a8\u8350"],
    "\u641c\u7d22": [r"\u641c\u7d22"],
    "\u63a8\u7406": [r"\u63a8\u7406", r"inference"],
    "\u8bad\u7ec3": [r"\u8bad\u7ec3", r"training"],
    "\u5fae\u8c03": [r"\u5fae\u8c03", r"fine[- ]?tuning"],
    "\u90e8\u7f72": [r"\u90e8\u7f72"],
    "\u8fd0\u7ef4": [r"\u8fd0\u7ef4", r"devops"],
    "\u5bb9\u5668\u5316": [r"\u5bb9\u5668", r"\u5bb9\u5668\u5316"],
    "\u5411\u91cf\u6570\u636e\u5e93": [r"\u5411\u91cf\u6570\u636e\u5e93", r"\bfaiss\b", r"\bmilvus\b"],
    "Elasticsearch": [r"\belasticsearch\b", r"\bes\b"],
    "Spark": [r"\bspark\b"],
    "Flink": [r"\bflink\b"],
    "Hadoop": [r"\bhadoop\b"],
    "CUDA": [r"\bcuda\b"],
    "Prometheus": [r"\bprometheus\b"],
    "Grafana": [r"\bgrafana\b"],
    "ELK": [r"\belk\b", r"\belasticsearch\b.*\blogstash\b.*\bkibana\b"],
}


@dataclass
class Job:
    keyword: str
    city: str
    page: int
    job_name: str
    salary: str
    company: str
    brand: str
    location: str
    experience: str
    degree: str
    skills: str
    welfare: str
    responsibilities: str
    requirements: str
    description: str
    detail_url: str
    encrypt_job_id: str
    raw: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Boss Zhipin AI job listings with your own browser session."
    )
    parser.add_argument("--keyword", "-k", action="append", help="Search keyword. Can repeat.")
    parser.add_argument("--city", "-c", default="101020100", help="Boss city code, default: Shanghai 101020100.")
    parser.add_argument("--pages", "-p", type=int, default=3, help="Pages per keyword.")
    parser.add_argument("--page-size", type=int, default=30, help="Result page size.")
    parser.add_argument("--out", default="boss_ai_jobs.csv", help="CSV output path.")
    parser.add_argument("--jsonl", default="boss_ai_jobs.jsonl", help="Raw JSONL output path.")
    parser.add_argument("--skill-stats-out", default="boss_skill_stats.csv", help="Skill statistics CSV output path.")
    parser.add_argument("--search-url", default=DEFAULT_SEARCH_URL, help="Search API URL.")
    parser.add_argument(
        "--detail-api-url",
        help="Optional detail API URL template, e.g. https://.../detail?jobId={encryptJobId}",
    )
    parser.add_argument("--headers", help="Path to a JSON file containing request headers.")
    parser.add_argument("--cookie", help="Cookie string. If omitted, reads BOSS_COOKIE env var.")
    parser.add_argument("--delay-min", type=float, default=2.5, help="Minimum delay between requests.")
    parser.add_argument("--delay-max", type=float, default=6.0, help="Maximum delay between requests.")
    parser.add_argument("--analyze", action="store_true", help="Print salary and responsibility skill analysis.")
    parser.add_argument("--debug", action="store_true", help="Print response summary when a page returns no jobs.")
    parser.add_argument("--debug-out", default="boss_debug_response.json", help="Save the first empty response JSON here.")
    return parser.parse_args()


def load_headers(path: str | None, cookie: str | None) -> dict[str, str]:
    headers = {
        "accept": "application/json, text/plain, */*",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "referer": "https://www.zhipin.com/web/geek/job",
    }
    if path:
        with open(path, "r", encoding="utf-8") as f:
            headers.update(json.load(f))

    cookie_value = cookie or os.getenv("BOSS_COOKIE")
    if cookie_value:
        headers["cookie"] = cookie_value
    return headers


def extract_jobs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    zp_data = payload.get("zpData") or payload.get("data") or {}
    job_list = (
        zp_data.get("jobList")
        or zp_data.get("jobs")
        or zp_data.get("list")
        or payload.get("jobList")
        or payload.get("jobs")
        or []
    )
    if not isinstance(job_list, list):
        return []
    return [item for item in job_list if isinstance(item, dict)]


def debug_response(payload: dict[str, Any], path: str) -> None:
    summary = {
        "top_keys": list(payload.keys()),
        "code": payload.get("code"),
        "message": payload.get("message") or payload.get("msg"),
        "zpData_keys": list((payload.get("zpData") or {}).keys()) if isinstance(payload.get("zpData"), dict) else [],
        "data_keys": list((payload.get("data") or {}).keys()) if isinstance(payload.get("data"), dict) else [],
    }
    print("debug response summary:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"debug response saved: {path}")


def pick(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            return " / ".join(str(x) for x in value if x)
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        return str(value)
    return ""


def clean_text(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_description(description: str) -> tuple[str, str]:
    text = clean_text(description)
    responsibility_match = re.search(
        r"(\u5c97\u4f4d\u804c\u8d23|\u804c\u4f4d\u804c\u8d23|\u5de5\u4f5c\u804c\u8d23|\u5de5\u4f5c\u5185\u5bb9)[:：]?",
        text,
    )
    requirement_match = re.search(
        r"(\u4efb\u804c\u8981\u6c42|\u5c97\u4f4d\u8981\u6c42|\u804c\u4f4d\u8981\u6c42|\u4efb\u804c\u8d44\u683c)[:：]?",
        text,
    )

    if responsibility_match and requirement_match and responsibility_match.start() < requirement_match.start():
        responsibilities = text[responsibility_match.end() : requirement_match.start()].strip()
        requirements = text[requirement_match.end() :].strip()
        return responsibilities, requirements
    if responsibility_match:
        return text[responsibility_match.end() :].strip(), ""
    if requirement_match:
        return text[: requirement_match.start()].strip(), text[requirement_match.end() :].strip()
    return text, ""


def normalize_job(item: dict[str, Any], keyword: str, city: str, page: int) -> Job:
    encrypt_job_id = pick(item, "encryptJobId", "jobId", "lid")
    detail_url = pick(item, "detailUrl")
    if not detail_url and encrypt_job_id:
        detail_url = f"https://www.zhipin.com/job_detail/{encrypt_job_id}.html"

    description = clean_text(pick(item, "postDescription", "description", "jobDescription"))
    responsibilities, requirements = split_description(description)
    return Job(
        keyword=keyword,
        city=city,
        page=page,
        job_name=pick(item, "jobName", "jobTitle"),
        salary=pick(item, "salaryDesc", "salary"),
        company=pick(item, "brandName", "companyName"),
        brand=pick(item, "brandName"),
        location=" ".join(
            x
            for x in [pick(item, "cityName"), pick(item, "areaDistrict"), pick(item, "businessDistrict")]
            if x
        ),
        experience=pick(item, "jobExperience", "experienceName"),
        degree=pick(item, "jobDegree", "degreeName"),
        skills=pick(item, "skills", "jobLabels"),
        welfare=pick(item, "welfareList", "jobBenefits"),
        responsibilities=responsibilities,
        requirements=requirements,
        description=description,
        detail_url=detail_url,
        encrypt_job_id=encrypt_job_id,
        raw=item,
    )


def fetch_page(
    session: requests.Session,
    search_url: str,
    headers: dict[str, str],
    keyword: str,
    city: str,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    params = {"query": keyword, "city": city, "page": page, "pageSize": page_size}
    resp = session.get(f"{search_url}?{urlencode(params)}", headers=headers, timeout=20)
    if resp.status_code in {401, 403, 429}:
        raise RuntimeError(f"Blocked or unauthenticated: HTTP {resp.status_code}. Refresh Cookie/headers and slow down.")
    resp.raise_for_status()
    return resp.json()


def find_description(value: Any) -> str:
    if isinstance(value, dict):
        for key in ["postDescription", "jobDescription", "description", "jobDesc", "content"]:
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return clean_text(item)
        for item in value.values():
            found = find_description(item)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = find_description(item)
            if found:
                return found
    return ""


def fetch_detail(
    session: requests.Session,
    detail_api_url: str,
    headers: dict[str, str],
    job: Job,
) -> dict[str, Any] | None:
    if not job.encrypt_job_id:
        return None
    url = detail_api_url.format(encryptJobId=job.encrypt_job_id, jobId=job.encrypt_job_id, lid=job.encrypt_job_id)
    resp = session.get(url, headers=headers, timeout=20)
    if resp.status_code in {401, 403, 429}:
        raise RuntimeError(f"Detail blocked or unauthenticated: HTTP {resp.status_code}.")
    resp.raise_for_status()
    return resp.json()


def salary_midpoint(salary: str) -> float | None:
    numbers = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", salary)]
    if not numbers:
        return None
    base = (numbers[0] + numbers[1]) / 2 if len(numbers) >= 2 else numbers[0]
    months_match = re.search(r"(\d+)\s*\u85aa", salary)
    months = int(months_match.group(1)) if months_match else 12
    return base * months / 12


def match_skills(text: str) -> set[str]:
    matched: set[str] = set()
    for skill, patterns in SKILL_PATTERNS.items():
        if any(re.search(pattern, text, flags=re.I) for pattern in patterns):
            matched.add(skill)
    return matched


def build_skill_stats(jobs: list[Job]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    total = len(jobs)
    for job in jobs:
        source = "\n".join([job.responsibilities, job.requirements, job.description, job.skills])
        for skill in match_skills(source):
            counter[skill] += 1
            if len(examples[skill]) < 3:
                examples[skill].append(f"{job.company}/{job.job_name}/{job.salary}")

    rows: list[dict[str, Any]] = []
    for skill, count in counter.most_common():
        rows.append(
            {
                "skill": skill,
                "job_count": count,
                "job_percent": f"{count / total * 100:.1f}%" if total else "0.0%",
                "examples": " | ".join(examples[skill]),
            }
        )
    return rows


def write_outputs(jobs: list[Job], csv_path: Path, jsonl_path: Path, skill_stats_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    skill_stats_path.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "keyword",
        "city",
        "page",
        "job_name",
        "salary",
        "company",
        "brand",
        "location",
        "experience",
        "degree",
        "skills",
        "welfare",
        "responsibilities",
        "requirements",
        "description",
        "detail_url",
        "encrypt_job_id",
    ]
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for job in jobs:
            writer.writerow({field: getattr(job, field) for field in fields})

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for job in jobs:
            f.write(json.dumps(job.raw, ensure_ascii=False) + "\n")

    with open(skill_stats_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["skill", "job_count", "job_percent", "examples"])
        writer.writeheader()
        writer.writerows(build_skill_stats(jobs))


def analyze(jobs: list[Job]) -> None:
    salary_values = sorted(v for _, v in [(job, salary_midpoint(job.salary)) for job in jobs] if v is not None)
    print(f"\u5c97\u4f4d\u6570: {len(jobs)}")
    if salary_values:
        mid = salary_values[len(salary_values) // 2]
        avg = sum(salary_values) / len(salary_values)
        print(f"\u6708\u85aa\u4e2d\u4f4d\u6570\u4f30\u7b97: {mid:.1f}K\uff0c\u5e73\u5747\u4f30\u7b97: {avg:.1f}K")

    print("\u5c97\u4f4d\u804c\u8d23/\u8981\u6c42\u91cd\u590d\u6280\u80fd\u70b9:")
    for row in build_skill_stats(jobs)[:30]:
        print(f"- {row['skill']}: {row['job_count']} \u4e2a\u5c97\u4f4d\uff0c{row['job_percent']}")

    buckets: dict[frozenset[str], list[Job]] = defaultdict(list)
    for job in jobs:
        skills = match_skills("\n".join([job.responsibilities, job.requirements, job.description, job.skills]))
        if skills:
            buckets[frozenset(skills)].append(job)

    print("\u6280\u672f\u76f8\u4f3c\u5c97\u4f4d\u7ec4:")
    for skills, group in sorted(buckets.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
        names = "；".join(f"{job.company}/{job.job_name}/{job.salary}" for job in group[:3])
        print(f"- {', '.join(sorted(skills))}: {len(group)} \u4e2a\uff1b{names}")


def main() -> int:
    args = parse_args()
    keywords = args.keyword or DEFAULT_KEYWORDS
    headers = load_headers(args.headers, args.cookie)
    if "cookie" not in headers:
        print("\u7f3a\u5c11 Cookie\uff1a\u8bf7\u7528 --cookie \u6216 BOSS_COOKIE \u63d0\u4f9b\u4f60\u81ea\u5df1\u7684\u767b\u5f55 Cookie\u3002", file=sys.stderr)
        return 2

    jobs: list[Job] = []
    session = requests.Session()
    seen_ids: set[str] = set()

    for keyword in keywords:
        for page in range(1, args.pages + 1):
            payload = fetch_page(session, args.search_url, headers, keyword, args.city, page, args.page_size)
            items = extract_jobs(payload)
            print(f"{keyword} page {page}: {len(items)} jobs")
            if not items:
                if args.debug:
                    debug_response(payload, args.debug_out)
                break

            for item in items:
                job = normalize_job(item, keyword, args.city, page)
                dedupe_key = job.encrypt_job_id or f"{job.company}|{job.job_name}|{job.salary}|{job.location}"
                if dedupe_key in seen_ids:
                    continue

                if args.detail_api_url:
                    detail_payload = fetch_detail(session, args.detail_api_url, headers, job)
                    if detail_payload:
                        job.raw["detailPayload"] = detail_payload
                        detail_text = find_description(detail_payload)
                        if detail_text:
                            job.description = detail_text
                            job.responsibilities, job.requirements = split_description(detail_text)
                    time.sleep(random.uniform(args.delay_min, args.delay_max))

                seen_ids.add(dedupe_key)
                jobs.append(job)

            time.sleep(random.uniform(args.delay_min, args.delay_max))

    write_outputs(jobs, Path(args.out), Path(args.jsonl), Path(args.skill_stats_out))
    print(f"\u5df2\u4fdd\u5b58: {args.out}, {args.jsonl}, {args.skill_stats_out}")
    if args.analyze:
        analyze(jobs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
