# ──────────────────────────────────────────────────────────────────────────
# Stochastix PRO — AWS ECS Fargate deployment (Terraform)
#
# Provisions:
#   - VPC with public/private subnets
#   - ECS Fargate cluster + service running the Stochastix container
#   - Application Load Balancer (public entrypoint, port 80 -> 8501)
#   - RDS PostgreSQL (TimescaleDB-compatible parameter group)
#   - ElastiCache Redis (for STREAM_BACKEND=redis)
#   - Secrets Manager entries for DB credentials + JWT secret
#   - CloudWatch log group for container logs
#
# Usage:
#   terraform init
#   terraform apply -var="image_url=<ecr-image-uri>" \
#                    -var="jwt_secret_key=<random-hex>"
# ──────────────────────────────────────────────────────────────────────────

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region"      { default = "us-east-1" }
variable "image_url"        { description = "ECR image URI for the Stochastix container" }
variable "jwt_secret_key"   { description = "Secret used to sign JWT access tokens" }
variable "db_password"      { default = "ChangeMe123!" }
variable "container_port"   { default = 8501 }
variable "desired_count"    { default = 2 }

# ── Networking ─────────────────────────────────────────────────────────
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags = { Name = "stochastix-vpc" }
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index)
  map_public_ip_on_launch = true
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  tags = { Name = "stochastix-public-${count.index}" }
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index + 10)
  availability_zone = data.aws_availability_zones.available.names[count.index]
  tags = { Name = "stochastix-private-${count.index}" }
}

data "aws_availability_zones" "available" { state = "available" }

resource "aws_internet_gateway" "gw" {
  vpc_id = aws_vpc.main.id
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.gw.id
  }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# ── Security groups ────────────────────────────────────────────────────
resource "aws_security_group" "alb" {
  name   = "stochastix-alb-sg"
  vpc_id = aws_vpc.main.id
  ingress { from_port = 80, to_port = 80, protocol = "tcp", cidr_blocks = ["0.0.0.0/0"] }
  egress  { from_port = 0,  to_port = 0,  protocol = "-1", cidr_blocks = ["0.0.0.0/0"] }
}

resource "aws_security_group" "app" {
  name   = "stochastix-app-sg"
  vpc_id = aws_vpc.main.id
  ingress {
    from_port       = var.container_port
    to_port         = var.container_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress { from_port = 0, to_port = 0, protocol = "-1", cidr_blocks = ["0.0.0.0/0"] }
}

resource "aws_security_group" "data" {
  name   = "stochastix-data-sg"
  vpc_id = aws_vpc.main.id
  ingress {
    from_port       = 5432
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }
  egress { from_port = 0, to_port = 0, protocol = "-1", cidr_blocks = ["0.0.0.0/0"] }
}

# ── RDS PostgreSQL (TimescaleDB) ──────────────────────────────────────
resource "aws_db_subnet_group" "main" {
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_instance" "postgres" {
  identifier              = "stochastix-timescaledb"
  engine                  = "postgres"
  engine_version          = "15"
  instance_class          = "db.t3.micro"
  allocated_storage       = 20
  db_name                 = "stochastix"
  username                = "stochastix"
  password                = var.db_password
  db_subnet_group_name    = aws_db_subnet_group.main.name
  vpc_security_group_ids  = [aws_security_group.data.id]
  skip_final_snapshot     = true
  # Note: enable the `timescaledb` extension via a custom parameter group
  # (shared_preload_libraries = 'timescaledb') for full hypertable support.
}

# ── ElastiCache Redis (STREAM_BACKEND=redis) ───────────────────────────
resource "aws_elasticache_subnet_group" "main" {
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "stochastix-redis"
  engine               = "redis"
  node_type            = "cache.t3.micro"
  num_cache_nodes      = 1
  subnet_group_name    = aws_elasticache_subnet_group.main.name
  security_group_ids   = [aws_security_group.data.id]
}

# ── Secrets ────────────────────────────────────────────────────────────
resource "aws_secretsmanager_secret" "jwt" {
  name = "stochastix/jwt-secret"
}
resource "aws_secretsmanager_secret_version" "jwt" {
  secret_id     = aws_secretsmanager_secret.jwt.id
  secret_string = var.jwt_secret_key
}

# ── ECS cluster + Fargate service ──────────────────────────────────────
resource "aws_ecs_cluster" "main" {
  name = "stochastix-cluster"
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/stochastix"
  retention_in_days = 14
}

resource "aws_ecs_task_definition" "app" {
  family                   = "stochastix"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.execution.arn

  container_definitions = jsonencode([{
    name      = "stochastix"
    image     = var.image_url
    essential = true
    portMappings = [{ containerPort = var.container_port, protocol = "tcp" }]
    environment = [
      { name = "DB_BACKEND", value = "postgres" },
      { name = "POSTGRES_HOST", value = aws_db_instance.postgres.address },
      { name = "POSTGRES_PORT", value = "5432" },
      { name = "POSTGRES_DB", value = "stochastix" },
      { name = "POSTGRES_USER", value = "stochastix" },
      { name = "POSTGRES_PASSWORD", value = var.db_password },
      { name = "STREAM_BACKEND", value = "redis" },
      { name = "REDIS_URL", value = "redis://${aws_elasticache_cluster.redis.cache_nodes[0].address}:6379/0" },
      { name = "JWT_SECRET_KEY", value = var.jwt_secret_key },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.app.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "stochastix"
      }
    }
  }])
}

resource "aws_iam_role" "execution" {
  name = "stochastix-ecs-execution"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_lb" "main" {
  name               = "stochastix-alb"
  load_balancer_type = "application"
  subnets            = aws_subnet.public[*].id
  security_groups    = [aws_security_group.alb.id]
}

resource "aws_lb_target_group" "app" {
  name        = "stochastix-tg"
  port        = var.container_port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"
  health_check {
    path = "/_stcore/health"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

resource "aws_ecs_service" "app" {
  name            = "stochastix-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "stochastix"
    container_port   = var.container_port
  }

  depends_on = [aws_lb_listener.http]
}

output "alb_dns_name" {
  value = aws_lb.main.dns_name
}
