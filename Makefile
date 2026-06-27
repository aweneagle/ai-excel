VENV := venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PORT := 5001

$(VENV):
	python3 -m venv $(VENV)
	$(PIP) install -r requirements.txt

.PHONY: run clean

run: $(VENV)
	$(PYTHON) main.py

clean:
	rm -rf $(VENV) __pycache__
