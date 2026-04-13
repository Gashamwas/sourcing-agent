SHELL := /bin/zsh

ROOT := $(abspath $(CURDIR))
PYTHON ?= python3

HEAD_AI_BRIEF ?= $(ROOT)/config/brief-head-ai-lab-nyc-v2.json
HEAD_AI_RUN_DIR ?= $(ROOT)/output/runs/linkedin/1957683706/imported-2026-04-09T21-22-22-384264+00-00__legacy-2
HEAD_AI_SEARCH_MEMORY ?= $(HEAD_AI_RUN_DIR)/search_memory-1957683706.json
HEAD_AI_FINAL_JUDGMENTS ?= $(HEAD_AI_RUN_DIR)/final_judgments.jsonl

FDE_BRIEF ?= $(ROOT)/config/Forward-Deployed-Engineer-NYC/brief-forward-deployed-engineer-us-v1.4.json
FDE_RUN_DIR ?= $(ROOT)/output/runs/linkedin/1990251114/2026-04-12T12-26-33-178377+00-00__run-3
FDE_SEARCH_MEMORY ?= $(FDE_RUN_DIR)/search_memory-1990251114.json
FDE_FINAL_JUDGMENTS ?= $(FDE_RUN_DIR)/final_judgments.jsonl

.PHONY: help head-ai-mi head-ai-brief fde-mi fde-brief

help: ## Show available shortcuts
	@printf "\nAvailable shortcuts:\n\n"
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z0-9_-]+:.*## / {printf "  make %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf "\nOverride any path if needed, e.g.:\n"
	@printf "  make head-ai-mi HEAD_AI_RUN_DIR=/abs/path/to/other/run\n\n"

head-ai-mi: ## Run Head of Applied AI market intel with external research
	$(PYTHON) tools/update_market_intel.py \
		--brief $(HEAD_AI_BRIEF) \
		--run-dir $(HEAD_AI_RUN_DIR) \
		--mode post_run \
		--with-external-research \
		--force-external-research \
		--force-edge-case-research \
		--heuristic-planner

head-ai-brief: ## Update the Head of Applied AI brief using the latest market intel
	$(PYTHON) -m tools.iterate_brief \
		--brief $(HEAD_AI_BRIEF) \
		--report $(HEAD_AI_RUN_DIR)/run-report.json \
		--search-memory $(HEAD_AI_SEARCH_MEMORY) \
		--final-judgments $(HEAD_AI_FINAL_JUDGMENTS) \
		--output-dir $(ROOT)/output

fde-mi: ## Run FDE market intel with external research on the latest known run
	$(PYTHON) tools/update_market_intel.py \
		--brief $(FDE_BRIEF) \
		--run-dir $(FDE_RUN_DIR) \
		--mode post_run \
		--with-external-research \
		--force-external-research \
		--force-edge-case-research \
		--heuristic-planner

fde-brief: ## Update the FDE brief using the latest market intel
	$(PYTHON) -m tools.iterate_brief \
		--brief $(FDE_BRIEF) \
		--report $(FDE_RUN_DIR)/run-report.json \
		--search-memory $(FDE_SEARCH_MEMORY) \
		--final-judgments $(FDE_FINAL_JUDGMENTS) \
		--output-dir $(ROOT)/output
