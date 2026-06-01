output "alb_dns_name" {
  description = "The DNS name of the load balancer"
  value       = aws_lb.main.dns_name
}

output "auth_db_endpoint" {
  description = "The connection endpoint for the auth database"
  value       = aws_db_instance.auth_db.endpoint
}

output "platform_db_endpoint" {
  description = "The connection endpoint for the platform database"
  value       = aws_db_instance.platform_db.endpoint
}

output "redis_endpoint" {
  description = "The endpoint of the Redis cluster"
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "ecs_cluster_name" {
  description = "The name of the ECS cluster"
  value       = aws_ecs_cluster.main.name
}
