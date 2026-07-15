PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
PRODUCT ?= centos-stream-9-x86_64-ext4
CANDIDATE_PRODUCT ?= eks-admin-bastion-al2023-x86_64
AMI ?=
ACCESS_ROLE_ARN ?=

.PHONY: validate-config list-products list-candidates resolve-source resolve-candidate-source build build-candidate validate-ami render-add-version render-create-product submit-validate

validate-config:
	$(PYTHON) scripts/list_allowed_products.py >/dev/null
	packer fmt -check packer/marketplace-ami.pkr.hcl
	packer validate -syntax-only packer/marketplace-ami.pkr.hcl

list-products:
	$(PYTHON) scripts/list_allowed_products.py

list-candidates:
	CORENOVA_PRODUCTS_FILE=products.candidates.yaml $(PYTHON) scripts/list_allowed_products.py

resolve-source:
	$(PYTHON) scripts/resolve_source_ami.py $(PRODUCT)

resolve-candidate-source:
	CORENOVA_PRODUCTS_FILE=products.candidates.yaml $(PYTHON) scripts/resolve_source_ami.py $(CANDIDATE_PRODUCT)

build:
	PYTHON="$(PYTHON)" scripts/build_one.sh $(PRODUCT)

build-candidate:
	PYTHON="$(PYTHON)" scripts/build_candidate.sh $(CANDIDATE_PRODUCT)

validate-ami:
	test -n "$(AMI)"
	$(PYTHON) scripts/validate_ami.py $(PRODUCT) $(AMI)

render-add-version:
	test -n "$(AMI)"
	test -n "$(ACCESS_ROLE_ARN)"
	$(PYTHON) scripts/render_marketplace_changeset.py $(PRODUCT) $(AMI) --access-role-arn "$(ACCESS_ROLE_ARN)"

render-create-product:
	test -n "$(AMI)"
	test -n "$(ACCESS_ROLE_ARN)"
	$(PYTHON) scripts/render_create_ami_product_changeset.py $(CANDIDATE_PRODUCT) $(AMI) --access-role-arn "$(ACCESS_ROLE_ARN)"

submit-validate:
	test -n "$(PLAN)"
	$(PYTHON) scripts/submit_changeset.py "$(PLAN)" --intent VALIDATE
