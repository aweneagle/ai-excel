import os
import re
import sys

import pandas as pd
from openai import OpenAI

_client = None
_current_deepseek_api_key = None


def _get_client():
    global _client, _current_deepseek_api_key
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if _client is None or _current_deepseek_api_key != api_key:
        truncated = api_key[:5] + "..." if api_key else "(empty)"
        print(f"[DeepSeek] using api_key={truncated}", file=sys.stderr)
        _client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
        )
        _current_deepseek_api_key = api_key
    return _client

SYSTEM_PROMPT = """你是一个 Python 数据处理助手。用户会给你一条自然语言指令，要求对 Excel/CSV 文件进行操作。

你必须生成一段可直接执行的 Python 代码，遵循以下规则：

## 执行环境（非常重要，必须严格遵守）
- 以下变量已预注入，可以直接使用，不需要定义：pd (pandas), os, INPUTS_DIR, OUTPUTS_DIR
- 允许 import 的库（仅限这些）：numpy, copy, openpyxl, openpyxl.utils, openpyxl.styles, datetime, math, re, json, csv, collections
- os 模块只有以下 5 个方法可用，调用其他方法会报错：
  - os.path.join()
  - os.path.exists()
  - os.path.basename()
  - os.path.splitext()
  - os.listdir()
- 禁止使用：open(), os.system, os.makedirs, os.rename, os.remove, subprocess, exec, eval

## 文件读写
- 读取文件：pd.read_excel() 读 .xlsx/.xls，pd.read_csv() 读 .csv
- 写入文件：df.to_excel() 或 df.to_csv()，不要用 open()
- 输入文件路径：os.path.join(INPUTS_DIR, 文件名)
- 输出文件路径：os.path.join(OUTPUTS_DIR, 文件名)
- 输出文件名要有意义，比如 "结果_原文件名.xlsx"

## openpyxl 样式复制（重要）
- 不要用 copy() 复制单元格样式，StyleProxy 对象不支持 copy()，会报 unhashable 错误
- 正确做法是直接赋值内部样式：cell._style = ref_cell._style
- 示例：
  ref = ws.cell(row=1, column=1)
  for row in range(2, ws.max_row + 1):
      cell = ws.cell(row=row, column=new_col)
      cell._style = ref._style

## 代码规范
- 如果用户指令中提到了具体文件名，用那个文件；如果没指定，根据可用文件列表推断
- 代码末尾必须将结果摘要赋值给变量 RESULT，这是一个字符串，描述操作结果
- 只返回纯 Python 代码，不要包含 markdown 标记或解释文字
- 禁止访问 INPUTS_DIR 和 OUTPUTS_DIR 之外的任何路径"""


def _extract_code(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    blocks = re.findall(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
    if blocks:
        return max(blocks, key=len).strip()
    m = re.search(r"```(?:python)?\n(.*)", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    if re.search(r"^(import |pd\.|df[_\s]|RESULT\s*=)", text, re.MULTILINE):
        return text
    return ""


def _build_api_kwargs(deep_thinking: bool) -> dict:
    if deep_thinking:
        return {
            "model": "deepseek-v4-pro",
            "max_tokens": 8192,
            "reasoning_effort": "high",
            "extra_body": {"thinking": {"type": "enabled"}},
        }
    return {
        "model": "deepseek-v4-pro",
        "max_tokens": 8192,
        "temperature": 0,
    }


def generate_code(command: str, input_files: list[str], inputs_dir: str, outputs_dir: str,
                  *, deep_thinking: bool = False) -> str:
    file_list = "\n".join(f"  - {f}" for f in input_files) if input_files else "  (无文件)"

    file_previews = []
    for f in input_files[:5]:
        path = os.path.join(inputs_dir, f)
        try:
            if f.endswith(".csv"):
                df = pd.read_csv(path, nrows=5)
            else:
                df = pd.read_excel(path, nrows=5)
            file_previews.append(f"文件 {f} 的前5行:\n{df.to_string()}\n列名: {list(df.columns)}")
        except Exception:
            file_previews.append(f"文件 {f}: 无法预览")

    preview_text = "\n\n".join(file_previews) if file_previews else "无可预览文件"

    user_msg = f"""可用文件列表:
{file_list}

文件预览:
{preview_text}

INPUTS_DIR = "{inputs_dir}"
OUTPUTS_DIR = "{outputs_dir}"

用户指令: {command}"""

    api_kwargs = _build_api_kwargs(deep_thinking)
    resp = _get_client().chat.completions.create(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        **api_kwargs,
    )

    import sys as _sys
    if deep_thinking:
        reasoning = getattr(resp.choices[0].message, "reasoning_content", None)
        if reasoning:
            print(f"[DeepSeek] thinking: {reasoning[:200]}...", file=_sys.stderr)
    print(f"[DeepSeek] model={resp.model} deep_thinking={deep_thinking}", file=_sys.stderr)

    code = _extract_code(resp.choices[0].message.content or "")
    if not code:
        raise ValueError("AI 未返回有效代码")

    return code


def fix_code(original_code: str, error_msg: str, command: str,
             input_files: list[str], inputs_dir: str, outputs_dir: str,
             *, deep_thinking: bool = False) -> str:
    file_list = "\n".join(f"  - {f}" for f in input_files) if input_files else "  (无文件)"

    allowed = ", ".join(sorted(ALLOWED_MODULES))

    user_msg = f"""之前生成的代码执行报错了，请修复。

用户原始指令: {command}

可用文件列表:
{file_list}

INPUTS_DIR = "{inputs_dir}"
OUTPUTS_DIR = "{outputs_dir}"

执行环境限制:
- 只能 import 以下模块: {allowed}
- 禁止使用 os.system, subprocess, exec, eval
- os 只能用 os.path.join, os.path.exists, os.path.basename, os.path.splitext, os.listdir

之前生成的代码:
```python
{original_code}
```

执行报错信息:
{error_msg}

请修复代码并返回完整的可执行代码。"""

    api_kwargs = _build_api_kwargs(deep_thinking)
    resp = _get_client().chat.completions.create(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        **api_kwargs,
    )

    code = _extract_code(resp.choices[0].message.content or "")
    if not code:
        raise ValueError("AI 未返回有效修复代码")

    return code


def match_script_filenames(code: str, input_files: list[str], inputs_dir: str, outputs_dir: str) -> str:
    if not input_files:
        return code

    file_list = "\n".join(f"  - {f}" for f in input_files)
    user_msg = f"""你将收到一段 Python 脚本，脚本中可能包含具体的输入文件名和输出文件名。

当前可用输入文件:
{file_list}

请根据当前可用输入文件，自动调整脚本中的文件路径，使脚本在当前 INPUTS_DIR 和 OUTPUTS_DIR 下可执行。
- 保持原始数据处理逻辑不变。
- 只修改或替换文件名和文件路径，不改变其他代码。
- 输入文件必须来自当前可用输入文件列表。
- 输出文件仍然写入 OUTPUTS_DIR，并尽量使用合理的输出文件名。
- 如果脚本使用了旧输入文件名，请替换为最匹配的当前输入文件名。
- 不要添加额外解释或 markdown，只返回完整 Python 代码。

脚本代码:
```python
{code}
```
"""

    api_kwargs = _build_api_kwargs(False)
    resp = _get_client().chat.completions.create(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        **api_kwargs,
    )

    matched_code = _extract_code(resp.choices[0].message.content or "")
    if not matched_code:
        raise ValueError("AI 未返回有效的匹配脚本代码")

    return matched_code


FORBIDDEN_PATTERNS = [
    r"\bos\.system\b",
    r"\bsubprocess\b",
    r"\bexec\s*\(",
    r"\beval\s*\(",
    r"\bcompile\s*\(",
    r"\bglobals\s*\(",
    r"\blocals\s*\(",
    r"\bbreakpoint\s*\(",
]


def _check_code_safety(code: str):
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, code):
            raise ValueError(f"代码包含禁止的操作: {pattern}")


ALLOWED_MODULES = {
    "pandas", "numpy", "copy", "openpyxl", "openpyxl.utils", "openpyxl.styles",
    "openpyxl.worksheet", "openpyxl.chart",
    "datetime", "math", "re", "json", "csv", "collections",
}


def _make_safe_import(restricted_os):
    def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in ("os", "os.path"):
            return restricted_os
        if name not in ALLOWED_MODULES:
            raise ImportError(f"not allowed to import '{name}'")
        return __builtins__["__import__"](name, globals, locals, fromlist, level)
    return _safe_import


def execute_code(code: str, inputs_dir: str, outputs_dir: str) -> str:
    _check_code_safety(code)

    restricted_os = _RestrictedOs(inputs_dir, outputs_dir)
    safe_builtins = {
        "__import__": _make_safe_import(restricted_os),
        "print": lambda *a, **kw: None,
        "len": len,
        "list": list,
        "dict": dict,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "tuple": tuple,
        "set": set,
        "range": range,
        "enumerate": enumerate,
        "zip": zip,
        "map": map,
        "filter": filter,
        "sorted": sorted,
        "all": all,
        "any": any,
        "sum": sum,
        "min": min,
        "max": max,
        "abs": abs,
        "round": round,
        "isinstance": isinstance,
        "type": type,
        "ValueError": ValueError,
        "TypeError": TypeError,
        "KeyError": KeyError,
        "IndexError": IndexError,
        "ImportError": ImportError,
        "Exception": Exception,
        "format": format,
        "repr": repr,
        "True": True,
        "False": False,
        "None": None,
    }
    safe_globals = {
        "__builtins__": safe_builtins,
        "pd": pd,
        "os": restricted_os,
        "INPUTS_DIR": inputs_dir,
        "OUTPUTS_DIR": outputs_dir,
        "RESULT": "",
    }

    exec(code, safe_globals)
    return safe_globals.get("RESULT", "执行完成，但未设置 RESULT 变量")


class _RestrictedOs:
    """Only expose os.path.join with directory validation."""

    def __init__(self, inputs_dir, outputs_dir):
        self._allowed = (os.path.abspath(inputs_dir), os.path.abspath(outputs_dir))
        self.path = _RestrictedOsPath(self._allowed)

    def listdir(self, path):
        abspath = os.path.abspath(path)
        if not any(abspath.startswith(d) for d in self._allowed):
            raise PermissionError(f"不允许访问目录: {path}")
        return os.listdir(path)


class _RestrictedOsPath:
    def __init__(self, allowed_dirs):
        self._allowed = allowed_dirs

    def join(self, *args):
        result = os.path.join(*args)
        abspath = os.path.abspath(result)
        if not any(abspath.startswith(d) for d in self._allowed):
            raise PermissionError(f"不允许访问路径: {result}")
        return result

    def exists(self, path):
        abspath = os.path.abspath(path)
        if not any(abspath.startswith(d) for d in self._allowed):
            raise PermissionError(f"不允许访问路径: {path}")
        return os.path.exists(path)

    def basename(self, path):
        return os.path.basename(path)

    def splitext(self, path):
        return os.path.splitext(path)


def preview_excel(filepath: str, max_rows: int = 20) -> dict:
    if filepath.endswith(".csv"):
        df = pd.read_csv(filepath, nrows=max_rows)
    else:
        df = pd.read_excel(filepath, nrows=max_rows)

    return {
        "columns": list(df.columns),
        "rows": df.fillna("").values.tolist(),
        "total_rows": len(df),
        "shape": list(df.shape),
    }
