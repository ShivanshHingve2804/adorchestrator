# AWS ECS deployment prerequisites

The `deploy-aws.yml` workflow is a manual deployment path to an already provisioned ECS Fargate API service. It uses GitHub OIDC and a protected `production` environment; it does not store long-lived AWS credentials in GitHub secrets.

Before enabling the workflow:

1. Provision an ECR repository, ECS cluster, Fargate service, networking/security groups, and CloudWatch log group `/ecs/adorchestrator-api`.
2. Provision PostgreSQL, Redis, Temporal, RabbitMQ, and the mock-platform service, or point the app at compatible managed endpoints. The other workers still need their own ECS task definitions/services.
3. Store `SECRET_KEY`, database password, broker URL, and optional AI key in AWS Secrets Manager. Grant the ECS execution role access to those secret ARNs and CloudWatch logs.
4. Configure the ECS task role and GitHub OIDC role with least privilege for the ECR repository and named ECS service/task family.
5. Set the `production` GitHub environment variables used by `deploy-aws.yml`, including `AWS_ROLE_ARN`, `AWS_REGION`, ECR/ECS names, endpoint names, secret ARNs, and JSON arrays for `ECS_SUBNET_IDS` and `ECS_SECURITY_GROUP_IDS`.
6. Set an environment reviewer in GitHub, then invoke the workflow manually. It runs migrations as a one-off Fargate task before updating the service; the migration task must be able to reach PostgreSQL.

The workflow builds and pushes the application image, registers a new API task definition, runs database migrations as a one-off task, updates the ECS service, and waits for stability. It does not run Terraform or create billable infrastructure automatically. Provision resources in the target account only after reviewing cost, network, backup, and secret-retention settings.
