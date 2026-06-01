terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    # Expected to be passed via backend config
    key    = "mindbridge/terraform.tfstate"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "MindBridge"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}
