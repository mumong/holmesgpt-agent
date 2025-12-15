# K8s AIOps Copilot Makefile

IMAGE_REPOSITORY := xnet.registry.io:8443
PROJECT := xnet-cloud
IMAGE_NAME := aiops-copilot
DOCKER_NAME := $(IMAGE_REPOSITORY)/$(PROJECT)/$(IMAGE_NAME)

VERSION ?= $(shell cat VERSION)
DOCKER_TAG := $(VERSION)

.PHONY: build push deploy delete restart logs sync-version

build:
	@echo "Building $(DOCKER_NAME):$(DOCKER_TAG)..."
	docker build -t $(DOCKER_NAME):$(DOCKER_TAG) .

push:
	@echo "Pushing $(DOCKER_NAME):$(DOCKER_TAG)..."
	docker push $(DOCKER_NAME):$(DOCKER_TAG)

deploy:
	@echo "Deploying $(DOCKER_NAME):$(DOCKER_TAG)..."
	# 1. 同步版本到 k8s-simple.yaml
	@sed -i 's|image: $(IMAGE_REPOSITORY)/$(PROJECT)/$(IMAGE_NAME):.*|image: $(DOCKER_NAME):$(DOCKER_TAG)|' deploy/k8s-simple.yaml
	# 2. 创建 namespace（如果不存在）
	@kubectl create namespace aiops --dry-run=client -o yaml | kubectl apply -f -
	# 3. 应用所有配置（会自动触发滚动更新）
	kubectl apply -f deploy/ --recursive
	# 4. 等待滚动更新完成
	@echo "Waiting for rollout to complete..."
	kubectl rollout status deployment/aiops-copilot -n aiops --timeout=120s

delete:
	@echo "Deleting (keeping namespace)..."
	kubectl delete -f deploy/k8s-simple.yaml --ignore-not-found
	kubectl delete -f deploy/rbac.yaml --ignore-not-found
	kubectl delete -f deploy/secrets/ --recursive --ignore-not-found
	kubectl delete -f deploy/configmap/ --recursive --ignore-not-found

restart:
	@echo "Restarting pods..."
	kubectl rollout restart deployment/aiops-copilot -n aiops
	kubectl rollout status deployment/aiops-copilot -n aiops --timeout=120s

logs:
	kubectl logs -f deployment/aiops-copilot -n aiops

# 同步 VERSION 到 k8s-simple.yaml
sync-version:
	@echo "Syncing version to $(DOCKER_TAG)..."
	sed -i 's|image: $(IMAGE_REPOSITORY)/$(PROJECT)/$(IMAGE_NAME):.*|image: $(DOCKER_NAME):$(DOCKER_TAG)|' deploy/k8s-simple.yaml
