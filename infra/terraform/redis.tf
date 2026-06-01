resource "aws_elasticache_subnet_group" "redis" {
  name       = "mindbridge-redis-subnet"
  subnet_ids = var.private_subnet_ids
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id          = "mindbridge-redis-${var.environment}"
  description                   = "Redis cluster for MindBridge sessions and celery"
  node_type                     = var.redis_node_type
  port                          = 6379
  parameter_group_name          = "default.redis7"
  automatic_failover_enabled    = true
  
  num_cache_clusters            = 2

  engine_version                = "7.0"
  subnet_group_name             = aws_elasticache_subnet_group.redis.name
  security_group_ids            = [aws_security_group.redis.id]

  at_rest_encryption_enabled    = true
  transit_encryption_enabled    = true

  tags = {
    Module = "shared"
  }
}
