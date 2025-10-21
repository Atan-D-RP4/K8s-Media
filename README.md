# Kubernetes Media Server Deployment

This directory contains the separated Kubernetes manifests for deploying the media server stack. The manifests are organized by resource type and should be applied in the correct order to ensure dependencies are satisfied.

## Directory Structure

```
manifests/
├── namespaces/        # Namespace definitions
├── storage/           # PV and PVC definitions
├── configs/           # ConfigMaps for application configuration
├── traefik/           # Traefik reverse proxy setup
├── deployments/       # Application deployments
├── services/          # Service definitions
├── ingress/           # Ingress routes and middlewares
└── jobs/              # CronJobs (e.g., Picard auto-tagging)
```

## Deployment

Apply the manifests in the following order:

```bash
kubectl apply -f manifests/namespaces/ # 1. Namespaces
kubectl apply -f manifests/storage/ # 2. Storage
kubectl apply -f manifests/configs/ # 3. ConfigMaps
kubectl apply -f manifests/deployments/ # 4. Application deployments
kubectl apply -f manifests/services/ # 5. Services
kubectl apply -f https://raw.githubusercontent.com/traefik/traefik/v3.1/docs/content/reference/dynamic-configuration/kubernetes-crd-definition-v1.yml # 6. Traefik CRDs (one-time setup):
kubectl apply -f manifests/traefik/ # 7. Traefik RBAC and deployment
kubectl apply -f manifests/ingress/middlewares.yml # 8. Ingress middlewares
kubectl apply -f manifests/ingress/routes # 9. Ingress routes
kubectl apply -f manifests/jobs/ # 10. Jobs
```

## Configuration

Before deploying, ensure you update:

1. Domain names in ingress/routes.yaml (replace YOUR_PUBLIC_IP)
2. Storage paths in storage/media-storage.yaml
3. Credentials in configs/\*.yaml
4. Email in traefik/deployment.yaml

## Port Forwarding

Configure your router to forward:

- Port 80 → NodePort 30080
- Port 443 → NodePort 30443

## Access

After deployment, services will be available at:

- https://lidarr.YOUR_PUBLIC_IP.sslip.io
- https://prowlarr.YOUR_PUBLIC_IP.sslip.io
- https://slskd.YOUR_PUBLIC_IP.sslip.io
- https://traefik.YOUR_PUBLIC_IP.sslip.io/dashboard/
- https://<service>.\<YOUR_PUBLIC_IP>.sslip.io

If using a custom domain:

- https://lidarr.\<YOUR_DOMAIN>
- https://prowlarr.\<YOUR_DOMAIN>
- https://slskd.\<YOUR_DOMAIN>
- https://traefik.\<YOUR_DOMAIN>/dashboard/
- https://service.\<YOUR_DOMAIN>

## Extension

To add more services, create new deployment, service, and ingress manifests in
their respective directories and apply them following the same order.

- Create a new deployment in `manifests/deployments/` for the service's container.
- Create a corresponding service in `manifests/services/` to expose the deployment.
- Add an ingress route in `manifests/ingress/routes/` to route traffic to the new service.
  - manifest/ingress/routes\_<service>.yaml
- Update ConfigMaps in `manifests/configs/` if the new service requires specific configuration.
- Ensure any required storage is defined in `manifests/storage/`.
- If the service requires scheduled tasks, add a CronJob in `manifests/jobs/`.
- Update Traefik middlewares in `manifests/ingress/middlewares.yml` if necessary.
- Apply the new manifests using `kubectl apply -f` in the correct order.
- Test access to the new service via the defined ingress route.
  - https://<service>.\<YOUR_PUBLIC_IP>.sslip.io
  - https://lidarr.<custom-domain> if using a custom domain
- Monitor logs and resource usage to ensure the new service is running smoothly.
- Document any specific configurations or dependencies for future reference.
- Adjust resource requests and limits in the deployment manifest to ensure optimal performance.
- Set up alerts or monitoring for the new service if required.
- Backup configurations and data for the new service as part of your regular backup strategy.
- Regularly update the new service's container image to ensure it has the latest features and security
  patches.
- Keep documentation up to date with any changes made to the deployment or configuration of the new service
- Periodically review and clean up unused resources to maintain a tidy and efficient cluster environment.
- Test integration with other services in the stack to ensure seamless operation.
- Set up user authentication and authorization if the new service requires secure access.
