OCB ?= builder
OCB_VERSION := 0.149.0
CONFIG := builder-config.yaml
COLLECTOR_CONFIG := collector-config.yaml
BUILD_DIR := ./build
BINARY := $(BUILD_DIR)/code-reviewer-collector

.PHONY: install-ocb build run clean

install-ocb:
	go install go.opentelemetry.io/collector/cmd/builder@v$(OCB_VERSION)

build:
	$(OCB) --config $(CONFIG)

run: build
	env $$(grep -v '^\s*#' ../.env | xargs) $(BINARY) --config $(COLLECTOR_CONFIG)

clean:
	rm -rf $(BUILD_DIR)
