PYTHON ?= python3
DATE ?=
REFRESH ?=

.PHONY: demo run site test

demo:
	PYTHONPATH=src $(PYTHON) -m tistory_newsroom run --demo $(if $(DATE),--date $(DATE),)

run:
	PYTHONPATH=src $(PYTHON) -m tistory_newsroom run $(if $(DATE),--date $(DATE),) $(if $(REFRESH),--refresh,)

site:
	PYTHONPATH=src $(PYTHON) -m tistory_newsroom build-site

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v
