import json
import os
import sys
import traceback

from flask import Flask, request, jsonify, render_template, send_from_directory
from dotenv import load_dotenv

from executor import generate_code, execute_code, fix_code, preview_excel, match_script_filenames


def _get_resource_dir():
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def _get_data_dir():
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            return os.path.join(os.path.expanduser("~"), "Documents", "ExcelAssistant")
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


RESOURCE_DIR = _get_resource_dir()
DATA_DIR = _get_data_dir()

load_dotenv(os.path.join(DATA_DIR, ".env"))
load_dotenv(os.path.join(RESOURCE_DIR, ".env"))

app = Flask(__name__, template_folder=os.path.join(RESOURCE_DIR, "templates"),
            static_folder=os.path.join(RESOURCE_DIR, "static"))

INPUTS_DIR = os.path.join(DATA_DIR, "inputs")
OUTPUTS_DIR = os.path.join(DATA_DIR, "outputs")
SCRIPTS_DIR = os.path.join(DATA_DIR, "scripts")

os.makedirs(INPUTS_DIR, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)
os.makedirs(SCRIPTS_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}


def _allowed_file(filename):
    return os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "没有选择文件"}), 400
    f = request.files["file"]
    if not f.filename or not _allowed_file(f.filename):
        return jsonify({"error": "仅支持 .xlsx / .xls / .csv 文件"}), 400
    dest = os.path.join(INPUTS_DIR, f.filename)
    f.save(dest)
    return jsonify({"message": f"文件 {f.filename} 上传成功", "filename": f.filename})


@app.route("/api/files")
def list_files():
    result = {"inputs": [], "outputs": []}
    for name in sorted(os.listdir(INPUTS_DIR)):
        if not name.startswith("."):
            result["inputs"].append(name)
    for name in sorted(os.listdir(OUTPUTS_DIR)):
        if not name.startswith("."):
            result["outputs"].append(name)
    return jsonify(result)


@app.route("/api/import_api_key", methods=["POST"])
def import_api_key():
    body = request.get_json()
    if not body or not body.get("key"):
        return jsonify({"error": "API Key 不能为空"}), 400

    key = body["key"].strip()
    if not key:
        return jsonify({"error": "API Key 不能为空"}), 400

    env_path = os.path.join(DATA_DIR, ".env")
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    updated = False
    for idx, line in enumerate(lines):
        if line.strip().startswith("DEEPSEEK_API_KEY="):
            lines[idx] = f"DEEPSEEK_API_KEY={key}\n"
            updated = True
            break

    if not updated:
        lines.append(f"DEEPSEEK_API_KEY={key}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    os.environ["DEEPSEEK_API_KEY"] = key
    return jsonify({"message": "DeepSeek API Key 已保存"})


@app.route("/api/download/<folder>/<filename>")
def download(folder, filename):
    if folder not in ("inputs", "outputs"):
        return jsonify({"error": "无效目录"}), 400
    directory = INPUTS_DIR if folder == "inputs" else OUTPUTS_DIR
    filepath = os.path.join(directory, filename)
    if not os.path.isfile(filepath):
        return jsonify({"error": "文件不存在"}), 404
    return send_from_directory(directory, filename, as_attachment=True)


@app.route("/api/delete/<folder>/<filename>", methods=["DELETE"])
def delete_file(folder, filename):
    if folder not in ("inputs", "outputs"):
        return jsonify({"error": "无效目录"}), 400
    directory = INPUTS_DIR if folder == "inputs" else OUTPUTS_DIR
    filepath = os.path.join(directory, filename)
    if not os.path.isfile(filepath):
        return jsonify({"error": "文件不存在"}), 404
    os.remove(filepath)
    return jsonify({"message": f"已删除 {filename}"})


@app.route("/api/preview/<folder>/<filename>")
def preview(folder, filename):
    if folder not in ("inputs", "outputs"):
        return jsonify({"error": "无效目录"}), 400
    directory = INPUTS_DIR if folder == "inputs" else OUTPUTS_DIR
    filepath = os.path.join(directory, filename)
    if not os.path.isfile(filepath):
        return jsonify({"error": "文件不存在"}), 404
    try:
        data = preview_excel(filepath, max_rows=20)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/execute", methods=["POST"])
def execute():
    body = request.get_json()
    if not body or not body.get("command"):
        return jsonify({"error": "请输入指令"}), 400

    command = body["command"]
    deep_thinking = body.get("deep_thinking", False)

    input_files = []
    for name in os.listdir(INPUTS_DIR):
        if not name.startswith("."):
            input_files.append(name)

    try:
        code = generate_code(command, input_files, INPUTS_DIR, OUTPUTS_DIR,
                             deep_thinking=deep_thinking)
    except Exception as e:
        return jsonify({"error": f"生成代码失败: {e}"}), 500

    max_retries = min(int(body.get("max_retries", 3)), 10)
    attempts = []
    for attempt in range(max_retries):
        try:
            result = execute_code(code, INPUTS_DIR, OUTPUTS_DIR)
            return jsonify({
                "message": "执行成功",
                "code": code,
                "result": result,
                "attempts": len(attempts) + 1,
                "retry_history": attempts if attempts else None,
            })
        except Exception as e:
            error_msg = traceback.format_exc()
            attempts.append({"code": code, "error": str(e)})

            if attempt < max_retries - 1:
                try:
                    code = fix_code(code, error_msg, command,
                                    input_files, INPUTS_DIR, OUTPUTS_DIR,
                                    deep_thinking=deep_thinking)
                except Exception as fix_err:
                    return jsonify({
                        "error": f"自动纠错失败: {fix_err}",
                        "code": code,
                        "retry_history": attempts,
                    }), 500

    return jsonify({
        "error": f"重试 {max_retries} 次后仍然失败",
        "code": code,
        "retry_history": attempts,
    }), 500


@app.route("/api/scripts", methods=["GET"])
def list_scripts():
    scripts = []
    for name in sorted(os.listdir(SCRIPTS_DIR)):
        if name.endswith(".json"):
            filepath = os.path.join(SCRIPTS_DIR, name)
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            scripts.append({
                "id": name[:-5],
                "name": data.get("name", ""),
                "command": data.get("command", ""),
            })
    return jsonify(scripts)


@app.route("/api/scripts", methods=["POST"])
def save_script():
    body = request.get_json()
    if not body or not body.get("name") or not body.get("code"):
        return jsonify({"error": "name 和 code 不能为空"}), 400

    script_id = body["name"].replace(" ", "_")
    filepath = os.path.join(SCRIPTS_DIR, f"{script_id}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({
            "name": body["name"],
            "command": body.get("command", ""),
            "code": body["code"],
        }, f, ensure_ascii=False, indent=2)
    return jsonify({"message": f"脚本 '{body['name']}' 已保存", "id": script_id})


@app.route("/api/scripts/<script_id>", methods=["DELETE"])
def delete_script(script_id):
    filepath = os.path.join(SCRIPTS_DIR, f"{script_id}.json")
    if not os.path.isfile(filepath):
        return jsonify({"error": "脚本不存在"}), 404
    os.remove(filepath)
    return jsonify({"message": "已删除"})


@app.route("/api/scripts/<script_id>/run", methods=["POST"])
def run_script(script_id):
    filepath = os.path.join(SCRIPTS_DIR, f"{script_id}.json")
    if not os.path.isfile(filepath):
        return jsonify({"error": "脚本不存在"}), 404

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    code = data["code"]
    input_files = [name for name in os.listdir(INPUTS_DIR) if not name.startswith('.')]
    try:
        code = match_script_filenames(code, input_files, INPUTS_DIR, OUTPUTS_DIR)
    except Exception as e:
        return jsonify({"error": f"脚本文件名匹配失败: {e}", "code": code}), 500

    try:
        result = execute_code(code, INPUTS_DIR, OUTPUTS_DIR)
    except Exception as e:
        tb = traceback.format_exc()
        return jsonify({"error": f"执行失败: {e}", "code": code, "traceback": tb}), 500

    return jsonify({"message": "执行成功", "code": code, "result": result})


if __name__ == "__main__":
    import webbrowser
    import threading
    import time
    import signal

    is_frozen = getattr(sys, "frozen", False)
    port = 5001

    if is_frozen:
        _last_heartbeat = time.time()

        @app.route("/api/heartbeat")
        def heartbeat():
            global _last_heartbeat
            _last_heartbeat = time.time()
            return jsonify({"status": "ok"})

        def _watchdog():
            while True:
                time.sleep(30)
                if time.time() - _last_heartbeat > 120:
                    os.kill(os.getpid(), signal.SIGTERM)

        threading.Thread(target=_watchdog, daemon=True).start()
        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{port}")).start()

    app.run(debug=not is_frozen, port=port)
