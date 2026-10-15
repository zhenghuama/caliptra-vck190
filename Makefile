PYTHON ?= python3
BOARD_HOST ?= ubuntu@192.168.77.2
CALIPTRA_SRC ?= $(CURDIR)/work/caliptra-sw
export BOARD_HOST CALIPTRA_SRC

.PHONY: smoke-casa smoke-casa-results test-infra
smoke-casa:
	$(PYTHON) scripts/smoke-casa.py

smoke-casa-results:
	$(PYTHON) scripts/smoke-casa.py --collect-run "$(RUN)"

test-infra:
	$(PYTHON) -m unittest discover -s tests -v
