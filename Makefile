#!/usr/bin/env make

vendor:
	bower install jquery
	bower install bootstrap
	bower install ace

pythonenv:
	python3 -m venv pythonenv
	pythonenv/bin/pip install -r requirements.txt -r requirements-dev.txt --upgrade

serve: 
	WERKZEUG_DEBUG_PIN=off pythonenv/bin/python wiki.py


assets:
	FLASK_APP=wiki.py flask assets build


clean:
	rm -rf


.PHONY: pythonenv
