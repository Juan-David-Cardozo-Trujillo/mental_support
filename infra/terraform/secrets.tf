resource "aws_secretsmanager_secret" "jwt" {
  name        = "mental-health/jwt-secret-${var.environment}"
  description = "JWT Secret Key for MindBridge Platform"
}

resource "aws_secretsmanager_secret" "aes" {
  name        = "mental-health/aes-key-${var.environment}"
  description = "AES-256 Key for Data Encryption"
}

resource "aws_secretsmanager_secret" "db_auth" {
  name        = "mental-health/db-auth-password-${var.environment}"
  description = "Auth Database Master Password"
}

resource "aws_secretsmanager_secret" "db_platform" {
  name        = "mental-health/db-platform-password-${var.environment}"
  description = "Platform Database Master Password"
}

resource "aws_secretsmanager_secret" "sso" {
  name        = "mental-health/sso-client-secret-${var.environment}"
  description = "University SSO Client Secret"
}
