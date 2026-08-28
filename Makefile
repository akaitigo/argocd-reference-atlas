LABS := application reconciliation sync diff health promotion security failure recovery
ATLAS_CORE ?= ../reference-atlas-core
EVIDENCE_FILES := $(shell find evidence/records -type f -name '*.evidence.yaml' -print 2>/dev/null | sort)

.PHONY: atlas-validate atlas-audit graph-validate skill-validate legal-validate sbom sbom-validate validate check lab-env lab-clean labs labs-dry-run labs-static $(addprefix lab-,$(LABS))

atlas-validate:
	test -f "$(ATLAS_CORE)/cmd/atlas/main.go"
	cd "$(ATLAS_CORE)" && GOCACHE="$(CURDIR)/.cache/go-build" go run ./cmd/atlas validate \
		"$(CURDIR)/atlas.yaml" \
		"$(CURDIR)/mastery.yaml" \
		"$(CURDIR)/sources.lock.yaml" \
		"$(CURDIR)/coverage.yaml" \
		"$(CURDIR)/skill.package.yaml" $(foreach file,$(EVIDENCE_FILES),"$(CURDIR)/$(file)")

atlas-audit:
	cd "$(ATLAS_CORE)" && GOCACHE="$(CURDIR)/.cache/go-build" go run ./cmd/atlas audit "$(CURDIR)"

graph-validate:
	python3 scripts/validate_graph.py

skill-validate:
	python3 scripts/validate_router_evals.py

legal-validate:
	python3 scripts/validate_legal.py

sbom:
	python3 scripts/generate_sbom.py

sbom-validate:
	python3 scripts/generate_sbom.py --check

validate: atlas-validate atlas-audit graph-validate skill-validate legal-validate sbom-validate labs-static

check: validate

lab-env:
	./scripts/environment.sh setup

lab-clean:
	./scripts/environment.sh cleanup

labs: lab-env
	@set -e; for lab in $(LABS); do ./scripts/run-suite.sh "$$lab"; done

$(addprefix lab-,$(LABS)): lab-env
	./scripts/run-suite.sh "$(@:lab-%=%)"

labs-dry-run:
	@set -e; for lab in $(LABS); do \
		for phase in setup execute verify cleanup; do ./scripts/run-lab.sh "$$lab" "$$phase" --dry-run; done; \
	done

labs-static:
	./tests/labs/static.sh
