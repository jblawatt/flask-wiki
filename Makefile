#!/usr/bin/env make

vendor:
	bower install jquery
	bower install bootstrap
	bower install ace

pythonenv:
	python3 -m venv pythonenv
	pythonenv/bin/pip install -r requirements.txt -requirements-dev.txt --upgrade

serve: pythonenv
	WERKZEUG_DEBUG_PIN=off pythonenv/bin/python wiki.py