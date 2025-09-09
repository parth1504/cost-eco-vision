// Mock data for the ITOps dashboard

export interface Alert {
  id: string;
  type: "Security" | "Cost" | "Performance" | "Compliance";
  severity: "Critical" | "Warning" | "Info";
  title: string;
  description: string;
  suggestedAction: string;
  estimatedSavings?: number;
  resourceId: string;
  timestamp: string;
  status: "Active" | "Resolved" | "In Progress";
}

export interface Resource {
  id: string;
  name: string;
  type: "EC2" | "RDS" | "S3" | "Lambda" | "ELB";
  status: "Running" | "Idle" | "Stopped" | "Optimized";
  utilization: number;
  monthlyCost: number;
  region: string;
  recommendations: string[];
  lastActivity: string;
}

export interface Recommendation {
  id: string;
  resource: string;
  resourceType: string;
  issue: string;
  recommendation: string;
  estimatedSavings: number;
  impact: "High" | "Medium" | "Low";
  category: "Cost" | "Security" | "Performance";
  status: "Pending" | "Applied" | "Dismissed";
}

export interface Activity {
  id: string;
  action: string;
  resource: string;
  savings: number;
  timestamp: string;
  type: "Cost" | "Security" | "Performance";
}

export interface SecurityFinding {
  id: string;
  title: string;
  severity: "Critical" | "High" | "Medium" | "Low";
  description: string;
  resource: string;
  compliance: string[];
  remediation: string;
  estimatedCost?: number;
  status: "Open" | "Fixed" | "In Progress";
}

// Mock data
export const mockAlerts: Alert[] = [
  {
    id: "alert-1",
    type: "Cost",
    severity: "Critical",
    title: "Idle EC2 Instance Running",
    description: "EC2 instance i-0123456789 has been idle for 7 days",
    suggestedAction: "Stop instance or resize to smaller type",
    estimatedSavings: 245,
    resourceId: "i-0123456789",
    timestamp: "2024-01-15T10:30:00Z",
    status: "Active"
  },
  {
    id: "alert-2",
    type: "Security",
    severity: "Critical",
    title: "RDS Instance Publicly Accessible",
    description: "RDS instance prod-db is accessible from the internet",
    suggestedAction: "Remove public access and configure VPC security groups",
    resourceId: "prod-db",
    timestamp: "2024-01-15T09:15:00Z",
    status: "Active"
  },
  {
    id: "alert-3",
    type: "Performance",
    severity: "Warning",
    title: "High Memory Utilization",
    description: "EC2 instance web-server-1 showing 85% memory usage",
    suggestedAction: "Scale up instance or optimize application",
    resourceId: "web-server-1",
    timestamp: "2024-01-15T08:45:00Z",
    status: "In Progress"
  }
];

export const mockResources: Resource[] = [
  {
    id: "i-0123456789",
    name: "web-server-1",
    type: "EC2",
    status: "Running",
    utilization: 15,
    monthlyCost: 89.50,
    region: "us-east-1",
    recommendations: ["Right-size to t3.small", "Enable detailed monitoring"],
    lastActivity: "2024-01-15T12:00:00Z"
  },
  {
    id: "prod-db",
    name: "Production Database",
    type: "RDS",
    status: "Running",
    utilization: 67,
    monthlyCost: 234.00,
    region: "us-east-1",
    recommendations: ["Remove public access", "Enable encryption"],
    lastActivity: "2024-01-15T11:30:00Z"
  },
  {
    id: "backup-bucket",
    name: "Backup Storage",
    type: "S3",
    status: "Optimized",
    utilization: 0,
    monthlyCost: 45.20,
    region: "us-east-1",
    recommendations: ["Archive old data to Glacier"],
    lastActivity: "2024-01-14T20:15:00Z"
  }
];

export const mockRecommendations: Recommendation[] = [
  {
    id: "rec-1",
    resource: "web-server-1 (i-0123456789)",
    resourceType: "EC2",
    issue: "Low CPU utilization (15%)",
    recommendation: "Right-size from t3.medium to t3.small",
    estimatedSavings: 245,
    impact: "High",
    category: "Cost",
    status: "Pending"
  },
  {
    id: "rec-2",
    resource: "prod-db",
    resourceType: "RDS",
    issue: "Publicly accessible database",
    recommendation: "Remove public access and use VPC endpoints",
    estimatedSavings: 0,
    impact: "High",
    category: "Security",
    status: "Pending"
  },
  {
    id: "rec-3",
    resource: "backup-bucket",
    resourceType: "S3",
    issue: "Old data in Standard storage",
    recommendation: "Move data older than 90 days to Glacier",
    estimatedSavings: 156,
    impact: "Medium",
    category: "Cost",
    status: "Pending"
  }
];

export const mockActivities: Activity[] = [
  {
    id: "act-1",
    action: "EC2 instance i-abc123 stopped",
    resource: "web-server-2",
    savings: 42,
    timestamp: "2024-01-15T14:30:00Z",
    type: "Cost"
  },
  {
    id: "act-2",
    action: "Security group updated",
    resource: "prod-db",
    savings: 0,
    timestamp: "2024-01-15T13:15:00Z",
    type: "Security"
  },
  {
    id: "act-3",
    action: "S3 lifecycle policy applied",
    resource: "backup-bucket",
    savings: 89,
    timestamp: "2024-01-15T12:00:00Z",
    type: "Cost"
  }
];

export const mockSecurityFindings: SecurityFinding[] = [
  {
    id: "sec-1",
    title: "RDS Instance Publicly Accessible",
    severity: "Critical",
    description: "Database instance can be accessed from the internet",
    resource: "prod-db",
    compliance: ["SOC 2", "ISO 27001", "GDPR"],
    remediation: "Remove public access and configure VPC security groups",
    status: "Open"
  },
  {
    id: "sec-2",
    title: "S3 Bucket Not Encrypted",
    severity: "High",
    description: "Sensitive data stored without encryption at rest",
    resource: "backup-bucket",
    compliance: ["SOC 2", "HIPAA"],
    remediation: "Enable AES-256 server-side encryption",
    estimatedCost: 12,
    status: "Open"
  },
  {
    id: "sec-3",
    title: "Overly Permissive Security Group",
    severity: "Medium",
    description: "Security group allows inbound traffic from 0.0.0.0/0",
    resource: "web-sg",
    compliance: ["CIS Benchmark"],
    remediation: "Restrict inbound rules to specific IP ranges",
    status: "In Progress"
  }
];

export const mockSavingsData = {
  monthly: 1234,
  yearly: 14808,
  co2Reduced: 2.4,
  totalOptimizations: 23,
  chartData: [
    { month: "Jul", savings: 800 },
    { month: "Aug", savings: 950 },
    { month: "Sep", savings: 1100 },
    { month: "Oct", savings: 1050 },
    { month: "Nov", savings: 1300 },
    { month: "Dec", savings: 1234 }
  ]
};