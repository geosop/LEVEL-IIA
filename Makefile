.PHONY: install smoke verify-smoke all figure tables verify test clean
RUN_HASH ?= $(shell cat outputs/LATEST_RUN.txt 2>/dev/null)

install:
	pip install -e .

smoke:
	python scripts/run_all.py --smoke

verify-smoke:
	python scripts/verify_outputs.py --smoke

all:
	python scripts/run_all.py --all --resume

figure:
	python scripts/make_figure2.py --run-hash $(RUN_HASH)

tables:
	python scripts/make_tables.py --run-hash $(RUN_HASH)

verify:
	python scripts/verify_outputs.py --run-hash $(RUN_HASH)

test:
	pytest -q

clean:
	rm -rf build *.egg-info src/*.egg-info
