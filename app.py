import os
import sys
import traceback

from flask import Flask, request, jsonify, render_template, send_from_directory
from dotenv import load_dotenv

from executor import generate_code, execute_code, preview_excel


def _get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = _get_base_dir()

load_dotenv(os.path.join(BASE_DIR, ".env"))

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"),
            static_folder=os.path.join(BASE_DIR, "static"))

INPUTS_DIR = os.path.join(BASE_DIR, "inputs")
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")

os.makedirs(INPUTS_DIR, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)

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

    input_files = []
    for name in os.listdir(INPUTS_DIR):
        if not name.startswith("."):
            input_files.append(name)

    try:
        code = generate_code(command, input_files, INPUTS_DIR, OUTPUTS_DIR)
    except Exception as e:
        return jsonify({"error": f"生成代码失败: {e}"}), 500

    try:
        result = execute_code(code, INPUTS_DIR, OUTPUTS_DIR)
    except Exception as e:
        tb = traceback.format_exc()
        return jsonify({
            "error": f"执行失败: {e}",
            "code": code,
            "traceback": tb,
        }), 500

    return jsonify({
        "message": "执行成功",
        "code": code,
        "result": result,
    })


if __name__ == "__main__":
    import webbrowser
    import threading

    is_frozen = getattr(sys, "frozen", False)
    port = 5001

    if is_frozen:
        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{port}")).start()

    app.run(debug=not is_frozen, port=port)
