resource "aws_appautoscaling_target" "backend" {
  max_capacity       = 10
  min_capacity       = 2
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.backend.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "backend_cpu" {
  name               = "mindbridge-backend-cpu-autoscaling-${var.environment}"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.backend.resource_id
  scalable_dimension = aws_appautoscaling_target.backend.scalable_dimension
  service_namespace  = aws_appautoscaling_target.backend.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 70.0
    scale_in_cooldown  = 600 # 10 min
    scale_out_cooldown = 60
  }
}

resource "aws_appautoscaling_policy" "backend_queue" {
  name               = "mindbridge-backend-queue-autoscaling-${var.environment}"
  policy_type        = "StepScaling"
  resource_id        = aws_appautoscaling_target.backend.resource_id
  scalable_dimension = aws_appautoscaling_target.backend.scalable_dimension
  service_namespace  = aws_appautoscaling_target.backend.service_namespace

  step_scaling_policy_configuration {
    adjustment_type         = "ChangeInCapacity"
    cooldown                = 60
    metric_aggregation_type = "Maximum"

    step_adjustment {
      metric_interval_lower_bound = 0
      scaling_adjustment          = 2 # Trigger at 2.0x baseline, queue depth > 50
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "backend_queue_high" {
  alarm_name          = "mindbridge-backend-queue-high-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "QueueLength"
  namespace           = "MindBridge/Matching"
  period              = 60
  statistic           = "Maximum"
  threshold           = 50
  alarm_actions       = [aws_appautoscaling_policy.backend_queue.arn]
}
