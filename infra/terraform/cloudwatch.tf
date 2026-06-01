resource "aws_sns_topic" "alerts" {
  name = "mindbridge-alerts-${var.environment}"
}

# Uptime Alarm
resource "aws_cloudwatch_metric_alarm" "uptime" {
  alarm_name          = "mindbridge-uptime-alarm-${var.environment}"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Uptime"
  namespace           = "MindBridge/Platform"
  period              = 86400 # 24h
  statistic           = "Average"
  threshold           = 99.0
  alarm_description   = "Triggered when uptime is < 99% in 24h"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# API Latency Alarm
resource "aws_cloudwatch_metric_alarm" "api_latency" {
  alarm_name          = "mindbridge-api-latency-alarm-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApiLatencyP95"
  namespace           = "MindBridge/Platform"
  period              = 300 # 5m
  statistic           = "Average"
  threshold           = 2000 # 2s
  alarm_description   = "Triggered when API P95 latency > 2s for 5m"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# Queue Length Alarm
resource "aws_cloudwatch_metric_alarm" "queue_length" {
  alarm_name          = "mindbridge-queue-length-alarm-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "QueueLength"
  namespace           = "MindBridge/Matching"
  period              = 60
  statistic           = "Maximum"
  threshold           = 20
  alarm_description   = "Triggered when queue length > 20 students"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# Burnout Count Alarm
resource "aws_cloudwatch_metric_alarm" "burnout_count" {
  alarm_name          = "mindbridge-burnout-count-alarm-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "BurnoutCount"
  namespace           = "MindBridge/Peer"
  period              = 3600
  statistic           = "Maximum"
  threshold           = 2
  alarm_description   = "Triggered when peer burnout count > 2"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# Error Rate Alarm
resource "aws_cloudwatch_metric_alarm" "error_rate" {
  alarm_name          = "mindbridge-error-rate-alarm-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "5XXErrorRate"
  namespace           = "AWS/ApplicationELB"
  period              = 300 # 5m
  statistic           = "Average"
  threshold           = 5.0
  alarm_description   = "CRITICAL: Triggered when 5XX error rate > 5% for 5m"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# Satisfaction Alarm
resource "aws_cloudwatch_metric_alarm" "satisfaction" {
  alarm_name          = "mindbridge-satisfaction-alarm-${var.environment}"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "AverageSatisfaction"
  namespace           = "MindBridge/Feedback"
  period              = 86400
  statistic           = "Average"
  threshold           = 3.5
  alarm_description   = "Triggered when average satisfaction < 3.5"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}
