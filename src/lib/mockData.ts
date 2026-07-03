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
  status: "Running" | "Idle" | "Stopped" | "optimized";
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
    boto3Commands?: Array<{
      service: string;
  operation: string;
  params: Record<string, any>;
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







