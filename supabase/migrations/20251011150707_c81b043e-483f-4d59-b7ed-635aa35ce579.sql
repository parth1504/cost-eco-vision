-- Create alerts table
CREATE TABLE public.alerts (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('critical', 'warning', 'info')),
  message TEXT NOT NULL,
  timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'resolved', 'acknowledged')),
  source TEXT NOT NULL,
  affected_resources TEXT[] DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- Create resources table
CREATE TABLE public.resources (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('EC2', 'RDS', 'S3', 'Lambda')),
  region TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('Running', 'Idle', 'Stopped', 'Optimized')),
  utilization INTEGER NOT NULL CHECK (utilization >= 0 AND utilization <= 100),
  monthly_cost DECIMAL(10,2) NOT NULL,
  last_activity TIMESTAMP WITH TIME ZONE NOT NULL,
  recommendations TEXT[] DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- Enable RLS
ALTER TABLE public.alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.resources ENABLE ROW LEVEL SECURITY;

-- Create policies for public access (since no authentication is implemented)
CREATE POLICY "Allow public read access to alerts" 
ON public.alerts FOR SELECT 
USING (true);

CREATE POLICY "Allow public insert to alerts" 
ON public.alerts FOR INSERT 
WITH CHECK (true);

CREATE POLICY "Allow public update to alerts" 
ON public.alerts FOR UPDATE 
USING (true);

CREATE POLICY "Allow public delete to alerts" 
ON public.alerts FOR DELETE 
USING (true);

CREATE POLICY "Allow public read access to resources" 
ON public.resources FOR SELECT 
USING (true);

CREATE POLICY "Allow public insert to resources" 
ON public.resources FOR INSERT 
WITH CHECK (true);

CREATE POLICY "Allow public update to resources" 
ON public.resources FOR UPDATE 
USING (true);

CREATE POLICY "Allow public delete to resources" 
ON public.resources FOR DELETE 
USING (true);

-- Insert mock data for alerts
INSERT INTO public.alerts (id, title, severity, message, timestamp, status, source, affected_resources) VALUES
('alert-1', 'High CPU Usage Detected', 'critical', 'EC2 instance i-1234567890abcdef0 has exceeded 90% CPU usage for 15 minutes', now() - interval '5 minutes', 'active', 'CloudWatch', ARRAY['i-1234567890abcdef0']),
('alert-2', 'Database Connection Pool Near Limit', 'warning', 'RDS instance db-prod-01 has 85% of connections in use', now() - interval '1 hour', 'active', 'RDS Monitoring', ARRAY['db-prod-01']),
('alert-3', 'Unusual API Request Pattern', 'warning', 'API Gateway detecting 300% increase in 4xx errors', now() - interval '30 minutes', 'acknowledged', 'API Gateway', ARRAY['api-gateway-prod']),
('alert-4', 'Storage Capacity Warning', 'info', 'S3 bucket approaching 80% of allocated quota', now() - interval '2 hours', 'active', 'S3 Monitoring', ARRAY['s3-bucket-data']),
('alert-5', 'Lambda Function Timeout', 'critical', 'Function data-processor exceeded timeout threshold 3 times', now() - interval '10 minutes', 'active', 'Lambda', ARRAY['lambda-data-processor']);

-- Insert mock data for resources
INSERT INTO public.resources (id, name, type, region, status, utilization, monthly_cost, last_activity, recommendations) VALUES
('res-1', 'Web Server 01', 'EC2', 'us-east-1', 'Running', 75, 245.50, now() - interval '5 minutes', ARRAY['Consider right-sizing to t3.medium', 'Enable auto-scaling']),
('res-2', 'Production Database', 'RDS', 'us-east-1', 'Running', 68, 580.00, now() - interval '2 minutes', ARRAY['Upgrade to newer instance type', 'Enable Multi-AZ']),
('res-3', 'Static Assets Bucket', 'S3', 'us-west-2', 'Idle', 25, 45.20, now() - interval '3 hours', ARRAY['Enable intelligent tiering', 'Implement lifecycle policies']),
('res-4', 'Data Processor', 'Lambda', 'eu-west-1', 'Running', 45, 125.80, now() - interval '1 minute', ARRAY['Optimize memory allocation', 'Review timeout settings']),
('res-5', 'Analytics DB', 'RDS', 'ap-south-1', 'Idle', 15, 420.00, now() - interval '4 hours', ARRAY['Consider Aurora Serverless', 'Schedule stop/start']),
('res-6', 'API Server 02', 'EC2', 'us-east-1', 'Optimized', 55, 180.30, now() - interval '10 minutes', ARRAY[]::TEXT[]);