LABS := application reconciliation sync diff health promotion security failure recovery
EXTENDED_LABS := architecture applicationset connection hook-wave access-boundary observability drift auto-recovery operations notifications
ISOLATED_LABS := high-availability upgrade-migration
ATLAS_CORE ?= ../reference-atlas-core
EVIDENCE_FILES := $(shell find evidence/records -type f -name '*.evidence.yaml' -print 2>/dev/null | sort)
CLAIM_FILES := $(shell find claims -type f -name '*.claim.yaml' -print 2>/dev/null | sort)
SKILL_EVAL_FILES := $(shell find evals -type f -name '*.skill-eval.json' -print 2>/dev/null | sort)
CORE_V1_FILES := migrations/core-v1.yaml provenance.yaml $(wildcard evidence/completion-certificate.json)

.PHONY: atlas-validate atlas-audit graph-validate definitive-validate scenario-proofs scenario-proofs-validate authority-locators authority-validate non-regression-validate evidence-validate skill-validate skill-definitive-eval legal-validate sbom sbom-validate core-v1-graph core-v1-provenance validate check lab-env lab-clean labs labs-dry-run labs-static extended-labs isolated-labs extended-labs-dry-run skill-forward-eval $(addprefix lab-,$(LABS)) $(addprefix extended-lab-,$(EXTENDED_LABS) $(ISOLATED_LABS))

atlas-validate:
	test -f "$(ATLAS_CORE)/cmd/atlas/main.go"
	cd "$(ATLAS_CORE)" && GOCACHE="$(CURDIR)/.cache/go-build" go run ./cmd/atlas validate \
		"$(CURDIR)/atlas.yaml" \
		"$(CURDIR)/mastery.yaml" \
		"$(CURDIR)/sources.lock.yaml" \
		"$(CURDIR)/coverage.yaml" \
		"$(CURDIR)/skill.package.yaml" \
		$(foreach file,$(CLAIM_FILES) $(EVIDENCE_FILES) $(SKILL_EVAL_FILES) $(CORE_V1_FILES),"$(CURDIR)/$(file)")

atlas-audit:
	cd "$(ATLAS_CORE)" && GOCACHE="$(CURDIR)/.cache/go-build" go run ./cmd/atlas audit "$(CURDIR)"

graph-validate:
	python3 scripts/validate_graph.py

definitive-validate:
	python3 scripts/validate_definitive_inventory.py
	python3 scripts/validate_scenario_proofs.py

scenario-proofs:
	python3 scripts/generate_scenario_proofs.py

scenario-proofs-validate:
	python3 scripts/validate_scenario_proofs.py

authority-locators:
	python3 scripts/generate_authority_locators.py --source-tree /private/tmp/argo-cd-v3.5.2-source
	python3 scripts/generate_authority_body_inventory.py --source-tree /private/tmp/argo-cd-v3.5.2-source
	python3 scripts/generate_authority_review_queue.py

authority-validate:
	python3 scripts/validate_authority_locators.py
	python3 scripts/validate_authority_body_inventory.py
	python3 scripts/validate_authority_review_queue.py
	python3 scripts/test_authority_review_queue.py

non-regression-validate:
	python3 scripts/validate_non_regression.py

evidence-validate:
	python3 scripts/validate_evidence_artifacts.py

skill-validate:
	python3 scripts/validate_router_evals.py
	python3 scripts/validate_definitive_skill_eval.py

skill-definitive-eval:
	python3 scripts/generate_skill_mastery_contract.py
	python3 scripts/generate_definitive_skill_eval.py
	python3 scripts/generate_definitive_skill_evidence.py

legal-validate:
	python3 scripts/validate_legal.py

sbom:
	python3 scripts/generate_sbom.py

sbom-validate:
	python3 scripts/generate_sbom.py --check

core-v1-graph:
	python3 scripts/generate_core_v1_metadata.py graph

core-v1-provenance:
	python3 scripts/generate_core_v1_metadata.py provenance

validate: atlas-validate atlas-audit graph-validate definitive-validate authority-validate non-regression-validate evidence-validate skill-validate legal-validate sbom-validate labs-static

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
	./tests/labs/extended-static.sh

extended-labs: lab-env
	@set -e; for lab in $(EXTENDED_LABS); do ./scripts/extended/run-suite.sh "$$lab"; done

isolated-labs:
	@set -e; for lab in $(ISOLATED_LABS); do ./scripts/extended/run-suite.sh "$$lab"; done

$(addprefix extended-lab-,$(EXTENDED_LABS)): lab-env
	./scripts/extended/run-suite.sh "$(@:extended-lab-%=%)"

$(addprefix extended-lab-,$(ISOLATED_LABS)):
	./scripts/extended/run-suite.sh "$(@:extended-lab-%=%)"

extended-labs-dry-run:
	@set -e; for lab in $(EXTENDED_LABS) $(ISOLATED_LABS); do \
		for phase in setup execute verify cleanup; do ./scripts/extended/run.sh "$$lab" "$$phase" --dry-run; done; \
	done

skill-forward-eval:
	python3 scripts/grade_skill_forward_eval.py /private/tmp/argocd-atlas-independent-eval.json evidence/raw/evidence.skill-eval.v3-5-2/result.json
	python3 scripts/evidence/record_extended.py skill-eval
