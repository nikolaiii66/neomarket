.PHONY: test-b2b test-moderation test-b2c test

test-b2b:
	cd services/b2b && python3 -m pytest -q

test-moderation:
	cd services/moderation && python3 -m pytest -q

test-b2c:
	cd services/b2c && python3 -m pytest -q

test: test-b2b test-moderation test-b2c
