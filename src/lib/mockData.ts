// Mock data for the ITOps dashboard

export interface Alert {
  id: string;
  type: "Security" | "Cost" | "Performance" | "Compliance";
  severity: "Critical" | "Warning" | "Info";
  title: string;
  description: string;
  suggestedAction: string;
  estimatedSavings?: number | "N/A";
  resourceId: string;
  timestamp: string;
  status: "Active" | "Resolved" | "In Progress";
  provider?: "AWS" | "GCP" | "Azure";
  solution_steps?: Array<{
    step: number;
    description: string;
    command: string;
  }>;
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
  remediation: {
    title: string;
    steps: {
      step: number;
      description: string;
      command: string;
    }[]
  };
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






export const mockSavingsData = {
  monthly: 1234,
  yearly: 14808,
  co2Reduced: 2.4,
  totalOptimizations: 23,
  chartData: [
    { month: "Jul", savings: 25 },
    { month: "Aug", savings: 24 },
    { month: "Sep", savings: 31 },
    { month: "Oct", savings: 30 },
    { month: "Nov", savings: 22 }
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

