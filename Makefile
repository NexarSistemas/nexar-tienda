.PHONY: install run clean

VENV := venv
BIN := $(VENV)/bin
PYTHON := $(BIN)/python3
PIP := $(BIN)/pip

install:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(PYTHON) -c "import database; database.init_db()"

run:
	$(PYTHON) app.py

clean:
	rm -rf $(VENV)
	find . -type d -name "__pycache__" -exec rm -rf {} +