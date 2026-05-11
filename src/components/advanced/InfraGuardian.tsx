import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { GitBranch, AlertTriangle, CheckCircle, ExternalLink, Code2, Settings } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 }
};

export function InfraGuardian() {
  const [drifts, setDrifts] = useState<any[]>([]);
  const [selectedDrift, setSelectedDrift] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();

  useEffect(() => {
    fetchDriftData();
  }, []);

  const handleFix = async (drift: any, direction: string) => {
  try {
    // Map frontend shape back to backend shape
    const backendDrift = {
      resource_id: drift.resource,
      resource_type: drift.resourceType,
      field: drift.driftType,
      severity: drift.severity,
      aws_value: drift.actualValue,
      terraform_value: drift.expectedValue,
      detected_at: drift.lastSync,
    };

    const response = await fetch("http://localhost:8000/drift/fix", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
        drift: backendDrift,  // Send the mapped version
        fix_direction: direction 
      }),
    });
    
    const data = await response.json();
    
    toast({
      title: "✅ PR Created",
      description: (
        <Button
          variant="link"
          onClick={() => window.open(data.pr_url, "_blank")}
        >
          View PR #{data.pr_number}
        </Button>
      ),
    });
  } catch (err: any) {
    toast({
      title: "❌ Failed to create PR",
      description: err.message,
      variant: "destructive",
    });
  }
};

  const fetchDriftData = async () => {
  try {
    console.log("🔄 Fetching drift data from backend...");
    const response = await fetch("http://localhost:8000/drift/data");
    
    if (!response.ok) {
      throw new Error(`Backend returned ${response.status}`);
    }
    
    const data = await response.json();
    console.log("✅ Successfully fetched drift data:", data);

    // Map backend shape → frontend shape
    const mapped = (data.drifts || []).map((d: any, index: number) => ({
      id: d.resource_id ? `${d.resource_type}-${d.resource_id}-${d.field}-${index}` : `drift-${index}`,
      resource: d.resource_id || "Unknown",
      resourceType: d.resource_type || "Unknown",
      driftType: d.field || "Configuration",
      severity: d.severity || "Low",
      actualValue: d.aws_value || "N/A",          // FIXED
      expectedValue: d.terraform_value || "N/A",  // FIXED
      reason: d.reason || "",
      lastSync: d.detected_at || new Date().toISOString(),
    }));

    setDrifts(mapped);
  } catch (error) {
    console.error("❌ Failed to fetch drift data:", error);
    setDrifts([]);
  } finally {
    setLoading(false);
  }
};

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'Critical': return 'status-critical';
      case 'High': return 'status-warning';
      case 'Medium': return 'bg-warning/10 text-warning border border-warning/20';
      default: return 'bg-muted text-muted-foreground';
    }
  };

  const handleAutoFix = async (driftId: string) => {
  try {
    const response = await fetch("http://localhost:8000/drift/autofix", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ drift_id: driftId }),
    });

    if (!response.ok) {
      throw new Error(`Backend returned ${response.status}`);
    }

    const data = await response.json();

    // show success
    toast({
      title: "🚀 Auto-Fix Triggered",
      description: (
        <div className="space-y-2">
          <p>{data.message}</p>

          {data.pr_url && (
            <Button
              variant="link"
              size="sm"
              className="p-0 h-auto text-primary"
              onClick={() => window.open(data.pr_url, "_blank")}
            >
              <ExternalLink className="h-3 w-3 mr-1" />
              View PR on GitHub
            </Button>
          )}
        </div>
      ),
    });

    // remove drift from list dynamically
    setDrifts((prev) => prev.filter((d) => d.id !== driftId));

  } catch (err: any) {
    console.error("Auto-fix failed:", err);
    toast({
      title: "❌ Auto-Fix Failed",
      description: err.message,
      variant: "destructive",
    });
  }
};


  if (loading) {
    return <div className="text-center text-muted-foreground">Loading drift detection data...</div>;
  }

  return (
    <div className="space-y-6">
      {/* Drift Detection Overview */}
      <motion.div variants={itemVariants}>
        <Card className="dashboard-card">
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <GitBranch className="h-5 w-5 text-warning" />
              <span>Infrastructure Drift Detection</span>
            </CardTitle>
            <CardHeader>
  <div className="flex items-center justify-between">
    <div>
      <CardTitle className="flex items-center space-x-2">
        <GitBranch className="h-5 w-5 text-warning" />
        <span>Infrastructure Drift Detection</span>
      </CardTitle>
      <CardDescription>
        Resources that have drifted from their defined Infrastructure as Code
      </CardDescription>
    </div>
    <div className="flex items-center space-x-2">
      <Button
        variant="outline"
        size="sm"
        onClick={async () => {
          try {
            const res = await fetch("http://localhost:8000/drift/baseline", {
              method: "POST",
            });
            const data = await res.json();
            toast({
              title: "✅ Baseline Set",
              description: "Current AWS state saved as baseline.",
            });
          } catch (err: any) {
            toast({
              title: "❌ Failed to set baseline",
              description: err.message,
              variant: "destructive",
            });
          }
        }}
      >
        Set Baseline
      </Button>
      <Button size="sm" onClick={fetchDriftData}>
        Check for Drift
      </Button>
    </div>
  </div>
</CardHeader>
            <CardDescription>
              Resources that have drifted from their defined Infrastructure as Code
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-4 mb-6">
              <div className="text-center p-3 bg-critical/5 border border-critical/20 rounded-lg">
                <p className="text-2xl font-bold text-critical">
                  {drifts.filter(d => d.severity === 'Critical').length}
                </p>
                <p className="text-sm text-muted-foreground">Critical</p>
              </div>
              <div className="text-center p-3 bg-warning/5 border border-warning/20 rounded-lg">
                <p className="text-2xl font-bold text-warning">
                  {drifts.filter(d => d.severity === 'High').length}
                </p>
                <p className="text-sm text-muted-foreground">High</p>
              </div>
              <div className="text-center p-3 bg-muted/30 rounded-lg">
                <p className="text-2xl font-bold text-foreground">
                  {drifts.filter(d => d.severity === 'Medium').length}
                </p>
                <p className="text-sm text-muted-foreground">Medium</p>
              </div>
            </div>

            <div className="space-y-4">
              {drifts.map((drift) => (
                <div
                  key={drift.id}
                  className="flex items-center justify-between p-4 border rounded-lg hover:bg-muted/30 transition-colors"
                >
                  <div className="flex items-center space-x-4">
                    <div className="flex items-center justify-center w-10 h-10 bg-muted/50 rounded-lg">
                      <Settings className="h-5 w-5 text-muted-foreground" />
                    </div>
                    
                    <div>
                      <div className="flex items-center space-x-2 mb-1">
                        <p className="font-medium text-foreground">{drift.resource}</p>
                        <Badge variant="outline" className="text-xs">{drift.resourceType}</Badge>
                        <Badge className={getSeverityColor(drift.severity)}>
                          {drift.severity}
                        </Badge>
                      </div>
                      <p className="text-sm text-muted-foreground">{drift.driftType} drift detected</p>
                    </div>
                  </div>

                  <div className="flex items-center space-x-3">
                    <Dialog>
                      <DialogTrigger asChild>
                        <Button 
                          variant="outline" 
                          size="sm"
                          onClick={() => setSelectedDrift(drift)}
                        >
                          <Code2 className="h-4 w-4 mr-2" />
                          View Diff
                        </Button>
                      </DialogTrigger>
                      <DialogContent className="max-w-2xl">
                        <DialogHeader>
                          <DialogTitle>Infrastructure Drift: {drift.resource}</DialogTitle>
                          <DialogDescription>
                            Comparing actual state vs. expected Infrastructure as Code
                          </DialogDescription>
                        </DialogHeader>
                        
                        <div className="space-y-4">
                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <h4 className="font-medium text-foreground mb-2 flex items-center">
                                <span className="w-3 h-3 bg-critical rounded-full mr-2"></span>
                                Actual State
                              </h4>
                              <div className="p-3 bg-critical/5 border border-critical/20 rounded font-mono text-sm">
                                {drift.actualValue}
                              </div>
                            </div>
                            <div>
                              <h4 className="font-medium text-foreground mb-2 flex items-center">
                                <span className="w-3 h-3 bg-success rounded-full mr-2"></span>
                                Expected State
                              </h4>
                              <div className="p-3 bg-success/5 border border-success/20 rounded font-mono text-sm">
                                {drift.expectedValue}
                              </div>
                            </div>
                          </div>
                          
                          <div className="p-4 bg-muted/30 rounded-lg">
                            <p className="text-sm">
                              <strong>Impact:</strong> This drift affects {(drift.driftType || "configuration").toLowerCase()} compliance

                            </p>
                          </div>
                        </div>
                      </DialogContent>
                    </Dialog>

                   <div className="flex items-center space-x-2">
  <Button
    size="sm"
    variant="outline"
    onClick={() => handleFix(drift, "aws_to_terraform")}
  >
    <GitBranch className="h-4 w-4 mr-2" />
    Update Terraform
  </Button>
  <Button
    size="sm"
    onClick={() => handleFix(drift, "terraform_to_aws")}
    className="action-success"
  >
    <GitBranch className="h-4 w-4 mr-2" />
    Apply Terraform
  </Button>
</div>
                  </div>
                </div>
              ))}
            </div>

            {drifts.length === 0 && (
              <div className="text-center py-8">
                <CheckCircle className="h-12 w-12 text-success mx-auto mb-4" />
                <p className="text-lg font-medium text-success">All infrastructure is in sync!</p>
                <p className="text-sm text-muted-foreground">No drift detected from your IaC definitions</p>
              </div>
            )}
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}