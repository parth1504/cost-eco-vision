output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.app.id
}

output "instance_public_ip" {
  description = "Public IP of the application server"
  value       = aws_instance.app.public_ip
}

output "app_url" {
  description = "Application API URL"
  value       = "http://${aws_instance.app.public_ip}:8080"
}

output "log_group_name" {
  description = "CloudWatch log group for application logs"
  value       = aws_cloudwatch_log_group.app_logs.name
}

output "access_log_group_name" {
  description = "CloudWatch log group for access logs"
  value       = aws_cloudwatch_log_group.app_access_logs.name
}

output "security_group_id" {
  description = "Security group ID"
  value       = aws_security_group.app_sg.id
}
