resource "aws_db_subnet_group" "platform_db" {
  name       = "mindbridge-platform-db-subnet"
  subnet_ids = var.private_subnet_ids
}

resource "aws_db_parameter_group" "platform_db" {
  name   = "mindbridge-platform-db-params"
  family = "postgres16"

  parameter {
    name  = "log_connections"
    value = "1"
  }

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
}

resource "aws_db_instance" "platform_db" {
  identifier                  = "mindbridge-platform-db-${var.environment}"
  engine                      = "postgres"
  engine_version              = "16"
  instance_class              = var.db_instance_class
  allocated_storage           = 50
  max_allocated_storage       = 200
  db_name                     = "platform_db"
  username                    = "postgres"
  manage_master_user_password = true # Uses Secrets Manager
  
  db_subnet_group_name   = aws_db_subnet_group.platform_db.name
  parameter_group_name   = aws_db_parameter_group.platform_db.name
  vpc_security_group_ids = [aws_security_group.db.id]

  multi_az               = true
  storage_encrypted      = true
  backup_retention_period = 30
  skip_final_snapshot    = false
  final_snapshot_identifier = "mindbridge-platform-db-final-${var.environment}"

  tags = {
    Module = "platform_db"
  }
}
