# K8s AIOps Copilot Makefile

IMAGE_REPOSITORY := xnet.registry.io:8443
PROJECT := xnet-cloud
IMAGE_NAME := aiops-copilot
DOCKER_NAME := $(IMAGE_REPOSITORY)/$(PROJECT)/$(IMAGE_NAME)

VERSION ?= $(shell cat VERSION)
DOCKER_TAG := $(VERSION)

.PHONY: build push deploy delete sync-version

build:
	@echo "Building $(DOCKER_NAME):$(DOCKER_TAG)..."
	docker build -t $(DOCKER_NAME):$(DOCKER_TAG) .

push:
	@echo "Pushing $(DOCKER_NAME):$(DOCKER_TAG)..."
	docker push $(DOCKER_NAME):$(DOCKER_TAG)

deploy:
	@echo "Deploying $(DOCKER_NAME):$(DOCKER_TAG)..."
	@kubectl create namespace aiops --dry-run=client -o yaml | kubectl apply -f -
	@sleep 1
	kubectl apply -f deploy/ --recursive
	@echo "Updating image to $(DOCKER_TAG)..."
	kubectl set image deployment/aiops-copilot -n aiops aiops-copilot=$(DOCKER_NAME):$(DOCKER_TAG)

delete:
	@echo "Deleting (keeping namespace)..."
	kubectl delete -f deploy/k8s-simple.yaml --ignore-not-found
	kubectl delete -f deploy/secrets/ --recursive --ignore-not-found
	kubectl delete -f deploy/configmap/ --recursive --ignore-not-found

# 同步 VERSION 到 k8s-simple.yaml
sync-version:
	@echo "Syncing version to $(DOCKER_TAG)..."
	sed -i 's|image: $(IMAGE_REPOSITORY)/$(PROJECT)/$(IMAGE_NAME):.*|image: $(DOCKER_NAME):$(DOCKER_TAG)|' deploy/k8s-simple.yaml
