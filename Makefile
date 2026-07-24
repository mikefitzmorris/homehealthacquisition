.PHONY: install test lint run smoke clean

install:
	pip install -e ".[dev]"

test:
	pytest -q

lint:
	ruff check .

## Full pipeline: discover dataset ids, download, build the panel.
run:
	hhpanel run

## Same thing, but only the first page of each file -- proves the wiring
## works against the live API in about 30 seconds.
smoke:
	hhpanel run --max-pages 1

clean:
	rm -rf data/cache data/interim data/processed
