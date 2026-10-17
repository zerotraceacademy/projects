
"""
YouTube Live Chat Password Auditor
Terminal-only version.

Install:
    python -m pip install pytchat

Windows CMD:
    set YOUTUBE_VIDEO_ID=YOUR_VIDEO_ID
    python youtube_live_auditor.py

Chat command:
    !audit DemoPass2026!

IMPORTANT:
Use dummy/test passphrases only. Never submit real passwords
in public YouTube chat.
"""

import os
import re
import math
import time
import hashlib
import queue
import threading
import urllib.request
import urllib.error
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
try:
    import pytchat
except ImportError:
    raise SystemExit(
        "Install pytchat first:\n"
        "python -m pip install pytchat"
    )

load_dotenv()

# ================= CONFIGURATION =================

VIDEO_ID = os.getenv("YOUTUBE_VIDEO_ID", "").strip()

MAX_WORKERS = 6
MAX_QUEUE_SIZE = 50
MAX_PASSWORD_LENGTH = 128
USER_COOLDOWN = 5
HIBP_TIMEOUT = 5


# ================= TERMINAL COLORS =================

class UI:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"


PRINT_LOCK = threading.Lock()


def safe_print(*args, **kwargs):
    with PRINT_LOCK:
        print(*args, **kwargs, flush=True)


# ================= PASSWORD MASKING =================

def mask_password(password):
    if len(password) <= 2:
        return "*" * max(4, len(password))

    return (
        password[0]
        + "*" * min(12, len(password) - 2)
        + password[-1]
    )


# ================= ENTROPY =================

def calculate_entropy(password):
    if not password:
        return 0.0

    pool = 0

    if re.search(r"[a-z]", password):
        pool += 26

    if re.search(r"[A-Z]", password):
        pool += 26

    if re.search(r"[0-9]", password):
        pool += 10

    if re.search(r"[^a-zA-Z0-9]", password):
        pool += 32

    if pool == 0:
        return 0.0

    return round(len(password) * math.log2(pool), 2)


# ================= WEAK PATTERNS =================

def detect_weak_patterns(password):
    warnings = []
    lower = password.lower()

    common = [
        "qwerty",
        "asdf",
        "zxcv",
        "12345",
        "09876",
        "password",
        "admin",
        "letmein",
        "welcome",
    ]

    if any(pattern in lower for pattern in common):
        warnings.append("Common/keyboard pattern")

    if re.search(r"(.)\1{2,}", password):
        warnings.append("Repeated characters")

    if re.search(r"(19\d\d|20\d\d)", password):
        warnings.append("Contains a year")

    if re.fullmatch(
        r"[a-zA-Z]+[0-9]{1,4}[!@#$%^&*]?",
        password
    ):
        warnings.append("Predictable suffix")

    return warnings


# ================= CRACK-TIME ESTIMATE =================

def estimate_crack_time(entropy):
    # Illustrative assumption, not a real-world guarantee.
    seconds = (2 ** min(entropy, 1024)) / 10_000_000_000

    if seconds < 1:
        return "Under 1 second"

    if seconds < 60:
        return f"{int(seconds)} seconds"

    if seconds < 3600:
        return f"{int(seconds // 60)} minutes"

    if seconds < 86400:
        return f"{int(seconds // 3600)} hours"

    if seconds < 31536000:
        return f"{int(seconds // 86400)} days"

    if seconds < 31536000 * 1000:
        return f"{int(seconds // 31536000)} years"

    return "Centuries+"


# ================= HIBP BREACH CHECK =================

HIBP_CACHE = {}
HIBP_CACHE_LOCK = threading.Lock()


def check_hibp_breach(password):
    """
    Uses Have I Been Pwned's k-anonymity range API.
    Only the first 5 SHA-1 hash characters are sent.
    
    Returns:
        Positive integer: known breach occurrences
        0: no match returned
       -1: API/network error
    """

    digest = hashlib.sha1(
        password.encode("utf-8")
    ).hexdigest().upper()

    prefix = digest[:5]
    suffix = digest[5:]

    with HIBP_CACHE_LOCK:
        cached = HIBP_CACHE.get(digest)

    if cached is not None:
        return cached

    url = f"https://api.pwnedpasswords.com/range/{prefix}"

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Python-Live-Password-Auditor",
            "Add-Padding": "true",
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=HIBP_TIMEOUT
        ) as response:
            body = response.read(
                1_000_000
            ).decode("utf-8", errors="replace")

        result = 0

        for line in body.splitlines():
            parts = line.strip().split(":")

            if len(parts) != 2:
                continue

            returned_suffix, count = parts

            if returned_suffix.upper() == suffix:
                result = int(count)
                break

        with HIBP_CACHE_LOCK:
            HIBP_CACHE[digest] = result

        return result

    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        ValueError,
    ):
        return -1


# ================= AUDIT ENGINE =================

def audit_single_password(password):
    entropy = calculate_entropy(password)
    warnings = detect_weak_patterns(password)
    breach_count = check_hibp_breach(password)

    if breach_count > 0 or entropy < 40:
        grade = "F-TIER (WEAK OR EXPOSED)"

    elif entropy < 60 or len(warnings) >= 2:
        grade = "C-TIER (WEAK)"

    elif entropy < 75 or len(warnings) == 1:
        grade = "A-TIER (GOOD ESTIMATE)"

    else:
        grade = "S-TIER (STRONG ESTIMATE)"

    return {
        "masked": mask_password(password),
        "entropy": entropy,
        "crack_time": estimate_crack_time(entropy),
        "breach_count": breach_count,
        "warnings": warnings,
        "grade": grade,
        "thread": threading.current_thread().name,
    }


# ================= DISPLAY RESULTS =================

def print_audit_result(username, result):
    count = result["breach_count"]

    if count > 0:
        breach = f"{UI.RED}{count:,} occurrences{UI.RESET}"

    elif count == 0:
        breach = f"{UI.GREEN}No match returned{UI.RESET}"

    else:
        breach = f"{UI.YELLOW}API unavailable{UI.RESET}"

    grade = result["grade"]

    if grade.startswith("S-TIER"):
        grade = f"{UI.GREEN}{UI.BOLD}{grade}{UI.RESET}"

    elif grade.startswith("A-TIER"):
        grade = f"{UI.CYAN}{grade}{UI.RESET}"

    elif grade.startswith("C-TIER"):
        grade = f"{UI.YELLOW}{grade}{UI.RESET}"

    else:
        grade = f"{UI.RED}{UI.BOLD}{grade}{UI.RESET}"

    safe_print(
        f"\n{UI.DIM}{'=' * 65}{UI.RESET}\n"
        f"{UI.CYAN}{UI.BOLD}VIEWER:{UI.RESET} {username[:50]}\n"
        f"Masked sample : {result['masked']}\n"
        f"Entropy       : {result['entropy']} bits\n"
        f"Crack estimate: {result['crack_time']}\n"
        f"HIBP result   : {breach}\n"
        f"Pattern flags : "
        f"{', '.join(result['warnings']) if result['warnings'] else 'None detected'}\n"
        f"Security grade: {grade}\n"
        f"Worker        : {result['thread']}\n"
        f"{UI.DIM}{'=' * 65}{UI.RESET}"
    )


# ================= CHAT COMMAND PARSER =================

def parse_audit_command(message):
    match = re.match(
        r"^!audit\s+(.+)$",
        message.strip(),
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    password = match.group(1).strip()

    if not password:
        return None

    if len(password) > MAX_PASSWORD_LENGTH:
        return None

    if any(ord(char) < 32 for char in password):
        return None

    return password


# ================= WORKER =================

def worker(work_queue, stop_event):
    while not stop_event.is_set():
        try:
            task = work_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        if task is None:
            work_queue.task_done()
            break

        username, password = task

        try:
            result = audit_single_password(password)
            print_audit_result(username, result)

        except Exception as exc:
            # Never log the raw submitted password.
            safe_print(
                f"{UI.RED}Audit error: "
                f"{type(exc).__name__}{UI.RESET}"
            )

        finally:
            password = ""
            work_queue.task_done()


# ================= MAIN APPLICATION =================

def main():
    if not VIDEO_ID:
        raise SystemExit(
            "Set your YouTube Video ID first.\n\n"
            "Windows CMD example:\n"
            "set YOUTUBE_VIDEO_ID=YOUR_VIDEO_ID\n"
            "python youtube_live_auditor.py"
        )

    safe_print(
        f"{UI.MAGENTA}{UI.BOLD}"
        "=== YOUTUBE LIVE PASSWORD AUDITOR ==="
        f"{UI.RESET}"
    )

    safe_print(
        "Use dummy/test passphrases only.\n"
        "Chat command: !audit DemoPass2026!\n"
        "Connecting to YouTube Live Chat..."
    )

    work_queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)
    stop_event = threading.Event()

    last_user_request = {}
    processed_ids = set()

    executor = ThreadPoolExecutor(
        max_workers=MAX_WORKERS,
        thread_name_prefix="Auditor",
    )

    workers = [
        executor.submit(worker, work_queue, stop_event)
        for _ in range(MAX_WORKERS)
    ]

    chat = None

    try:
        chat = pytchat.create(video_id=VIDEO_ID)

        safe_print(
            f"{UI.GREEN}Connected! Waiting for chat commands..."
            f"{UI.RESET}"
        )

        while chat.is_alive():

            try:
                messages = chat.get().sync_items()

            except Exception as exc:
                safe_print(
                    f"{UI.YELLOW}Chat read error: "
                    f"{type(exc).__name__}{UI.RESET}"
                )
                time.sleep(2)
                continue

            for item in messages:

                message_id = str(
                    getattr(item, "id", "") or ""
                )

                if message_id:
                    if message_id in processed_ids:
                        continue

                    processed_ids.add(message_id)

                    if len(processed_ids) > 5000:
                        processed_ids.clear()

                message = str(
                    getattr(item, "message", "") or ""
                )

                password = parse_audit_command(message)

                if password is None:
                    continue

                author = getattr(item, "author", None)

                username = str(
                    getattr(author, "name", "Viewer")
                    or "Viewer"
                )

                user_id = str(
                    getattr(author, "channelId", "")
                    or username
                )

                now = time.monotonic()
                previous = last_user_request.get(user_id, 0)

                if now - previous < USER_COOLDOWN:
                    password = ""
                    continue

                last_user_request[user_id] = now

                try:
                    work_queue.put_nowait(
                        (username, password)
                    )

                    safe_print(
                        f"{UI.DIM}[QUEUED] {username[:40]} "
                        f"submitted a test phrase.{UI.RESET}"
                    )

                except queue.Full:
                    safe_print(
                        f"{UI.YELLOW}[QUEUE FULL] "
                        f"Submission ignored.{UI.RESET}"
                    )

                password = ""

            time.sleep(0.5)

        safe_print("Live chat ended or became unavailable.")

    except KeyboardInterrupt:
        safe_print("\nStopping auditor...")

    except Exception as exc:
        safe_print(
            f"{UI.RED}Connection error: "
            f"{type(exc).__name__}{UI.RESET}\n"
            "Check the Video ID, internet connection, "
            "stream status and live-chat availability."
        )

    finally:
        if chat is not None:
            try:
                chat.terminate()
            except Exception:
                pass

        # Drain accepted work before stopping workers.
        work_queue.join()
        stop_event.set()

        for _ in workers:
            work_queue.put(None)

        executor.shutdown(wait=True)

        safe_print("Auditor stopped.")


if __name__ == "__main__":
    main()
