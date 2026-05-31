import json
from http.server import HTTPServer
from socketserver import ThreadingMixIn


def json_response(handler, code: int, data=None, message: str = "", code_str: str = None):
    status_map = {
        200: "success",
        201: "created",
        400: "bad_request",
        404: "not_found",
        500: "internal_error"
    }
    status = code_str or status_map.get(code, "error")
    body = {
        "code": code,
        "status": status,
        "message": message,
        "data": data
    }
    body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body_bytes)))
    handler.send_header("X-Request-ID", getattr(handler, "_request_id", ""))
    handler.end_headers()
    handler.wfile.write(body_bytes)
    handler.wfile.flush()


def read_json_body(handler) -> dict:
    try:
        length = int(handler.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        body = handler.rfile.read(length)
        return json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def format_tasks_to_text(json_data: dict) -> str:
    lines = []
    active_count = json_data.get("active_count", 0)
    total = json_data.get("total", 0)
    tasks = json_data.get("tasks", [])

    lines.append("+--------------------------------------------------------------------------------------------+")
    lines.append(f"|  NAS影视入库系统 - 活跃任务                                                                   |")
    lines.append(f"|  活跃任务: {active_count}{' ' * 6}总记录: {total}{' ' * 54} |")
    lines.append("+--------------------------------------------------------------------------------------------+")
    lines.append("")

    if not tasks:
        lines.append("  没有活跃任务，所有任务已处理完毕")
    else:
        def status_label(s):
            if s == "SUCCESS":
                return "成功"
            if s == "FAILED":
                return "失败"
            if s == "PROCESSING":
                return "处理中"
            if s == "PENDING":
                return "待处理"
            if s == "SKIPPED":
                return "跳过"
            return s

        def format_error(msg, max_len=20):
            if not msg:
                return ""
            if len(msg) > max_len:
                return msg[:max_len-2] + ".."
            return msg

        lines.append(f'{"文件名":.<28} {"状态":^8} {"进度":^6} {"刮削结果":.<18} {"错误原因":.<20}')
        lines.append(f'{"-" * 28} {"-" * 8} {"-" * 6} {"-" * 18} {"-" * 20}')

        for t in tasks:
            name = t.get("source_filename", "")
            name_short = (name[:25] + "...") if len(name) > 28 else name
            status = t.get("status", "")
            pct = t.get("percentage", 0)
            scraped = t.get("scrape_result", {})
            error_msg = format_error(t.get("error_message", ""), 20)

            title_cn = scraped.get("title_cn", "") or scraped.get("title_en", "") or "?"
            year = scraped.get("year", "")
            result = f"{title_cn}({year})" if year else title_cn
            result_short = (result[:16] + "..") if len(result) > 18 else result

            lines.append(f"{name_short:<28} {status_label(status):^8} {pct:>3}%   {result_short:<18} {error_msg:<20}")

    return "\n".join(lines)
