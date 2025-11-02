import os
import sys
from typing import Optional, List
import json
from datetime import datetime
import threading
import time
from textwrap import dedent
import re
import pathlib
import subprocess

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:
    pass

import google.generativeai as genai

DEFAULT_MODEL = "gemini-1.5-flash-latest"


def get_api_key() -> Optional[str]:
    return os.environ.get("GOOGLE_API_KEY")


def _make_model(model_name: str, system_instruction: Optional[str]):
    if system_instruction:
        return genai.GenerativeModel(model_name, system_instruction=system_instruction)  # type: ignore[attr-defined]
    return genai.GenerativeModel(model_name)  # type: ignore[attr-defined]


def list_available_text_models(api_key: str) -> list[str]:
    genai.configure(api_key=api_key)  # type: ignore[attr-defined]
    names: list[str] = []
    try:
        for m in genai.list_models():  # type: ignore[attr-defined]
            methods = getattr(m, "supported_generation_methods", []) or []
            if any(str(x).lower() == "generatecontent" for x in methods):
                name = getattr(m, "name", None)
                if name:
                    names.append(str(name))
    except Exception:
        pass
    return names


def generate_text(
    prompt: str, model_name: str, system_instruction: Optional[str]
) -> str:
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError(
            "Thiếu GOOGLE_API_KEY. Hãy đặt biến môi trường hoặc tạo file .env (xem README)."
        )

    genai.configure(api_key=api_key)  # type: ignore[attr-defined]

    # Sắp xếp danh sách ứng viên model theo khả dụng và ưu tiên
    tried: list[str] = []
    available = list_available_text_models(api_key)

    candidates: list[str] = []
    if model_name:
        candidates.append(model_name)
        if not model_name.endswith("-latest") and (
            model_name.startswith("gemini-1.5-") or model_name.startswith("gemini-2.")
        ):
            candidates.append(model_name + "-latest")

    pref_order = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-latest",
        "gemini-2.5-pro",
        "gemini-2.5-pro-latest",
        "gemini-1.5-flash",
        "gemini-1.5-flash-latest",
        "gemini-1.5-pro",
        "gemini-1.5-pro-latest",
        "gemini-pro",
    ]
    for n in pref_order:
        if n in available and n not in candidates:
            candidates.append(n)
    for n in available:
        if n not in candidates:
            candidates.append(n)

    last_err: Optional[Exception] = None
    for name in candidates:
        try:
            model = _make_model(name, system_instruction)
            response = model.generate_content(prompt)
            return getattr(response, "text", str(response))
        except Exception as e:
            msg = str(e).lower()
            tried.append(name)
            if (
                ("404" in msg)
                or ("not found" in msg)
                or ("is not supported" in msg)
                or ("invalid argument" in msg)
            ):
                last_err = e
                continue
            raise
    raise RuntimeError(
        f"Không thể gọi model. Đã thử: {tried}. Model khả dụng: {available}. Lỗi cuối: {last_err}"
    )


def _ensure_log_dir() -> str:
    cand = os.path.abspath(os.path.join(os.getcwd(), "logs"))
    os.makedirs(cand, exist_ok=True)
    return cand


def _new_session_logfile() -> str:
    log_dir = _ensure_log_dir()
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join(log_dir, f"chat-{ts}.jsonl")


def _append_jsonl(path: str, obj: dict) -> None:
    safe_root = os.path.abspath(_ensure_log_dir())
    abs_path = os.path.abspath(path)
    if not abs_path.startswith(safe_root):
        raise ValueError("Invalid log path outside of allowed directory")
    with open(abs_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _spinner(stop_event: threading.Event, interval: float = 0.25):
    while not stop_event.is_set():
        print(".", end="", flush=True)
        time.sleep(interval)


def _read_code_from_user() -> Optional[str]:
    print("Dán đoạn mã code của bạn bên dưới. Kết thúc bằng một dòng chỉ chứa: EOF")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            print("\n(Huỷ nhập mã)")
            return None
        if line.strip() == "EOF":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _promptify_from_code(
    code_text: str, template: Optional[str], model_name: str
) -> str:
    user_template = (
        (template or os.environ.get("PROMPTIFY_TEMPLATE"))
        or 'Đây là đoạn mã code của ngôn ngữ "{lang}" và những lỗi trong đoạn mã đó là những test case'
    )
    sys_inst = (
        os.environ.get("GEMINI_SYSTEM")
        or "Bạn là công cụ tạo prompt. Chỉ xuất ra đúng 1 dòng theo template, không thêm giải thích hay ký tự thừa."
    )
    meta_prompt = dedent(
        f"""
        Nhiệm vụ: Xác định ngôn ngữ của đoạn mã và xuất đúng 1 dòng PROMPT theo TEMPLATE sau.

        TEMPLATE: "{user_template}"
        - Thay thế {{lang}} bằng tên ngôn ngữ phù hợp (ví dụ: Python, JavaScript, C++, Java, Go, v.v.).
        - Nếu không xác định được, thay {{lang}} = "không rõ".
        - Không thêm giải thích, không thêm ký tự trang trí, không xuống dòng dư. Chỉ in đúng 1 dòng kết quả.

        Đoạn mã:
        ```
        {code_text}
        ```
        """
    ).strip()
    return generate_text(
        meta_prompt, model_name=model_name, system_instruction=sys_inst
    ).strip()


def _fixcode_formatted_output(code_text: str, model_name: str) -> str:
    """Yêu cầu Gemini xuất ĐÚNG định dạng:
    1. Đoạn code sai
    2. Các test case (dạng text)
    3. Đoạn code đã sửa

    Không thêm bất kỳ mô tả nào khác trước hoặc sau 3 phần này.
    """
    sys_inst = (
        os.environ.get("GEMINI_SYSTEM")
        or "Bạn là trợ lý sửa lỗi code. Hãy tuân thủ định dạng nghiêm ngặt, không thêm mô tả ngoài yêu cầu."
    )
    meta_prompt = dedent(
        f"""
        Nhiệm vụ: Phân tích đoạn mã được cung cấp bên dưới.
        Chỉ trả lời bằng 3 phần theo ĐỊNH DẠNG BẮT BUỘC sau. KHÔNG thêm bất kỳ lời chào, giải thích, hay văn bản nào khác trước hoặc sau 3 phần này.

        ĐỊNH DẠNG BẮT BUỘC:

        1. Đoạn code sai
        ```{{lang}}
        (Chép NGUYÊN XI đoạn mã đầu vào)
        {code_text}
        
        2. Kết quả kiểm thử (In chính xác theo mẫu. Cung cấp nhiều KIỂM THỬ đa dạng: phức tạp, ngắn, dài, và các trường hợp biên.)

        KIỂM THỬ 1 Đầu vào "<input_1>" Đầu ra thực tế <actual_output> Đầu ra mong đợi <expected_output> Giới hạn thời gian 2000 ms Thời gian thực thi <execution_time> ms Mô tả: <Right answer hoặc Wrong answer>

        KIỂM THỬ 2 Đầu vào "<input_1>" "<input_2>" Đầu ra thực tế <actual_output> Đầu ra mong đợi <expected_output> Giới hạn thời gian 2000 ms Thời gian thực thi <execution_time> ms Mô tả: <Right answer hoặc Wrong answer>

        (Thêm các KIỂM THỬ khác nếu cần)

        Đoạn code đã sửa

        3. Đoạn code đã sửa
        ```{{lang}}
        (Chỉ in mã đã sửa. Nếu mã ban đầu đã đúng, chép lại y hệt mã ban đầu.)
        ```
        Quy tắc:
        - {{lang}} là tên ngôn ngữ phù hợp với đoạn mã (ví dụ: c, cpp, python, javascript, java, go...).
        - KHÔNG thêm bất kỳ văn bản nào ngoài 3 mục trên. KHÔNG thêm lời chào, giải thích hay ghi chú.
        - Nếu cần thay đổi định dạng khoảng trắng trong mục (1) chỉ để giữ nguyên ý nghĩa; tốt nhất hãy giữ nguyên như đầu vào.

        Đây là đoạn mã cần xử lý:
        ```
        {code_text}
        ```
        """
    ).strip()
    return generate_text(
        meta_prompt, model_name=model_name, system_instruction=sys_inst
    ).strip()


# ---------- Strict 3-part output (guardrailed) ----------


def _guess_language_simple(code_text: str) -> str:
    s = code_text.strip()
    # Heuristic only
    if (
        "def " in s or "import " in s or re.search(r"^\s*class\s+\w+", s, re.M)
    ) and "#include" not in s:
        return "python"
    if "#include" in s:
        return "c"
    if re.search(r"public\s+class\s+\w+", s):
        return "java"
    if re.search(r"function\s+\w+\s*\(|=>", s) and ";" in s:
        return "javascript"
    return ""


def _ai_generate_test_lines(code_text: str, model_name: str) -> list[str]:
    sys_inst = (
        os.environ.get("GEMINI_SYSTEM")
        or "Chỉ xuất 4 dòng test case, đánh số 1..4, mỗi dòng ngắn gọn. Không thêm bất cứ nội dung nào khác."
    )
    prompt = dedent(
        f"""
        Tạo 4 test case DẠNG VĂN BẢN cho đoạn mã sau để phát hiện lỗi hiện có (trước khi sửa).
        QUY TẮC:
        - Chỉ in đúng 4 dòng, đánh số: 1. ..., 2. ..., 3. ..., 4. ...
        - Mỗi dòng là một mô tả test ngắn gọn (input/điều kiện + kỳ vọng).
        - Không in code, không in tiêu đề, không giải thích thêm.

        Đoạn mã:
        ```
        {code_text}
        ```
        """
    ).strip()
    out = generate_text(prompt, model_name=model_name, system_instruction=sys_inst)
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    # Lọc 4 dòng đầu, bỏ tiền tố số nếu cần chuẩn hóa
    cleaned: list[str] = []
    for ln in lines:
        # Bóc tiền tố số (1., 2., ...)
        m = re.match(r"^\s*\d+\.?\s*(.*)$", ln)
        cleaned.append(m.group(1).strip() if m else ln)
        if len(cleaned) == 4:
            break
    # Đảm bảo có 4 dòng (đệm nếu thiếu)
    while len(cleaned) < 4:
        cleaned.append("<bổ sung test case>")
    return cleaned[:4]


def _ai_generate_fixed_code(code_text: str, model_name: str) -> tuple[str, str]:
    """Return (lang, code) for a SINGLE, CONSOLIDATED corrected file.

    Behavior:
    - The model is instructed to output exactly ONE code fence containing the FINAL, FULLY MERGED source file
      (useful for integration tests), even if the input contains multiple snippets and prose.
    - If multiple fences are returned, we pick the largest block by content length.
    - On failure, fall back to original code with a guessed language.
    """
    sys_inst = os.environ.get("GEMINI_SYSTEM") or (
        "Chỉ xuất DUY NHẤT 1 khối code fence chứa toàn bộ mã đã sửa sau khi hợp nhất. "
        "Không in thêm bất kỳ văn bản nào ngoài khối code."
    )
    prompt = dedent(
        f"""
        Bạn nhận một văn bản có thể bao gồm nhiều đoạn code rời rạc, tiêu đề, và phân tích. Nhiệm vụ của bạn:
        - TẠO RA MỘT TỆP MÃ HOÀN CHỈNH đã SỬA LỖI, hợp nhất tất cả phần liên quan, có thể biên dịch/chạy ngay.
        - GIỮ NGUYÊN NGÔN NGỮ của đoạn mã gốc (tự đoán: python, java, javascript, c/cpp, v.v.).
        - Nếu là Java: đảm bảo 1 public class thống nhất (giữ tên class gốc nếu suy ra được; nếu không, dùng CorrectedUtilityFunctions).
        - Nếu là Python: tệp tự chạy được nếu hợp lý (thêm guard if __name__ == "__main__": khi cần).
        - Không thêm giải thích, không tiêu đề, không mô tả.
        - CHỈ IN đúng 1 khối code fence: ```{{lang}}\n<toàn bộ mã đã sửa>\n```

        ĐÂY LÀ NỘI DUNG ĐẦU VÀO (CÓ THỂ GỒM NHIỀU KHỐI CODE VÀ MÔ TẢ):
        ```
        {code_text}
        ```
        """
    ).strip()
    out = generate_text(prompt, model_name=model_name, system_instruction=sys_inst)
    # Thu tất cả block rồi lấy block lớn nhất nếu có nhiều hơn 1
    blocks = list(re.finditer(r"```(\w+)?\n(.*?)\n```", out, re.S))
    if blocks:
        # Chọn block có nội dung dài nhất
        best = max(blocks, key=lambda m: len(m.group(2) or ""))
        lang = (best.group(1) or "").strip()
        code = best.group(2)
        return lang, code
    # fallback
    return _guess_language_simple(code_text), code_text


def _fixcode_strict_three_parts(code_text: str, model_name: str) -> str:
    lang = _guess_language_simple(code_text)
    tests = _ai_generate_test_lines(code_text, model_name)
    fixed_lang, fixed_code = _ai_generate_fixed_code(code_text, model_name)
    if not fixed_lang:
        fixed_lang = lang
    # Dựng kết quả đúng khuôn
    parts = []
    parts.append("1. Đoạn code sai")
    parts.append(f"```{lang}\n{code_text}\n```")
    parts.append("\n2. Các test case (dạng text)")
    for i, line in enumerate(tests, 1):
        parts.append(f"{i}. {line}")
    parts.append("\n3. Đoạn code đã sửa")
    parts.append(f"```{fixed_lang}\n{fixed_code}\n```")
    return "\n".join(parts)


# ---------- TESTIFY (Generate & Run tests) helpers ----------


def _ensure_dir(path: str) -> str:
    p = os.path.abspath(path)
    os.makedirs(p, exist_ok=True)
    return p


def _write_text_file(path: str, content: str) -> str:
    abs_root = os.path.abspath(os.getcwd())
    abs_path = os.path.abspath(path)
    if not abs_path.startswith(abs_root):
        raise ValueError("Invalid path outside project root")
    _ensure_dir(os.path.dirname(abs_path))
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(content)
    return abs_path


def _extract_code_blocks(text: str) -> list[tuple[str, str]]:
    """Return list of (lang, code) from triple-backtick blocks."""
    blocks: list[tuple[str, str]] = []
    pattern = re.compile(r"```(\w+)?\n(.*?)\n```", re.S)
    for m in pattern.finditer(text):
        lang = (m.group(1) or "").lower().strip()
        code = m.group(2)
        blocks.append((lang, code))
    return blocks


def _generate_pytests_for_python(code_text: str, model_name: str) -> dict:
    """Ask Gemini to produce two pytest files: unit and integration. Returns dict name->content."""
    sys_inst = (
        os.environ.get("GEMINI_SYSTEM")
        or "Bạn là trợ lý tạo test. Hãy tạo cặp file pytest rõ ràng và CHẠY ĐƯỢC."
    )
    meta_prompt = dedent(
        f"""
        Hãy viết 2 file pytest cho đoạn mã Python dưới đây.
        YÊU CẦU:
        - Trả lời CHỈ BẰNG 2 khối code fence python, mỗi khối bắt đầu bằng 1 dòng comment `# FILE: <tên_file.py>`.
        - File 1: test_user_unit.py — Unit tests tập trung vào từng hàm/nhánh.
        - File 2: test_user_integration.py — Integration tests: chạy chương trình như người dùng (nếu có entrypoint) hoặc kiểm thử đường đi end-to-end hợp lý.
        - Dùng pytest, không phụ thuộc gói ngoài.
        - Không in thêm mô tả ngoài 2 khối code.

        Đoạn mã cần kiểm thử:
        ```python
        {code_text}
        ```
        """
    ).strip()
    out = generate_text(meta_prompt, model_name=model_name, system_instruction=sys_inst)
    blocks = _extract_code_blocks(out)
    results: dict[str, str] = {}
    for lang, code in blocks:
        if lang != "python":
            continue
        lines = code.splitlines()
        first_line = lines[0] if lines else ""
        fname = None
        m = re.match(r"\s*#\s*FILE:\s*([\w\-_.]+)", first_line)
        if m:
            fname = m.group(1)
            body = "\n".join(lines[1:])
        else:
            body = code
        if not fname:
            fname = "test_user_unit.py" if not results else "test_user_integration.py"
        results[fname] = body
        if len(results) >= 2:
            break
    if not results:
        raise RuntimeError("Không trích xuất được file pytest từ phản hồi AI")
    return results


def _run_pytest_and_capture(paths: list[str]) -> str:
    cmd = [sys.executable, "-m", "pytest", "-q", *paths]
    try:
        proc = subprocess.run(cmd, cwd=os.getcwd(), text=True, capture_output=True)
        output = (proc.stdout or "") + (proc.stderr or "")
        return output.strip()
    except Exception as ex:
        return f"Không chạy được pytest: {ex}"


def start_chat_loop(model_name: str, system_instruction: Optional[str]) -> int:
    api_key = get_api_key()
    if not api_key:
        print(
            "Thiếu GOOGLE_API_KEY. Hãy đặt biến môi trường hoặc tạo file .env (xem README)."
        )
        return 1

    genai.configure(api_key=api_key)  # type: ignore[attr-defined]
    model = _make_model(model_name, system_instruction)
    chat = model.start_chat(history=[])  # type: ignore[attr-defined]

    session_log = _new_session_logfile()
    _append_jsonl(
        session_log,
        {
            "event": "session_start",
            "time": datetime.now().isoformat(),
            "model": model_name,
            "system": system_instruction or "",
        },
    )

    print("\nBắt đầu trò chuyện với Gemini. Gõ /help để xem danh sách lệnh.\n")

    while True:
        try:
            user = input("Bạn: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nTạm biệt 👋")
            return 0

        if not user:
            continue

        if user.startswith("/"):
            parts = user.split()
            cmd = parts[0].lower()

            if cmd == "/exit":
                print("Tạm biệt 👋")
                return 0

            elif cmd == "/reset":
                chat = model.start_chat(history=[])  # type: ignore[attr-defined]
                session_log = _new_session_logfile()
                _append_jsonl(
                    session_log,
                    {
                        "event": "session_reset",
                        "time": datetime.now().isoformat(),
                        "model": model_name,
                        "system": system_instruction or "",
                    },
                )
                print("Đã tạo phiên trò chuyện mới.")
                continue

            elif cmd == "/model":
                if len(parts) < 2:
                    print("Dùng: /model <ten_model>")
                    continue
                new_model = parts[1]
                try:
                    model = _make_model(new_model, system_instruction)
                    chat = model.start_chat(history=[])  # type: ignore[attr-defined]
                    model_name = new_model
                    session_log = _new_session_logfile()
                    _append_jsonl(
                        session_log,
                        {
                            "event": "model_changed",
                            "time": datetime.now().isoformat(),
                            "model": model_name,
                        },
                    )
                    print(f"Đã chuyển model sang: {model_name}")
                except Exception as ex:
                    print(f"(Không thể đổi model: {ex})")
                continue

            elif cmd == "/system":
                new_sys = user[len("/system") :].strip()
                if not new_sys:
                    print("Dùng: /system <chuỗi system instruction>")
                    continue
                system_instruction = new_sys
                model = _make_model(model_name, system_instruction)
                chat = model.start_chat(history=[])  # type: ignore[attr-defined]
                session_log = _new_session_logfile()
                _append_jsonl(
                    session_log,
                    {
                        "event": "system_changed",
                        "time": datetime.now().isoformat(),
                        "system": system_instruction,
                    },
                )
                print("Đã cập nhật system instruction và tạo phiên mới.")
                continue

            elif cmd == "/models":
                try:
                    names = list_available_text_models(api_key)
                except Exception as ex:
                    print(f"(Lỗi khi liệt kê model: {ex})")
                    names = []
                if not names:
                    print(
                        "Không lấy được danh sách model (có thể do quyền). Hãy thử đặt GEMINI_MODEL thủ công."
                    )
                else:
                    print("Các model hỗ trợ generateContent:")
                    for n in names:
                        print(" -", n)
                continue

            elif cmd == "/promptify":
                code_text: Optional[str] = None
                if len(parts) >= 2:
                    path = parts[1]
                    abs_fp = os.path.abspath(path)
                    cwd = os.path.abspath(os.getcwd())
                    if not abs_fp.startswith(cwd) or not os.path.isfile(abs_fp):
                        print(
                            "Đường dẫn không hợp lệ hoặc nằm ngoài thư mục dự án. Dán mã thay vì chỉ đường dẫn."
                        )
                    else:
                        try:
                            with open(
                                abs_fp, "r", encoding="utf-8", errors="ignore"
                            ) as f:
                                code_text = f.read().strip()
                        except Exception as ex:
                            print(f"(Không đọc được file: {ex})")
                            code_text = None
                if code_text is None:
                    code_text = _read_code_from_user()
                if not code_text:
                    print("(Không có mã để tạo prompt)")
                    continue
                tmpl: Optional[str] = None
                try:
                    out_prompt = _promptify_from_code(code_text, tmpl, model_name)
                    print(out_prompt)
                except Exception as ex:
                    print(f"(Lỗi promptify: {ex})")
                continue

            elif cmd == "/fixcode":
                # /fixcode [path]
                code_text: Optional[str] = None
                if len(parts) >= 2:
                    path = parts[1]
                    abs_fp = os.path.abspath(path)
                    cwd = os.path.abspath(os.getcwd())
                    if not abs_fp.startswith(cwd) or not os.path.isfile(abs_fp):
                        print(
                            "Đường dẫn không hợp lệ hoặc nằm ngoài thư mục dự án. Dán mã thay vì chỉ đường dẫn."
                        )
                    else:
                        try:
                            with open(
                                abs_fp, "r", encoding="utf-8", errors="ignore"
                            ) as f:
                                code_text = f.read().strip()
                        except Exception as ex:
                            print(f"(Không đọc được file: {ex})")
                            code_text = None
                if code_text is None:
                    code_text = _read_code_from_user()
                if not code_text:
                    print("(Không có mã để xử lý)")
                    continue
                try:
                    # Dùng phiên bản guardrail để đảm bảo đúng khuôn 3 phần
                    out_text = _fixcode_strict_three_parts(code_text, model_name)
                    print(out_text)
                except Exception as ex:
                    print(f"(Lỗi fixcode: {ex})")
                continue

            elif cmd == "/testify":
                code_text: Optional[str] = None
                if len(parts) >= 2:
                    path = parts[1]
                    abs_fp = os.path.abspath(path)
                    cwd = os.path.abspath(os.getcwd())
                    if not abs_fp.startswith(cwd) or not os.path.isfile(abs_fp):
                        print(
                            "Đường dẫn không hợp lệ hoặc nằm ngoài thư mục dự án. Dán mã thay vì chỉ đường dẫn."
                        )
                    else:
                        try:
                            with open(
                                abs_fp, "r", encoding="utf-8", errors="ignore"
                            ) as f:
                                code_text = f.read().strip()
                        except Exception as ex:
                            print(f"(Không đọc được file: {ex})")
                            code_text = None
                if code_text is None:
                    code_text = _read_code_from_user()
                if not code_text:
                    print("(Không có mã để xử lý)")
                    continue

                lang = _guess_language_simple(code_text)
                if lang != "python":
                    print(
                        "Hiện chỉ tự động sinh & chạy test cho Python. Test cho ngôn ngữ khác sẽ được bổ sung sau."
                    )
                    continue

                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                code_dir = _ensure_dir(os.path.join("user_code"))
                mod_name = f"user_code_{ts}"
                code_path = os.path.join(code_dir, f"{mod_name}.py")
                _write_text_file(code_path, code_text)

                try:
                    files = _generate_pytests_for_python(code_text, model_name)
                except Exception as ex:
                    print(f"(Lỗi sinh file pytest: {ex})")
                    continue

                gen_dir = _ensure_dir(os.path.join("tests", "generated"))
                written_paths: list[str] = []
                header = f"# Auto-generated at {ts}\n# Module under test path: {code_path}\n\n"
                loader = dedent(
                    f"""
                    import importlib.util, sys, pathlib
                    _p = pathlib.Path(r"{code_path}").resolve()
                    _spec = importlib.util.spec_from_file_location("{mod_name}", _p)
                    {mod_name} = importlib.util.module_from_spec(_spec)
                    _spec.loader.exec_module({mod_name})  # type: ignore
                    """
                )
                for name, content in files.items():
                    safe_name = re.sub(r"[^\w_.-]", "_", name)
                    full_path = os.path.join(gen_dir, safe_name)
                    _write_text_file(full_path, header + loader + "\n" + content)
                    written_paths.append(full_path)

                print("Đang chạy pytest cho file sinh tự động...")
                out = _run_pytest_and_capture(written_paths)
                print(out)
                continue

            elif cmd == "/help":
                print(
                    "Các lệnh:\n"
                    "  /exit                Thoát\n"
                    "  /reset               Xoá lịch sử, tạo phiên mới\n"
                    "  /model <ten_model>   Đổi model (vd: gemini-2.5-flash)\n"
                    "  /system <chuoi>      Đặt system instruction mới\n"
                    "  /models              Liệt kê model khả dụng\n"
                    "  /promptify [path]    Tạo 1 dòng prompt từ đoạn mã (nếu không chỉ path, dán mã và kết thúc bằng EOF)\n"
                    "  /fixcode  [path]     Phân tích và IN RA ĐÚNG 3 PHẦN: (1) Đoạn code sai, (2) Các test case (text), (3) Đoạn code đã sửa\n"
                    "  /testify [path]      Tạo và CHẠY pytest (unit + integration) cho đoạn mã Python\n"
                    "  /help                Trợ giúp"
                )
                continue

            else:
                print("(Lệnh không hợp lệ. Gõ /help để xem danh sách lệnh.)")
                continue

        _append_jsonl(
            session_log,
            {"role": "user", "text": user, "time": datetime.now().isoformat()},
        )

        print("Gemini: ", end="", flush=True)
        try:
            response = chat.send_message(user, stream=True)  # type: ignore[attr-defined]
            full_text_parts: List[str] = []

            first_chunk = threading.Event()
            stop_spinner = threading.Event()
            spinner_thread = threading.Thread(target=_spinner, args=(stop_spinner,))
            spinner_thread.daemon = True
            spinner_thread.start()

            try:
                for chunk in response:
                    text_piece = getattr(chunk, "text", None)
                    if text_piece:
                        if not first_chunk.is_set():
                            stop_spinner.set()
                            first_chunk.set()
                            spinner_thread.join(timeout=1)
                            print(" ", end="", flush=True)
                        print(text_piece, end="", flush=True)
                        full_text_parts.append(text_piece)
            finally:
                stop_spinner.set()
                try:
                    spinner_thread.join(timeout=1)
                except Exception:
                    pass

                try:
                    response.resolve()  # type: ignore[attr-defined]
                except Exception:
                    pass
                print()

            assistant_text = "".join(full_text_parts)
            _append_jsonl(
                session_log,
                {
                    "role": "assistant",
                    "text": assistant_text,
                    "time": datetime.now().isoformat(),
                },
            )
        except TypeError:
            response = chat.send_message(user)  # type: ignore[attr-defined]
            as_text = getattr(response, "text", str(response))
            print(as_text)
            _append_jsonl(
                session_log,
                {
                    "role": "assistant",
                    "text": as_text,
                    "time": datetime.now().isoformat(),
                },
            )
        except Exception as e:
            print(f"\n(Lỗi khi gọi API: {e})")

    return 0


def main(argv: List[str]) -> int:
    model_name = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    system_instruction = os.environ.get("GEMINI_SYSTEM")
    return start_chat_loop(model_name=model_name, system_instruction=system_instruction)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
