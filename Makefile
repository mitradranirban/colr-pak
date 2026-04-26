VENV ?= venv
PYTHON ?= python3
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python
PYINSTALLER := $(VENV)/bin/pyinstaller
SPEC ?= ColrPak.spec

ifeq ($(OS),Windows_NT)
PIP := $(VENV)/Scripts/pip.exe
PY := $(VENV)/Scripts/python.exe
PYINSTALLER := $(VENV)/Scripts/pyinstaller.exe
endif

.PHONY: all venv install build clean rebuild help

all: build

venv:
	@if [ ! -x "$(PY)" ]; then \
		echo "Creating virtual environment in $(VENV)"; \
		$(PYTHON) -m venv $(VENV); \
	else \
		echo "Virtual environment already exists at $(VENV)"; \
	fi

install: venv
	$(PY) -m pip install --upgrade pip
	$(PIP) install -r requirements.txt

build: install
	$(PYINSTALLER) $(SPEC)

rebuild: clean build

clean:
	rm -rf build dist *.spec.bak __pycache__

help:
	@echo "Targets:"
	@echo "  make          - create venv if needed, install requirements, build PyInstaller app"
	@echo "  make venv     - create virtual environment"
	@echo "  make install  - install/update dependencies into the venv"
	@echo "  make build    - run the full build"
	@echo "  make rebuild  - clean and build again"
	@echo "  make clean    - remove build artifacts"
	@echo ""
	@echo "Variables:"
	@echo "  VENV=venv         virtual environment directory"
	@echo "  PYTHON=python3    python used to create the venv"
	@echo "  SPEC=ColrPak.spec PyInstaller spec file"
