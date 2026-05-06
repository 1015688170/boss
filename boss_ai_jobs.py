#!/usr/bin/env python3
"""
Fetch and analyze AI-related job listings from Boss Zhipin search APIs.

This script intentionally does not bypass login, CAPTCHA, rate limits, or
anti-bot protections. Use your own authenticated browser headers/cookies and
keep requests slow.
"""

from __future__ import annotations

import argparse
import csv
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
    "人工智能",
    "大模型",
    "LLM",
    "AIGC",
    "机器学习",
    "深度学习",
    "NLP",
    "算法工程师",
]

TECH_WORDS = [
    "python",
    "pytorch",
    "tensorflow",
    "transformers",
    "langchain",
    "llamaindex",
    "rag",
    "llm",
    "aigc",
    "agent",
    "nlp",
    "cv",
    "ocr",
    "推荐",
    "搜索",
    "机器学习",
    "深度学习",
    "大模型",
    "多模态",
    "向量数据库",
    "faiss",
    "milvus",
    "elasticsearch",
    "spark",
    "flink",
    "hadoop",
    "sql",
    "java",
    "go",
    "c++",
    "cuda",
    "kubernetes",
    "docker",
]


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
    parser.add_argument("--search-url", default=DEFAULT_SEARCH_URL, help="Search API URL.")
    parser.add_argument(
        "--detail-api-url",
        help="Optional detail API URL template, e.g. https://.../detail?jobId={encryptJobId}",
    )
    parser.add_argument("--headers", help="Path to a JSON file containing request headers.")
    parser.add_argument("--cookie", help="Cookie string. If omitted, reads BOSS_COOKIE env var.")
    parser.add_argument("--delay-min", type=float, default=2.5, help="Minimum delay between requests.")
    parser.add_argument("--delay-max", type=float, default=6.0, help="Maximum delay between requests.")
    parser.add_argument("--analyze", action="store_true", help="Print salary and tech similarity analysis after fetch.")
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
    job_list = zp_data.get("jobList") or zp_data.get("jobs") or []
    if not isinstance(job_list, list):
        return []
    return [item for item in job_list if isinstance(item, dict)]


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


def normalize_job(item: dict[str, Any], keyword: str, city: str, page: int) -> Job:
    encrypt_job_id = pick(item, "encryptJobId", "jobId", "lid")
    detail_url = pick(item, "detailUrl")
    if not detail_url and encrypt_job_id:
        detail_url = f"https://www.zhipin.com/job_detail/{encrypt_job_id}.html"

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
            for x in [
                pick(item, "cityName"),
                pick(item, "areaDistrict"),
                pick(item, "businessDistrict"),
            ]
            if x
        ),
        experience=pick(item, "jobExperience", "experienceName"),
        degree=pick(item, "jobDegree", "degreeName"),
        skills=pick(item, "skills", "jobLabels", "postDescription"),
        welfare=pick(item, "welfareList", "jobBenefits"),
        description=pick(item, "postDescription", "description", "jobDescription"),
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
    params = {
        "query": keyword,
        "city": city,
        "page": page,
        "pageSize": page_size,
    }
    url = f"{search_url}?{urlencode(params)}"
    resp = session.get(url, headers=headers, timeout=20)
    if resp.status_code in {401, 403, 429}:
        raise RuntimeError(f"Blocked or unauthenticated: HTTP {resp.status_code}. Refresh Cookie/headers and slow down.")
    resp.raise_for_status()
    return resp.json()


def find_description(value: Any) -> str:
    if isinstance(value, dict):
        for key in ["postDescription", "jobDescription", "description", "jobDesc", "content"]:
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
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
    url = detail_api_url.format(
        encryptJobId=job.encrypt_job_id,
        jobId=job.encrypt_job_id,
        lid=job.encrypt_job_id,
    )
    resp = session.get(url, headers=headers, timeout=20)
    if resp.status_code in {401, 403, 429}:
        raise RuntimeError(f"Detail blocked or unauthenticated: HTTP {resp.status_code}.")
    resp.raise_for_status()
    return resp.json()


def write_outputs(jobs: list[Job], csv_path: Path, jsonl_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)

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


def salary_midpoint(salary: str) -> float | None:
    numbers = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", salary)]
    if not numbers:
        return None
    if len(numbers) >= 2:
        base = (numbers[0] + numbers[1]) / 2
    else:
        base = numbers[0]
    months_match = re.search(r"(\d+)\s*薪", salary)
    months = int(months_match.group(1)) if months_match else 12
    return base * months / 12


def tokenize_tech(text: str) -> set[str]:
    lowered = text.lower()
    return {word for word in TECH_WORDS if word.lower() in lowered}


def analyze(jobs: list[Job]) -> None:
    salaries = [(job, salary_midpoint(job.salary)) for job in jobs]
    salary_values = sorted(v for _, v in salaries if v is not None)
    print(f"岗位数: {len(jobs)}")
    if salary_values:
        mid = salary_values[len(salary_values) // 2]
        avg = sum(salary_values) / len(salary_values)
        print(f"月薪中位数估算: {mid:.1f}K，平均估算: {avg:.1f}K")

    tech_counter: Counter[str] = Counter()
    buckets: dict[frozenset[str], list[Job]] = defaultdict(list)
    for job in jobs:
        techs = tokenize_tech(" ".join([job.job_name, job.skills, job.description, json.dumps(job.raw, ensure_ascii=False)]))
        tech_counter.update(techs)
        if techs:
            buckets[frozenset(techs)].append(job)

    print("高频技术词:")
    for word, count in tech_counter.most_common(20):
        print(f"- {word}: {count}")

    print("技术相似岗位组:")
    grouped = sorted(buckets.items(), key=lambda x: len(x[1]), reverse=True)
    for techs, group in grouped[:10]:
        names = "；".join(f"{job.company}/{job.job_name}/{job.salary}" for job in group[:3])
        print(f"- {', '.join(sorted(techs))}: {len(group)} 个；{names}")


def main() -> int:
    args = parse_args()
    keywords = args.keyword or DEFAULT_KEYWORDS
    headers = load_headers(args.headers, args.cookie)
    if "cookie" not in headers:
        print("缺少 Cookie：请用 --cookie 或 BOSS_COOKIE 提供你自己的登录 Cookie。", file=sys.stderr)
        return 2

    jobs: list[Job] = []
    session = requests.Session()
    seen_ids: set[str] = set()

    for keyword in keywords:
        for page in range(1, args.pages + 1):
            payload = fetch_page(
                session=session,
                search_url=args.search_url,
                headers=headers,
                keyword=keyword,
                city=args.city,
                page=page,
                page_size=args.page_size,
            )
            items = extract_jobs(payload)
            print(f"{keyword} page {page}: {len(items)} jobs")
            if not items:
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
                        job.description = find_description(detail_payload) or job.description
                    time.sleep(random.uniform(args.delay_min, args.delay_max))
                seen_ids.add(dedupe_key)
                jobs.append(job)

            time.sleep(random.uniform(args.delay_min, args.delay_max))

    write_outputs(jobs, Path(args.out), Path(args.jsonl))
    print(f"已保存: {args.out}, {args.jsonl}")
    if args.analyze:
        analyze(jobs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
