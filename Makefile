VERSION = 1.0.0
IMAGE_NAME ?= wonkyto/ubnt-switch-collector:$(VERSION)

build:
	docker build -t $(IMAGE_NAME) .
flake8:
	docker-compose run --rm flake8
run:
	docker-compose run --rm run
test:
	docker-compose run --rm test
