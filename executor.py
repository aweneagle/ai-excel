import os
import re

import pandas as pd
from openai import OpenAI

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
        )
    return _client

SYSTEM_PROMPT = """你是一个 Python 数据处理助手。用户会给你一条自然语言指令，要求对 Excel/CSV 文件进行操作。

你必须生成一段可直接执行的 Python 代码，遵循以下规则：
1. 只能使用 pandas 和 openpyxl 库，不要导入其他库
2. 输入文件在 INPUTS_DIR 目录下，输出文件保存到 OUTPUTS_DIR 目录下
3. INPUTS_DIR 和 OUTPUTS_DIR 会作为变量注入，直接使用即可
4. 输出文件名要有意义，比如 "结果_原文件名.xlsx"
5. 代码末尾必须将结果摘要赋值给变量 RESULT，这是一个字符串，描述操作结果
6. 只返回纯 Python 代码，不要包含 markdown 标记或解释文字
7. 用 pd.read_excel() 读取 .xlsx/.xls，用 pd.read_csv() 读取 .csv
8. 如果用户指令中提到了具体文件名，用那个文件；如果没指定，根据可用文件列表推断
9. 禁止使用 os.system, subprocess, exec, eval, __import__, open (用 pandas 的 IO 方法代替)
10. 禁止访问 INPUTS_DIR 和 OUTPUTS_DIR 之外的任何路径"""


def generate_code(command: str, input_files: list[str], inputs_dir: str, outputs_dir: str) -> str:
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

    user_msg = f"""{SYSTEM_PROMPT}

可用文件列表:
{file_list}

文件预览:
{preview_text}

INPUTS_DIR = "{inputs_dir}"
OUTPUTS_DIR = "{outputs_dir}"

用户指令: {command}"""

    resp = _get_client().chat.completions.create(
        model="deepseek-reasoner",
        messages=[
            {"role": "user", "content": user_msg},
        ],
        max_tokens=4096,
    )

    import sys as _sys
    print(f"[DeepSeek] model used: {resp.model}", file=_sys.stderr)

    code = resp.choices[0].message.content.strip()
    if code.startswith("```"):
        code = re.sub(r"^```(?:python)?\n?", "", code)
        code = re.sub(r"\n?```$", "", code)

    return code


def fix_code(original_code: str, error_msg: str, command: str,
             input_files: list[str], inputs_dir: str, outputs_dir: str) -> str:
    file_list = "\n".join(f"  - {f}" for f in input_files) if input_files else "  (无文件)"

    user_msg = f"""之前生成的代码执行报错了，请修复。

用户原始指令: {command}

可用文件列表:
{file_list}

INPUTS_DIR = "{inputs_dir}"
OUTPUTS_DIR = "{outputs_dir}"

之前生成的代码:
```python
{original_code}
```

执行报错信息:
{error_msg}

请修复代码并返回完整的可执行代码。"""

    fix_msg = f"""{SYSTEM_PROMPT}

{user_msg}"""

    resp = _get_client().chat.completions.create(
        model="deepseek-reasoner",
        messages=[
            {"role": "user", "content": fix_msg},
        ],
        max_tokens=4096,
    )

    code = resp.choices[0].message.content.strip()
    if code.startswith("```"):
        code = re.sub(r"^```(?:python)?\n?", "", code)
        code = re.sub(r"\n?```$", "", code)

    return code


FORBIDDEN_PATTERNS = [
    r"\bos\.system\b",
    r"\bsubprocess\b",
    r"\b__import__\b",
    r"\bexec\s*\(",
    r"\beval\s*\(",
    r"\bopen\s*\(",
    r"\bcompile\s*\(",
    r"\bglobals\s*\(",
    r"\blocals\s*\(",
    r"\bgetattr\s*\(",
    r"\bsetattr\s*\(",
    r"\bdelattr\s*\(",
    r"\bbreakpoint\s*\(",
]


def _check_code_safety(code: str):
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, code):
            raise ValueError(f"代码包含禁止的操作: {pattern}")


def _strip_imports(code: str) -> str:
    lines = code.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def execute_code(code: str, inputs_dir: str, outputs_dir: str) -> str:
    _check_code_safety(code)
    code = _strip_imports(code)

    safe_globals = {"__builtins__": {}}
    safe_locals = {
        "pd": pd,
        "os": _RestrictedOs(inputs_dir, outputs_dir),
        "INPUTS_DIR": inputs_dir,
        "OUTPUTS_DIR": outputs_dir,
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
        "Exception": Exception,
        "format": format,
        "repr": repr,
        "RESULT": "",
    }

    exec(code, safe_globals, safe_locals)
    return safe_locals.get("RESULT", "执行完成，但未设置 RESULT 变量")


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
