#!/usr/bin/env python3
import getpass
import os
import tempfile


def get_current_user():
    try:
        return getpass.getuser()
    except Exception:
        try:
            import pwd
            return pwd.getpwuid(os.getuid()).pw_name
        except Exception:
            return "unknown"


def is_app_managed_path(path: str) -> bool:
    if not path:
        return False
    managed_prefixes = [
        "/vol1/@appdata/", "/vol2/@appdata/", "/vol3/@appdata/", "/vol4/@appdata/",
        "/vol1/@appcenter/", "/vol2/@appcenter/", "/vol3/@appcenter/", "/vol4/@appcenter/",
        "/vol1/@appconf/", "/vol2/@appconf/", "/vol3/@appconf/", "/vol4/@appconf/",
        "/vol1/@apptemp/", "/vol2/@apptemp/", "/vol3/@apptemp/", "/vol4/@apptemp/",
        "/vol1/@appshare/", "/vol2/@appshare/", "/vol3/@appshare/", "/vol4/@appshare/",
    ]
    for prefix in managed_prefixes:
        if path.startswith(prefix):
            return True
    return False


def check_path_permission(path: str, need_write: bool = True) -> dict:
    result = {
        "path": path,
        "ok": True,
        "level": "ok",
        "message": "",
        "hint": "",
        "exists": False,
        "readable": False,
        "writable": False,
    }

    if not path:
        result["ok"] = False
        result["level"] = "error"
        result["message"] = "路径为空"
        return result

    if not os.path.isabs(path):
        result["ok"] = False
        result["level"] = "error"
        result["message"] = "必须使用绝对路径"
        return result

    if os.path.exists(path):
        result["exists"] = True

        if not os.path.isdir(path):
            result["ok"] = False
            result["level"] = "error"
            result["message"] = f"路径存在但不是目录: {path}"
            return result

        result["readable"] = os.access(path, os.R_OK)
        result["writable"] = os.access(path, os.W_OK)

        if not result["readable"]:
            result["ok"] = False
            result["level"] = "error"
            result["message"] = f"应用用户 {get_current_user()} 无权读取此目录"
            result["hint"] = _build_auth_hint(path, need_write)
            return result

        if need_write and not result["writable"]:
            result["ok"] = False
            result["level"] = "error"
            result["message"] = f"应用用户 {get_current_user()} 无权写入此目录"
            result["hint"] = _build_auth_hint(path, need_write)
            return result

        if need_write:
            try:
                with tempfile.NamedTemporaryFile(dir=path, prefix=".perm_test_", delete=True):
                    pass
            except (OSError, PermissionError) as e:
                result["ok"] = False
                result["level"] = "error"
                result["message"] = f"实际写入测试失败: {e}"
                result["hint"] = _build_auth_hint(path, need_write)
                return result

        result["message"] = "权限正常"
        return result

    parent = os.path.dirname(path) or "/"
    while parent and not os.path.exists(parent):
        new_parent = os.path.dirname(parent)
        if new_parent == parent:
            break
        parent = new_parent

    if not os.path.exists(parent):
        result["ok"] = False
        result["level"] = "error"
        result["message"] = f"路径不存在，且父目录也不存在: {parent}"
        result["hint"] = "请先确认上级目录已创建，或选择已存在的目录"
        return result

    if not os.access(parent, os.W_OK):
        result["ok"] = False
        result["level"] = "error"
        result["message"] = f"路径不存在，且无权在父目录 {parent} 中创建"
        result["hint"] = _build_auth_hint(parent, True)
        return result

    try:
        os.makedirs(path, exist_ok=True)
        result["exists"] = True
        result["readable"] = True
        result["writable"] = True
        result["message"] = "目录已自动创建，权限正常"
        return result
    except (OSError, PermissionError) as e:
        result["ok"] = False
        result["level"] = "error"
        result["message"] = f"无法创建目录: {e}"
        result["hint"] = _build_auth_hint(parent, True)
        return result


def _build_auth_hint(path: str, need_write: bool) -> str:
    perm_text = "【读】+【写】" if need_write else "【读】"
    return (
        f"请在 fnOS 应用中心 → nas-media-importer → 设置 → 授权目录 → 添加目录\n"
        f"路径: {path}\n"
        f"权限: 勾选 {perm_text}\n"
        f"保存授权后，回到此页面重新点击保存或测试"
    )


def extract_root_from_template(template: str) -> str:
    if not template:
        return ""
    template = template.strip()
    var_pos = template.find("{")
    if var_pos < 0:
        return template.rstrip("/")
    prefix = template[:var_pos]
    last_sep = prefix.rfind("/")
    if last_sep < 0:
        return ""
    root = prefix[:last_sep]
    return root.rstrip("/")


def check_config_permissions(config: dict) -> dict:
    issues = []

    def _add_issue(field, path, check_result):
        if check_result["ok"]:
            return
        issues.append({
            "field": field,
            "path": path,
            "level": check_result["level"],
            "message": check_result["message"],
            "hint": check_result["hint"],
        })

    source_dir = config.get("source_dir", "")
    source_cleaner = config.get("source_cleaner", {})
    cleaner_enabled = source_cleaner.get("enabled", False)
    source_need_write = cleaner_enabled
    if source_dir and not is_app_managed_path(source_dir):
        r = check_path_permission(source_dir, need_write=source_need_write)
        field_label = "source_dir" if not cleaner_enabled else "source_dir (清理器需写权限)"
        _add_issue(field_label, source_dir, r)

    recycle_dir = ""
    source_policy = config.get("source_policy", {})
    recycle_dir = source_policy.get("recycle_dir", "")
    if recycle_dir and not is_app_managed_path(recycle_dir):
        r = check_path_permission(recycle_dir, need_write=True)
        _add_issue("recycle_dir", recycle_dir, r)

    temp_dir = config.get("temp_dir", "")
    if temp_dir and not is_app_managed_path(temp_dir):
        r = check_path_permission(temp_dir, need_write=True)
        _add_issue("temp_dir", temp_dir, r)

    log_dir = config.get("log_dir", "")
    if log_dir and not is_app_managed_path(log_dir):
        r = check_path_permission(log_dir, need_write=True)
        _add_issue("log_dir", log_dir, r)

    path_rules = config.get("path_rules", [])
    seen_roots = set()
    for idx, rule in enumerate(path_rules):
        template = rule.get("template", "")
        root = extract_root_from_template(template)
        if not root or root in seen_roots or is_app_managed_path(root):
            continue
        seen_roots.add(root)
        r = check_path_permission(root, need_write=True)
        if not r["ok"]:
            issues.append({
                "field": f"path_rules[{idx}].template",
                "path": root,
                "level": r["level"],
                "message": f"入库规则[{idx+1}]的根目录权限检查失败: {r['message']}",
                "hint": r["hint"],
                "rule_index": idx,
                "rule_template": template,
            })

    return {
        "all_ok": len(issues) == 0,
        "user": get_current_user(),
        "issues": issues,
    }
