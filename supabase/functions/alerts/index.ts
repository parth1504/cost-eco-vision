import { createClient } from 'https://esm.sh/@supabase/supabase-js@2.39.3';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

// Mock alerts data (moved from frontend)
const mockAlerts = [
  {
    id: "alert-1",
    title: "EC2 Instance Running Idle",
    description: "Instance i-0123456789abcdef has been running with <5% CPU for 7 days",
    severity: "Warning" as const,
    type: "Cost",
    resourceId: "i-0123456789abcdef",
    status: "Active" as const,
    timestamp: "2025-01-15T10:30:00Z",
    estimatedSavings: 42,
    suggestedAction: "Consider stopping or downsizing this instance. AI analysis shows this workload could run on a t3.micro instead of t3.large, saving $42/month."
  },
  {
    id: "alert-2",
    title: "S3 Bucket Publicly Accessible",
    description: "Bucket prod-data-storage has public read access enabled",
    severity: "Critical" as const,
    type: "Security",
    resourceId: "prod-data-storage",
    status: "Active" as const,
    timestamp: "2025-01-15T09:15:00Z",
    suggestedAction: "This is a critical security risk. Remove public access and implement proper IAM policies. Apply recommended bucket policy to restrict access to authorized users only."
  },
  {
    id: "alert-3",
    title: "RDS Database Underutilized",
    description: "Database prod-mysql-01 running at 15% capacity",
    severity: "Warning" as const,
    type: "Cost",
    resourceId: "prod-mysql-01",
    status: "In Progress" as const,
    timestamp: "2025-01-15T08:45:00Z",
    estimatedSavings: 180,
    suggestedAction: "Downsize from db.m5.2xlarge to db.m5.xlarge to match actual usage patterns. This will save $180/month while maintaining performance."
  },
  {
    id: "alert-4",
    title: "Unencrypted EBS Volume",
    description: "Volume vol-abc123 is not encrypted",
    severity: "Critical" as const,
    type: "Security",
    resourceId: "vol-abc123",
    status: "Active" as const,
    timestamp: "2025-01-15T07:20:00Z",
    suggestedAction: "Create encrypted snapshot and restore to new encrypted volume. AI can automate this process during next maintenance window."
  },
  {
    id: "alert-5",
    title: "Unused Elastic IP",
    description: "Elastic IP 54.123.45.67 not associated with any instance",
    severity: "Info" as const,
    type: "Cost",
    resourceId: "54.123.45.67",
    status: "Resolved" as const,
    timestamp: "2025-01-14T16:30:00Z",
    estimatedSavings: 3.6,
    suggestedAction: "Release unused Elastic IP to save $3.60/month."
  },
  {
    id: "alert-6",
    title: "Old AMI Snapshots",
    description: "12 AMI snapshots older than 90 days detected",
    severity: "Info" as const,
    type: "Cost",
    resourceId: "snapshot-group-1",
    status: "Active" as const,
    timestamp: "2025-01-14T14:00:00Z",
    estimatedSavings: 24,
    suggestedAction: "Delete old snapshots that are no longer needed. Keep only recent 3 versions per image."
  },
  {
    id: "alert-7",
    title: "IAM Policy Too Permissive",
    description: "Policy dev-access grants admin rights to 15 users",
    severity: "Warning" as const,
    type: "Security",
    resourceId: "dev-access",
    status: "Active" as const,
    timestamp: "2025-01-14T11:20:00Z",
    suggestedAction: "Implement least-privilege principle. AI recommends splitting into role-based policies with granular permissions."
  },
  {
    id: "alert-8",
    title: "Lambda Function Over-Provisioned",
    description: "Function data-processor using only 30% of allocated memory",
    severity: "Warning" as const,
    type: "Cost",
    resourceId: "data-processor",
    status: "In Progress" as const,
    timestamp: "2025-01-14T09:10:00Z",
    estimatedSavings: 35,
    suggestedAction: "Reduce memory allocation from 3GB to 1GB based on actual usage patterns."
  }
];

Deno.serve(async (req) => {
  // Handle CORS preflight requests
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const url = new URL(req.url);
    const pathParts = url.pathname.split('/').filter(Boolean);
    
    console.log('Alerts endpoint called:', { method: req.method, pathname: url.pathname });

    // GET /alerts - Return all alerts
    if (req.method === 'GET' && pathParts.length === 1) {
      console.log('Returning all alerts:', mockAlerts.length);
      return new Response(
        JSON.stringify({ data: mockAlerts }),
        { 
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
          status: 200 
        }
      );
    }

    // GET /alerts/{id} - Return specific alert
    if (req.method === 'GET' && pathParts.length === 2) {
      const alertId = pathParts[1];
      const alert = mockAlerts.find(a => a.id === alertId);
      
      if (!alert) {
        console.log('Alert not found:', alertId);
        return new Response(
          JSON.stringify({ error: 'Alert not found' }),
          { 
            headers: { ...corsHeaders, 'Content-Type': 'application/json' },
            status: 404 
          }
        );
      }

      console.log('Returning alert:', alertId);
      return new Response(
        JSON.stringify({ data: alert }),
        { 
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
          status: 200 
        }
      );
    }

    // Method not allowed
    return new Response(
      JSON.stringify({ error: 'Method not allowed' }),
      { 
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        status: 405 
      }
    );

  } catch (error) {
    console.error('Error in alerts function:', error);
    return new Response(
      JSON.stringify({ error: error.message }),
      { 
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        status: 500 
      }
    );
  }
});
