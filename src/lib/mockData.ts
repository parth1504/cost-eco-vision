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
  provider?: "AWS" | "GCP" | "Azure";
}

export interface Resource {
  id: string;
  name: string;
  type: "EC2" | "RDS" | "S3" | "Lambda" | "ELB" | "DynamoDB";
  status: "Running" | "Idle" | "Stopped" | "Optimized";
  utilization: number;
  monthly_cost: number;
  region: string;
  provider?: "AWS" | "GCP" | "Azure";
  lastActivity: string;

  // NEW: Rich Recommendation Object
  recommendations: Array<{
    title: string;
    description: string;
    type: "cost" | "security" | "performance" | "compliance";
    severity: "critical" | "warning" | "info" | "resolved" | "in-progress";
    saving: number | "N/A";
    issue: string;
    impact: "high" | "medium" | "low";
    solution_steps: Array<{
      step: number;
      description: string;
      command: string;
    }>;
  }>;

  // NEW: Commands the agent will run (flattened list)
  commands?: Array<{
    step: number;
    title: string;
    command: string;
  }>;
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

export interface LeaderboardEntry {
  id: string;
  team: string;
  user: string;
  savings: number;
  optimizations: number;
  rank: number;
}

export interface DriftDetection {
  id: string;
  resource: string;
  resourceType: string;
  driftType: "Configuration" | "Security" | "Compliance";
  severity: "Critical" | "High" | "Medium" | "Low";
  actualValue: string;
  expectedValue: string;
  lastSync: string;
}

export interface CapacityForecast {
  resource: string;
  metric: "CPU" | "Memory" | "Storage" | "Network";
  current: number;
  predicted: number;
  timeframe: string;
  confidence: number;
  status: "Normal" | "Warning" | "Critical";
}

export interface IncidentEvent {
  id: string;
  timestamp: string;
  type: "Alert" | "Log" | "Metric" | "Action";
  source: string;
  message: string;
  severity: "Info" | "Warning" | "Critical";
}

export interface SecurityKey {
  id: string;
  name: string;
  type: "API Key" | "Service Account" | "SSH Key" | "Certificate";
  lastUsed: string;
  expiresIn: number; // days
  status: "Active" | "Unused" | "Expired";
}

// Mock data



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

// New advanced AI-agent features data

export const mockLeaderboard: LeaderboardEntry[] = [
  {
    id: "team-1",
    team: "Platform Team",
    user: "Sarah Chen",
    savings: 2847,
    optimizations: 12,
    rank: 1
  },
  {
    id: "team-2", 
    team: "Data Engineering",
    user: "Marcus Johnson",
    savings: 2156,
    optimizations: 8,
    rank: 2
  },
  {
    id: "team-3",
    team: "Mobile Team",
    user: "Elena Rodriguez",
    savings: 1943,
    optimizations: 15,
    rank: 3
  },
  {
    id: "team-4",
    team: "Web Frontend",
    user: "David Kim",
    savings: 1678,
    optimizations: 6,
    rank: 4
  }
];

export const mockDriftDetections: DriftDetection[] = [
  {
    id: "drift-1",
    resource: "prod-web-server",
    resourceType: "EC2",
    driftType: "Configuration",
    severity: "High",
    actualValue: "t3.large",
    expectedValue: "t3.medium",
    lastSync: "2024-01-14T10:30:00Z"
  },
  {
    id: "drift-2",
    resource: "database-security-group",
    resourceType: "Security Group",
    driftType: "Security",
    severity: "Critical",
    actualValue: "0.0.0.0/0:3306",
    expectedValue: "10.0.0.0/8:3306",
    lastSync: "2024-01-15T08:15:00Z"
  },
  {
    id: "drift-3",
    resource: "backup-bucket-policy",
    resourceType: "S3",
    driftType: "Compliance",
    severity: "Medium",
    actualValue: "Public Read",
    expectedValue: "Private",
    lastSync: "2024-01-15T12:00:00Z"
  }
];



export const mockIncidentTimeline: IncidentEvent[] = [
  {
    id: "event-1",
    timestamp: "2024-01-15T14:32:15Z",
    type: "Alert",
    source: "CloudWatch",
    message: "High CPU utilization detected on web-server-1",
    severity: "Warning"
  },
  {
    id: "event-2",
    timestamp: "2024-01-15T14:33:02Z", 
    type: "Metric",
    source: "Prometheus",
    message: "CPU usage spiked to 89% on web-server-1",
    severity: "Critical"
  },
  {
    id: "event-3",
    timestamp: "2024-01-15T14:34:18Z",
    type: "Log",
    source: "Application",
    message: "Database connection pool exhausted",
    severity: "Critical"
  },
  {
    id: "event-4",
    timestamp: "2024-01-15T14:35:45Z",
    type: "Action",
    source: "AI Agent",
    message: "Auto-scaling triggered: Added 2 instances",
    severity: "Info"
  }
];

export const mockSecurityKeys: SecurityKey[] = [
  {
    id: "key-1",
    name: "legacy-api-key",
    type: "API Key",
    lastUsed: "2023-08-15T10:30:00Z",
    expiresIn: 30,
    status: "Unused"
  },
  {
    id: "key-2",
    name: "old-service-account",
    type: "Service Account",
    lastUsed: "2023-12-01T15:22:00Z",
    expiresIn: -15,
    status: "Expired"
  },
  {
    id: "key-3",
    name: "backup-ssh-key",
    type: "SSH Key",
    lastUsed: "2024-01-10T09:15:00Z",
    expiresIn: 90,
    status: "Unused"
  }
];

export const mockSecurityScore = {
  current: 87,
  previous: 72,
  trend: "up",
  weeklyData: [
    { day: "Mon", score: 72 },
    { day: "Tue", score: 74 },
    { day: "Wed", score: 78 },
    { day: "Thu", score: 81 },
    { day: "Fri", score: 85 },
    { day: "Sat", score: 86 },
    { day: "Sun", score: 87 }
  ]
};


export const mockCapacityForecasts: CapacityForecast[] = [
  {
    resource: "web-cluster",
    metric: "CPU",
    current: 67,
    predicted: 89,
    timeframe: "Next 4 hours",
    confidence: 92,
    status: "Warning"
  },
  {
    resource: "database-main",
    metric: "Memory",
    current: 78,
    predicted: 95,
    timeframe: "Next 2 hours", 
    confidence: 88,
    status: "Critical"
  },
  {
    resource: "cache-cluster",
    metric: "CPU",
    current: 45,
    predicted: 52,
    timeframe: "Next 6 hours",
    confidence: 85,
    status: "Normal"
  }
];