PYTHON ?= python3
DATE ?=
REFRESH ?=

.PHONY: demo run refresh-hero site test

demo:
	PYTHONPATH=src $(PYTHON) -m tistory_newsroom run --demo $(if $(DATE),--date $(DATE),)

run:
	PYTHONPATH=src $(PYTHON) -m tistory_newsroom run $(if $(DATE),--date $(DATE),) $(if $(REFRESH),--refresh,)

refresh-hero:
	PYTHONPATH=src $(PYTHON) -m tistory_newsroom refresh-hero $(if $(DATE),--date $(DATE),)

site:
	PYTHONPATH=src $(PYTHON) -m tistory_newsroom build-site

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v
