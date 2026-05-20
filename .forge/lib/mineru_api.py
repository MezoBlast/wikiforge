#!/usr/bin/env python3
"""Convert PDF to markdown via MinerU API (agent or precision).

Agent API (no token): 10MB / 20 pages, free, markdown only.
Precision API (MINERU_API_TOKEN): 200MB / 200 pages, markdown + JSON in zip.
Set MINERU_API_TOKEN in the environment to use the precision API automatically.

Output is a directory containing the markdown file and extracted images.
"""

import sys
import time
import os
import json
import argparse
import shutil
import subprocess
import zipfile
import tempfile
from urllib.request import Request, urlopen

AGENT_API = "https://mineru.net/api/v1/agent"
PRECISION_API = "https://mineru.net/api/v4"
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "mineru-api-token.json")


def get_mineru_token():
    token = os.environ.get("MINERU_API_TOKEN")
    if token:
        return token
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
        return json.load(f).get("token")


def api_request(method, url, body=None, headers=None):
    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with urlopen(req) as resp:
        return json.loads(resp.read())


def download_and_extract_zip(zip_url, output_dir, base_name):
    """Download a result zip and extract markdown + images into output_dir."""
    print("Downloading result zip...", file=sys.stderr)
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "result.zip")
        r = subprocess.run(["curl", "-sL", "-o", zip_path, zip_url],
                           capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            print("Download failed", file=sys.stderr)
            sys.exit(1)

        extract_dir = os.path.join(tmpdir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_dir)

        # Find markdown file — prefer one matching the filename
        md_files = []
        for root, _dirs, files in os.walk(extract_dir):
            for f in files:
                if f.endswith('.md'):
                    md_files.append(os.path.join(root, f))

        if not md_files:
            print("No markdown file found in result zip. Contents:", file=sys.stderr)
            for root, _dirs, files in os.walk(extract_dir):
                for f in files:
                    print(f"  {os.path.relpath(os.path.join(root, f), extract_dir)}", file=sys.stderr)
            sys.exit(1)

        # Pick best matching .md file
        md_path = md_files[0]
        for p in md_files:
            if base_name in os.path.basename(p):
                md_path = p
                break

        # Find images directory
        images_dir = None
        for root, dirs, _files in os.walk(extract_dir):
            for d in dirs:
                if d == "images":
                    images_dir = os.path.join(root, d)
                    break
            if images_dir:
                break

        # Create output directory
        os.makedirs(output_dir, exist_ok=True)

        # Copy markdown to output_dir/<base_name>.md
        md_out = os.path.join(output_dir, base_name + ".md")
        shutil.copy2(md_path, md_out)
        print(f"Saved markdown to {md_out}")

        # Copy images directory if present
        if images_dir:
            dest_images = os.path.join(output_dir, "images")
            if os.path.exists(dest_images):
                shutil.rmtree(dest_images)
            shutil.copytree(images_dir, dest_images)
            img_count = len(os.listdir(dest_images))
            print(f"Saved {img_count} images to {dest_images}")
        else:
            print("No images directory in result zip.", file=sys.stderr)

        return md_out


def agent_parse(filepath, filename, language, is_ocr, output_dir, base_name):
    """Parse via the free Agent API (no token)."""
    filesize_mb = os.path.getsize(filepath) / (1024 * 1024)
    if filesize_mb > 10:
        print(f"File too large ({filesize_mb:.1f}MB > 10MB). Set MINERU_API_TOKEN for precision API.", file=sys.stderr)
        sys.exit(1)

    print(f"Requesting upload URL for {filename} ({filesize_mb:.1f}MB)...", file=sys.stderr)
    data = api_request("POST", f"{AGENT_API}/parse/file", {
        "file_name": filename,
        "language": language,
        "is_ocr": is_ocr,
    })
    result = data.get("data", data)
    task_id = result["task_id"]
    file_url = result["file_url"]

    print("Uploading file...", file=sys.stderr)
    r = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-X", "PUT", "-T", filepath, file_url],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0 or r.stdout.strip() != "200":
        print(f"Upload failed: HTTP {r.stdout.strip()}", file=sys.stderr)
        sys.exit(1)

    print("Parsing...", file=sys.stderr)
    while True:
        time.sleep(3)
        data = api_request("GET", f"{AGENT_API}/parse/{task_id}")
        state_data = data.get("data", data)
        state = state_data.get("state", "")
        if state == "done":
            # Prefer zip (includes images) over bare markdown URL
            zip_url = state_data.get("full_zip_url") or state_data.get("zip_url")
            if zip_url:
                download_and_extract_zip(zip_url, output_dir, base_name)
                return
            md_url = state_data.get("markdown_url")
            if md_url:
                print("Downloading markdown...", file=sys.stderr)
                r = subprocess.run(["curl", "-sL", md_url], capture_output=True, text=True, timeout=60)
                if r.returncode != 0:
                    print("Download failed", file=sys.stderr)
                    sys.exit(1)
                os.makedirs(output_dir, exist_ok=True)
                md_out = os.path.join(output_dir, base_name + ".md")
                with open(md_out, "w", encoding="utf-8") as f:
                    f.write(r.stdout)
                print(f"Saved to {md_out}")
                return
            print("No download URL in response.", file=sys.stderr)
            sys.exit(1)
        elif state == "failed":
            print(f"Parse failed: {state_data.get('err_msg', 'unknown')}", file=sys.stderr)
            sys.exit(1)


def precision_parse(filepath, filename, language, is_ocr, output_dir, base_name, model, token):
    """Parse via the Precision API."""
    auth_headers = {"Authorization": f"Bearer {token}"}

    print("Requesting upload URL (precision API)...", file=sys.stderr)
    req_body = {"files": [{"name": filename, "is_ocr": is_ocr, "lang": language}]}
    if model:
        req_body["model_version"] = model
    data = api_request("POST", f"{PRECISION_API}/file-urls/batch",
                       req_body, auth_headers)
    result = data.get("data", data)
    if data.get("code") != 0:
        print(f"Failed to get upload URL: {json.dumps(data)}", file=sys.stderr)
        sys.exit(1)
    file_urls = result.get("file_urls", [])
    if not file_urls:
        print(f"No upload URL in response: {json.dumps(data)}", file=sys.stderr)
        sys.exit(1)
    upload_url = file_urls[0]
    batch_id = result.get("batch_id")
    if not batch_id:
        print(f"No batch_id in response: {json.dumps(data)}", file=sys.stderr)
        sys.exit(1)

    print("Uploading file...", file=sys.stderr)
    r = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-X", "PUT",
         "--upload-file", filepath, upload_url],
        capture_output=True, text=True, timeout=300,
    )
    http_code = r.stdout.strip()
    if r.returncode != 0 or http_code != "200":
        print(f"Upload failed: HTTP {http_code}", file=sys.stderr)
        if http_code == "403":
            print("Check that MINERU_API_TOKEN is valid.", file=sys.stderr)
        sys.exit(1)
    print(f"Upload OK (HTTP {http_code})", file=sys.stderr)

    print("Parsing (auto-submitted after upload)...", file=sys.stderr)
    result_url = None
    while result_url is None:
        time.sleep(3)
        data = api_request("GET", f"{PRECISION_API}/extract-results/batch/{batch_id}",
                           headers=auth_headers)
        state_data = data.get("data", data)
        result_list = state_data.get("extract_result", [])
        if not result_list:
            print(f"Unexpected poll response: {json.dumps(state_data)[:500]}", file=sys.stderr)
            sys.exit(1)
        file_result = result_list[0]
        state = file_result.get("state", "")
        if state == "done":
            result_url = (file_result.get("full_zip_url") or
                          file_result.get("download_url") or
                          file_result.get("zip_url") or
                          file_result.get("result_url"))
            if not result_url:
                print(f"No download URL in result: {json.dumps(file_result)}", file=sys.stderr)
                sys.exit(1)
        elif state == "failed":
            print(f"Parse failed: {file_result.get('err_msg', 'unknown')}", file=sys.stderr)
            sys.exit(1)

    download_and_extract_zip(result_url, output_dir, base_name)


def main():
    p = argparse.ArgumentParser(description="Convert PDF to markdown via MinerU API")
    p.add_argument("file", help="PDF file to convert")
    p.add_argument("-o", "--output", help="Output directory (default: <input>_output/)")
    p.add_argument("-l", "--language", default="en", help="Document language (default: en)")
    p.add_argument("--ocr", action="store_true", help="Enable OCR for scanned PDFs")
    p.add_argument("-m", "--model", choices=["pipeline", "vlm"],
                   help="Model for precision API (default: vlm). Ignored with agent API.")
    args = p.parse_args()

    filepath = os.path.abspath(args.file)
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    filename = os.path.basename(filepath)
    base_name = os.path.splitext(filename)[0]

    if args.output:
        output = args.output
        if output.endswith('.md'):
            output = output[:-3]
        output_dir = os.path.abspath(output)
    else:
        output_dir = os.path.abspath(base_name + "_output")

    token = get_mineru_token()
    if token:
        precision_parse(filepath, filename, args.language, args.ocr, output_dir,
                        base_name, model=args.model or "vlm", token=token)
    else:
        agent_parse(filepath, filename, args.language, args.ocr, output_dir, base_name)


if __name__ == "__main__":
    main()
