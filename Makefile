PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
CFN_LINT ?= $(if $(wildcard .venv/bin/cfn-lint),.venv/bin/cfn-lint,cfn-lint)
PRODUCT ?= centos-stream-9-x86_64-ext4
CANDIDATE_PRODUCT ?= eks-admin-bastion-al2023-x86_64
AMI ?=
ACCESS_ROLE_ARN ?=
ASSET_BASE_URL ?=

.PHONY: validate-config validate-eks-delivery test-eks-delivery package-eks-delivery list-products list-candidates resolve-source resolve-candidate-source build build-candidate validate-ami render-add-version render-eks-add-version render-create-product render-add-instance-types submit-validate

validate-config:
	$(PYTHON) scripts/list_allowed_products.py >/dev/null
	packer fmt -check packer/marketplace-ami.pkr.hcl
	packer validate -syntax-only packer/marketplace-ami.pkr.hcl

validate-eks-delivery:
	$(PYTHON) scripts/validate_eks_admin_delivery_assets.py
	$(CFN_LINT) \
		marketplace/eks-admin-bastion/cloudformation/identity-relay.yaml \
		marketplace/eks-admin-bastion/cloudformation/audited-workstation.yaml \
		marketplace/eks-admin-bastion/tests/e2e-environment.yaml

test-eks-delivery: validate-eks-delivery
	$(PYTHON) -m unittest discover -s tests -p 'test_eks_*.py' -v

package-eks-delivery: test-eks-delivery
	$(PYTHON) scripts/package_eks_admin_delivery_assets.py

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

render-eks-add-version:
	test -n "$(AMI)"
	test -n "$(ACCESS_ROLE_ARN)"
	test -n "$(ASSET_BASE_URL)"
	$(PYTHON) scripts/render_marketplace_changeset.py $(PRODUCT) $(AMI) --access-role-arn "$(ACCESS_ROLE_ARN)" --include-eks-cloudformation --asset-base-url "$(ASSET_BASE_URL)"

render-create-product:
	test -n "$(AMI)"
	test -n "$(ACCESS_ROLE_ARN)"
	$(PYTHON) scripts/render_create_ami_product_changeset.py $(CANDIDATE_PRODUCT) $(AMI) --access-role-arn "$(ACCESS_ROLE_ARN)"

render-add-instance-types:
	CORENOVA_PRODUCTS_FILE=products.candidates.yaml $(PYTHON) scripts/render_add_instance_types_changeset.py $(CANDIDATE_PRODUCT)

submit-validate:
	test -n "$(PLAN)"
	$(PYTHON) scripts/submit_changeset.py "$(PLAN)" --intent VALIDATE
